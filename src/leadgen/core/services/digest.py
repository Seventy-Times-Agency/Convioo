"""Daily-digest builder + dispatcher.

Once a day the worker calls :func:`run_daily_digest_for_all_users` which
iterates over users opted into ``daily_digest_enabled`` and emails each
one a small summary of the previous 24 hours: new leads in their CRM,
hot leads (score ≥ 75), and any lead that received a reply since the
last tick. Users who opted out, who have no activity, or who don't yet
have a verified email are silently skipped — the digest never spams.

Why server-side aggregation rather than pre-rendered Jinja: HTML output
in Convioo is hand-rolled (see ``_wrap_html`` in ``email_sender.py``)
to keep transactional and notification emails on the same look. Jinja
would pull in a template engine just for one report.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# We reuse the shared HTML shell + button helpers from email_sender so
# every Convioo email looks the same. They're prefixed with an
# underscore because they're not part of the public surface, but the
# digest renderer is conceptually one such email — happy to share the
# template.
from leadgen.core.services.email_sender import (
    _button_html,
    _wrap_html,
    send_email,
)
from leadgen.core.services.notification_prefs import (
    list_users_with_digest_enabled,
)
from leadgen.db.models import Lead, LeadActivity, User

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DigestSummary:
    new_leads: int
    hot_leads: int
    replies: int

    def is_empty(self) -> bool:
        return (
            self.new_leads == 0
            and self.hot_leads == 0
            and self.replies == 0
        )


async def build_summary(
    session: AsyncSession,
    user_id: int,
    *,
    since: datetime,
) -> DigestSummary:
    """Count the three numbers we put in the email — nothing else.

    ``Lead`` has no direct user_id column; ownership lives on the parent
    ``SearchQuery``. The JOIN keeps lead-level filters scoped to one
    user without a separate denormalised column.
    """
    from leadgen.db.models import SearchQuery

    rows = (
        await session.execute(
            select(Lead)
            .join(SearchQuery, SearchQuery.id == Lead.query_id)
            .where(Lead.created_at >= since)
            .where(Lead.deleted_at.is_(None))
            .where(SearchQuery.user_id == user_id)
        )
    ).scalars().all()
    new_leads = list(rows)
    hot = sum(1 for lead in new_leads if (lead.score_ai or 0) >= 75)
    replies = (
        await session.execute(
            select(LeadActivity)
            .where(LeadActivity.user_id == user_id)
            .where(LeadActivity.kind == "email_replied")
            .where(LeadActivity.created_at >= since)
        )
    ).scalars().all()
    return DigestSummary(
        new_leads=len(new_leads),
        hot_leads=hot,
        replies=len(replies),
    )


def render_digest_email(
    *,
    name: str,
    summary: DigestSummary,
    app_url: str,
) -> tuple[str, str]:
    """Return ``(html, text)`` for the daily digest body."""
    leads_url = f"{app_url.rstrip('/')}/app/leads"
    text = (
        f"Привет, {name}!\n\n"
        f"За сутки в Convioo:\n"
        f"  • Новых лидов: {summary.new_leads}\n"
        f"  • Из них горячих (score ≥ 75): {summary.hot_leads}\n"
        f"  • Ответов на исходящие письма: {summary.replies}\n\n"
        f"Открыть CRM: {leads_url}\n\n"
        "— Convioo. Отписаться можно в Settings → Уведомления."
    )
    rows = "".join(
        f'<li style="margin: 4px 0;">{label}: <strong>{value}</strong></li>'
        for label, value in (
            ("Новых лидов", summary.new_leads),
            ("Горячих (score ≥ 75)", summary.hot_leads),
            ("Ответов в почте", summary.replies),
        )
    )
    body = (
        '<p style="color:#475569; line-height:1.55; font-size:14.5px;">'
        f"Привет, {name}! Вот короткая сводка за последние 24 часа:</p>"
        f'<ul style="font-size:14px; color:#1f2937; padding-left:20px;">{rows}</ul>'
        + _button_html(href=leads_url, label="Открыть CRM")
        + '<p style="font-size:12px; color:#94a3b8; margin-top:24px;">'
        "Этот дайджест отправлен потому что вы включили его в Settings → "
        "Уведомления. Снять галочку можно там же.</p>"
    )
    return _wrap_html(heading="Сводка за сутки", body_html=body), text


async def send_digest_for_user(
    session: AsyncSession,
    user: User,
    *,
    since: datetime,
    app_url: str,
) -> bool:
    """Build and send a digest for one user. Returns True iff sent.

    Skips silently when:
    * the user has no email (shouldn't happen post-verification)
    * there's nothing to report (all three counters are zero)

    The "nothing to report" branch is intentional — daily-digest emails
    that say "0 new leads" condition users to mute the channel after
    a week of empty days.
    """
    if not user.email:
        return False
    summary = await build_summary(
        session, user_id=user.id, since=since
    )
    if summary.is_empty():
        return False
    html, text = render_digest_email(
        name=user.first_name or user.email.split("@")[0],
        summary=summary,
        app_url=app_url,
    )
    await send_email(
        to=user.email,
        subject="Convioo — сводка за сутки",
        html=html,
        text=text,
    )
    return True


async def run_daily_digest_for_all_users(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    app_url: str,
) -> int:
    """Iterate every opted-in user. Returns the number of digests sent.

    The cron caller decides ``now`` so tests can pin time without
    monkeypatching ``datetime`` everywhere.
    """
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=24)
    users = await list_users_with_digest_enabled(session)
    sent = 0
    for user in users:
        try:
            if await send_digest_for_user(
                session, user, since=since, app_url=app_url
            ):
                sent += 1
        except Exception as exc:
            # One failing user mustn't block the rest of the batch.
            logger.warning(
                "digest: send failed user_id=%s err=%s", user.id, exc
            )
    return sent
