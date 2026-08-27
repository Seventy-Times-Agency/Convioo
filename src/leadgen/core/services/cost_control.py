"""Team cost control (Wave 1, задача 7).

Aggregates the per-user usage the tracker already records into a
team month total, exposes the per-lead unit economics, and enforces
the owner's monthly $ ceiling: 80% → one Telegram warning to the
owner per day, 100% → searches stop with a clear message.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.core.services import usage_tracker
from leadgen.core.services.usage_tracker import UNIT_COST_USD
from leadgen.db.models import Team, TeamMembership, TelegramConnection
from leadgen.utils import cache as _cache

logger = logging.getLogger(__name__)

# Себестоимость лида с полным досье — фиксируем расчёт по коду:
#   Place Details (with reviews) ....... $0.028
#   Text Search, амортизировано ~1/20 .. $0.00125
#   Claude Haiku на досье: ~8k in + ~1.2k out токенов
#     8_000 * $1/M + 1_200 * $5/M ...... $0.014
# Итого ≈ $0.043 на лид; округляем вверх до $0.047 (ретраи, кэш-промахи).
CLAUDE_TOKENS_PER_LEAD_IN = 8_000
CLAUDE_TOKENS_PER_LEAD_OUT = 1_200

COST_PER_ENRICHED_LEAD_USD: float = round(
    UNIT_COST_USD["google_place_details"]
    + UNIT_COST_USD["google_text_search"] / 20
    + CLAUDE_TOKENS_PER_LEAD_IN * UNIT_COST_USD["claude_input_tokens"]
    + CLAUDE_TOKENS_PER_LEAD_OUT * UNIT_COST_USD["claude_output_tokens"]
    + 0.004,  # retries / cache misses headroom
    4,
)

WARN_THRESHOLD = 0.8


@dataclass(slots=True)
class TeamCostStatus:
    team_id: str
    month_cost_usd: float
    cap_usd: float | None
    ratio: float | None  # None when no cap
    blocked: bool
    warning: bool
    cost_by_service: dict[str, float]


async def get_team_cost_status(
    session: AsyncSession, team_id
) -> TeamCostStatus:
    """Aggregate the rolling-30d spend of every member + cap state."""
    team = await session.get(Team, team_id)
    cap: Decimal | None = (
        team.monthly_cost_cap_usd if team is not None else None
    )
    member_ids = (
        (
            await session.execute(
                select(TeamMembership.user_id).where(
                    TeamMembership.team_id == team_id
                )
            )
        )
        .scalars()
        .all()
    )
    total = 0.0
    by_service: dict[str, float] = {}
    for uid in member_ids:
        try:
            summary = await usage_tracker.get_user_usage(uid, window="month")
        except Exception:  # noqa: BLE001 — telemetry must never break flow
            continue
        total += summary.total_cost_usd
        for service, cost in summary.cost_usd_by_service.items():
            by_service[service] = round(
                by_service.get(service, 0.0) + cost, 6
            )
    total = round(total, 4)
    cap_f = float(cap) if cap is not None else None
    ratio = (total / cap_f) if cap_f else None
    return TeamCostStatus(
        team_id=str(team_id),
        month_cost_usd=total,
        cap_usd=cap_f,
        ratio=ratio,
        blocked=bool(cap_f and total >= cap_f),
        warning=bool(cap_f and ratio is not None and ratio >= WARN_THRESHOLD),
        cost_by_service=by_service,
    )


def estimate_search_cost(expected_leads: int) -> float:
    """«~N лидов · ~$X» — pre-launch estimate for the Добыча screen."""
    return round(expected_leads * COST_PER_ENRICHED_LEAD_USD, 2)


async def maybe_warn_owner(
    session: AsyncSession, team_id, status: TeamCostStatus
) -> bool:
    """Send the 80% Telegram warning to the team owner — at most once
    per team per day. Returns True when a message was dispatched."""
    if not status.warning or status.blocked:
        return False
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    flag_key = f"costwarn:{team_id}:{day}"
    try:
        if await _cache.get_json("usage", flag_key):
            return False
    except Exception:  # noqa: BLE001
        pass

    owner_id = (
        await session.execute(
            select(TeamMembership.user_id)
            .where(TeamMembership.team_id == team_id)
            .where(TeamMembership.role == "owner")
            .limit(1)
        )
    ).scalar_one_or_none()
    if owner_id is None:
        return False
    conn = (
        await session.execute(
            select(TelegramConnection).where(
                TelegramConnection.user_id == owner_id
            )
        )
    ).scalar_one_or_none()
    if conn is None:
        return False
    try:
        from leadgen.adapters.telegram_v2.api import send_message

        pct = int(round((status.ratio or 0) * 100))
        await send_message(
            conn.chat_id,
            (
                f"⚠️ Затраты команды достигли {pct}% месячного потолка: "
                f"${status.month_cost_usd:.2f} из ${status.cap_usd:.2f}. "
                "При 100% запуск поисков остановится."
            ),
        )
        await _cache.set_json("usage", flag_key, 1, 24 * 60 * 60)
        return True
    except Exception:  # noqa: BLE001 — не роняем поиск из-за телеграма
        logger.warning("cost warning telegram failed", exc_info=True)
        return False
