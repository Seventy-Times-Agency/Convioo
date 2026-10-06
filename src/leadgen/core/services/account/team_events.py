"""Team event notifications (Wave 1, задача 9).

Only events that REQUIRE action reach a human — no noise:

* горячий ответ → селзу мгновенно, с черновиком ответа;
* цель достигнута → менеджерам отдела;
* пакет назначен → селзу;
* просроченный перезвон → селзу; сильно просроченный → эскалация
  менеджеру (cron);
* вечерняя сводка отдела → менеджерам, утренняя → владельцу (cron);
* потолок затрат 80% → владельцу (живёт в cost_control).

Every event lands in the in-app feed (the bell, see
``notification_feed``); a linked Telegram gets a copy, and urgent ones
are emailed to people who are away. Delivery never breaks the flow
that raised the event.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.core.services.account.team_permissions import normalize_role
from leadgen.core.services.sales.funnel_engine import on_email_step
from leadgen.db.models import (
    Funnel,
    Lead,
    LeadActivity,
    SearchQuery,
    TeamMembership,
)

logger = logging.getLogger(__name__)

# Callback overdue thresholds.
OVERDUE_AFTER = timedelta(hours=2)      # rep is nudged
ESCALATE_AFTER = timedelta(hours=24)    # manager is told


async def notify_user(
    session: AsyncSession,
    user_id: int,
    *,
    kind: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    team_id=None,
    important: bool = False,
    urgent: bool = False,
) -> bool:
    """One person: in-app feed + Telegram copy (+ email when urgent and
    away). ``session`` is unused but kept so callers stay uniform."""
    from leadgen.core.services.account.notification_feed import notify

    return await notify(
        user_id,
        kind=kind,
        title=title,
        body=body,
        link=link,
        team_id=team_id,
        important=important,
        urgent=urgent,
    )


async def notify_roles(
    session: AsyncSession, team_id, roles: set[str], **event
) -> int:
    """Everyone in the team whose canonical role ∈ roles."""
    rows = (
        (
            await session.execute(
                select(TeamMembership).where(
                    TeamMembership.team_id == team_id
                )
            )
        )
        .scalars()
        .all()
    )
    sent = 0
    for ms in rows:
        if normalize_role(ms.role) in roles and await notify_user(
            session, ms.user_id, team_id=team_id, **event
        ):
            sent += 1
    return sent


# ── point events ───────────────────────────────────────────────────────


async def hot_reply(
    session: AsyncSession,
    *,
    lead: Lead,
    team_id,
    summary: str | None,
    suggested_reply: str | None,
) -> None:
    """Горячий ответ → селзу мгновенно, с черновиком."""
    rep_id = lead.owner_user_id
    if rep_id is None:
        return
    draft = (suggested_reply or "").strip()
    if len(draft) > 400:
        draft = draft[:400] + "…"
    body = (summary or "").strip()[:200]
    if draft:
        body = f"{body}\n\nЧерновик ответа:\n{draft}".strip()
    await notify_user(
        session,
        rep_id,
        kind="hot_reply",
        title=f"Горячий ответ: {lead.name}",
        body=body or None,
        link="/app/work/letters",
        team_id=team_id,
        urgent=True,
    )


async def goal_reached(
    session: AsyncSession,
    *,
    lead: Lead,
    team_id,
    funnel: Funnel | None,
    rep_name: str | None,
) -> None:
    """Цель достигнута → менеджерам (владелец видит в утренней сводке)."""
    goal = funnel.goal_name if funnel is not None else "цель"
    body = f"{rep_name} закрыл цель воронки" if rep_name else None
    if funnel is not None and funnel.goal_price is not None:
        body = f"{body or 'Цель воронки'} · ${float(funnel.goal_price):.0f}"
    await notify_roles(
        session,
        team_id,
        {"manager", "admin", "owner"},
        kind="goal",
        title=f"Цель: {lead.name} — {goal}",
        body=body,
        link=f"/app/leads?lead={lead.id}",
    )


async def batch_assigned(
    session: AsyncSession,
    *,
    team_id,
    rep_id: int,
    count: int,
    funnel_name: str,
) -> None:
    """Пакет назначен → селзу."""
    await notify_user(
        session,
        rep_id,
        kind="batch",
        title=f"Вам раздали {count} лидов",
        body=f"Воронка «{funnel_name}». Очередь обновлена в «Работе».",
        link="/app/work",
        team_id=team_id,
        important=True,
    )


# ── crons (called from the worker) ─────────────────────────────────────


async def process_overdue_callbacks(
    session: AsyncSession, *, now: datetime | None = None
) -> dict[str, int]:
    """Просроченные перезвоны: селзу — напоминание, менеджеру —
    эскалация после суток. Каждый лид дёргается один раз на стадию
    (флаг в extra-активити не нужен — окно между порогами)."""
    current = now or datetime.now(timezone.utc)
    nudged = 0
    escalated = 0

    rows = (
        (
            await session.execute(
                select(Lead, SearchQuery.team_id)
                .join(SearchQuery, SearchQuery.id == Lead.query_id)
                .where(SearchQuery.team_id.is_not(None))
                .where(Lead.owner_user_id.is_not(None))
                .where(Lead.deleted_at.is_(None))
                .where(Lead.goal_reached_at.is_(None))
                .where(Lead.next_touch_at.is_not(None))
                .where(Lead.next_touch_at <= current - OVERDUE_AFTER)
                .where(~on_email_step())
                .limit(300)
            )
        )
        .all()
    )

    # Group per rep / per team so one person gets ONE message, not
    # thirty. Только события, требующие действия, — без шума.
    per_rep: dict[int, list[str]] = {}
    rep_team: dict[int, object] = {}
    per_team_escalations: dict[str, list[str]] = {}
    for lead, team_id in rows:
        due = lead.next_touch_at
        if due is not None and due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        overdue_for = current - (due or current)
        if overdue_for >= ESCALATE_AFTER:
            per_team_escalations.setdefault(str(team_id), []).append(
                lead.name
            )
        else:
            per_rep.setdefault(lead.owner_user_id, []).append(lead.name)
            rep_team[lead.owner_user_id] = team_id

    for rep_id, names in per_rep.items():
        listing = ", ".join(names[:5]) + ("…" if len(names) > 5 else "")
        if await notify_user(
            session,
            rep_id,
            kind="overdue",
            title=f"Просрочены перезвоны: {len(names)}",
            body=f"{listing}. Они первыми в очереди «Работы».",
            link="/app/work",
            team_id=rep_team.get(rep_id),
            urgent=True,
        ):
            nudged += 1

    teams_seen: set[str] = set()
    for _lead, team_id in rows:
        key = str(team_id)
        if key in teams_seen or key not in per_team_escalations:
            continue
        teams_seen.add(key)
        names = per_team_escalations[key]
        if not names:
            continue
        listing = ", ".join(names[:5]) + ("…" if len(names) > 5 else "")
        escalated += await notify_roles(
            session,
            team_id,
            {"manager", "admin"},
            kind="escalation",
            title=f"Перезвоны просрочены больше суток: {len(names)}",
            body=listing,
            link="/app/work",
            important=True,
        )

    return {"nudged": nudged, "escalated": escalated}


async def _team_day_stats(
    session: AsyncSession, team_id, since: datetime
) -> dict[str, int]:
    calls = int(
        (
            await session.execute(
                select(func.count(LeadActivity.id))
                .where(LeadActivity.team_id == team_id)
                .where(LeadActivity.kind == "call")
                .where(LeadActivity.created_at >= since)
            )
        ).scalar()
        or 0
    )
    goals = int(
        (
            await session.execute(
                select(func.count(Lead.id))
                .join(SearchQuery, SearchQuery.id == Lead.query_id)
                .where(SearchQuery.team_id == team_id)
                .where(Lead.goal_reached_at >= since)
            )
        ).scalar()
        or 0
    )
    assigned = int(
        (
            await session.execute(
                select(func.count(LeadActivity.id))
                .where(LeadActivity.team_id == team_id)
                .where(LeadActivity.kind == "assigned")
                .where(LeadActivity.created_at >= since)
            )
        ).scalar()
        or 0
    )
    overdue = int(
        (
            await session.execute(
                select(func.count(Lead.id))
                .join(SearchQuery, SearchQuery.id == Lead.query_id)
                .where(SearchQuery.team_id == team_id)
                .where(Lead.owner_user_id.is_not(None))
                .where(Lead.deleted_at.is_(None))
                .where(Lead.goal_reached_at.is_(None))
                .where(Lead.next_touch_at.is_not(None))
                .where(
                    Lead.next_touch_at
                    <= datetime.now(timezone.utc) - OVERDUE_AFTER
                )
                .where(~on_email_step())
            )
        ).scalar()
        or 0
    )
    return {
        "calls": calls,
        "goals": goals,
        "assigned": assigned,
        "overdue": overdue,
    }


def _digest_text(stats: dict[str, int]) -> str:
    return (
        f"Звонки-исходы: {stats['calls']} · цели: {stats['goals']} · "
        f"назначено лидов: {stats['assigned']} · "
        f"просроченных перезвонов: {stats['overdue']}"
    )


async def send_team_digests(
    session: AsyncSession, *, audience: str, now: datetime | None = None
) -> int:
    """Дневные сводки: ``audience`` = "managers" (вечер) или
    "owners" (утро, за прошедшие сутки)."""
    current = now or datetime.now(timezone.utc)
    since = current - timedelta(hours=24)
    team_ids = (
        (
            await session.execute(
                select(TeamMembership.team_id).distinct()
            )
        )
        .scalars()
        .all()
    )
    sent = 0
    for team_id in team_ids:
        stats = await _team_day_stats(session, team_id, since)
        if not any(stats.values()):
            continue  # тихий день — не шумим
        if audience == "managers":
            sent += await notify_roles(
                session,
                team_id,
                {"manager", "admin"},
                kind="digest",
                title="Вечерняя сводка отдела",
                body=_digest_text(stats),
                link="/app/team/analytics",
            )
        else:
            sent += await notify_roles(
                session,
                team_id,
                {"owner"},
                kind="digest",
                title="Утренняя сводка за сутки",
                body=_digest_text(stats),
                link="/app/team/analytics",
            )
    return sent
