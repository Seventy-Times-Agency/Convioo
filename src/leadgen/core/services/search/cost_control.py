"""Team cost control (Wave 1, задача 7).

Aggregates the per-user usage the tracker already records into a
team month total and exposes the per-lead unit economics — a cost
report. Launches are gated by the team's tokens (``budget``), not by
dollars.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.core.services.search import usage_tracker
from leadgen.db.models import Team, TeamMembership

logger = logging.getLogger(__name__)

# Цена токена (1 токен = 1 лид). Зафиксирована числом, а не выводится
# из цен сервисов: от неё зависят бюджеты команд, и менять её — решение
# владельца, а не побочный эффект правки прайса в учёте трат. Реальная
# себестоимость лида теперь видна по журналу трат (cost_events).
COST_PER_ENRICHED_LEAD_USD: float = 0.0473

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


@dataclass(slots=True)
class PersonalCostStatus:
    month_cost_usd: float
    cap_usd: float | None
    blocked: bool


async def get_personal_cost_status(user_id: int | str) -> PersonalCostStatus:
    """Потолок личного пространства — тот же учёт, но лимит платформы.

    Командные поиски ограничивает владелец своим потолком; личные без
    этой проверки не ограничивал никто — переключение в «Личное»
    обходило контроль затрат целиком. Лимит задаёт платформа через
    ``PERSONAL_MONTHLY_COST_CAP_USD`` (0 — выключен).
    """
    from leadgen.config import get_settings

    cap = float(get_settings().personal_monthly_cost_cap_usd or 0)
    month = 0.0
    try:
        summary = await usage_tracker.get_user_usage(user_id, window="month")
        month = summary.total_cost_usd
    except Exception:  # noqa: BLE001 — телеметрия не блокирует запуск
        logger.warning("personal cost status failed", exc_info=True)
    return PersonalCostStatus(
        month_cost_usd=round(month, 2),
        cap_usd=cap if cap > 0 else None,
        blocked=cap > 0 and month >= cap,
    )
