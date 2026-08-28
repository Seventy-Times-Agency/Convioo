"""Team event notifications → Telegram (Wave 1, задача 9).

Only events that REQUIRE action reach a human — no noise:

* горячий ответ → селзу мгновенно, с черновиком ответа;
* цель достигнута → менеджерам отдела;
* пакет назначен → селзу;
* просроченный перезвон → селзу; сильно просроченный → эскалация
  менеджеру (cron);
* вечерняя сводка отдела → менеджерам, утренняя → владельцу (cron);
* потолок затрат 80% → владельцу (живёт в cost_control).

Delivery is fire-and-forget through the linked Telegram account;
users without a linked chat are silently skipped, and a Telegram
failure never breaks the flow that raised the event.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.core.services.team_permissions import normalize_role
from leadgen.db.models import (
    Funnel,
    Lead,
    LeadActivity,
    SearchQuery,
    TeamMembership,
    TelegramConnection,
)

logger = logging.getLogger(__name__)

# Callback overdue thresholds.
OVERDUE_AFTER = timedelta(hours=2)      # rep is nudged
ESCALATE_AFTER = timedelta(hours=24)    # manager is told


async def notify_user(
    session: AsyncSession, user_id: int, text: str
) -> bool:
    """Send ``text`` to one user's linked Telegram. False when the
    user has no link or the send failed — never raises."""
    conn = (
        await session.execute(
            select(TelegramConnection).where(
                TelegramConnection.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if conn is None:
        return False
    try:
        from leadgen.adapters.telegram_v2.api import send_message

        await send_message(conn.chat_id, text)
        return True
    except Exception:  # noqa: BLE001 — уведомление не роняет поток
        logger.warning(
            "team_events.notify_user failed user=%s", user_id, exc_info=True
        )
        return False


async def notify_roles(
    session: AsyncSession, team_id, roles: set[str], text: str
) -> int:
    """Send ``text`` to every member whose canonical role ∈ roles."""
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
            session, ms.user_id, text
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
    text = f"🔥 Горячий ответ — {lead.name}"
    if summary:
        text += f"\n{summary.strip()[:200]}"
    if draft:
        text += f"\n\nЧерновик ответа:\n{draft}"
    await notify_user(session, rep_id, text)


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
    who = f" ({rep_name})" if rep_name else ""
    text = f"✅ {goal} — {lead.name}{who}"
    if funnel is not None and funnel.goal_price is not None:
        text += f" · ${float(funnel.goal_price):.0f}"
    await notify_roles(session, team_id, {"manager", "admin"}, text)


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
        f"📦 Вам назначен пакет: {count} лидов · воронка «{funnel_name}». "
        "Очередь обновлена в «Работе».",
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
                .limit(300)
            )
        )
        .all()
    )

    # Group per rep / per team so one person gets ONE message, not
    # thirty. Только события, требующие действия, — без шума.
    per_rep: dict[int, list[str]] = {}
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

    for rep_id, names in per_rep.items():
        listing = ", ".join(names[:5]) + ("…" if len(names) > 5 else "")
        if await notify_user(
            session,
            rep_id,
            f"⏰ Просроченные перезвоны: {len(names)} — {listing}. "
            "Они первыми в очереди «Работы».",
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
            f"🚨 Эскалация: перезвоны просрочены более суток "
            f"({len(names)}) — {listing}.",
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


def _digest_text(title: str, stats: dict[str, int]) -> str:
    return (
        f"{title}\n"
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
            text = _digest_text("🌆 Вечерняя сводка отдела", stats)
            sent += await notify_roles(
                session, team_id, {"manager", "admin"}, text
            )
        else:
            text = _digest_text("🌅 Утренняя сводка за сутки", stats)
            sent += await notify_roles(session, team_id, {"owner"}, text)
    return sent
