"""Экономика запусков: полная стоимость и сколько из неё сгорело.

Токены команда платит только за выданных лидов. Но платформа тратит
деньги на каждый прогон: на поиск по карте, на дубли, на отсеянных и
на неудачные запуски. Здесь из журнала трат (``cost_events``) и
воронки запуска собирается честная картина:

* **полная стоимость** — всё, что потрачено на запуск;
* **на результат** — то, что привело к выданным лидам;
* **сгорело** — то, за что ничего не получили, с причиной.

Как делится сгоревшее, если что-то выдано (оценка, а не учёт по
каждой компании): расходы поиска по карте делятся пропорционально
судьбе найденных компаний (дубли, ваши фильтры, язык, лишние сверх
лимита, выданные); расходы досье — пропорционально выданным и
исключённым ИИ. Если не выдано ничего — сгорело всё.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.db.models import CostEvent, SearchQuery

#: Этапы, которые относятся к поиску по карте (общие на весь запуск).
DISCOVERY_STAGES = {"discovery", None}
#: Причины «сгорело» в порядке показа.
WASTE_REASONS = ("duplicates", "prefiltered", "language", "over_limit", "excluded", "nothing_found", "failed")


async def _costs_for_search(session: AsyncSession, search_id: uuid.UUID) -> list[tuple[str, str | None, float]]:
    rows = (
        await session.execute(
            select(CostEvent.service, CostEvent.stage, func.sum(CostEvent.cost_usd))
            .where(CostEvent.search_id == search_id)
            .group_by(CostEvent.service, CostEvent.stage)
        )
    ).all()
    return [(s, st, float(c or 0)) for s, st, c in rows]


async def compute_search_economics(
    session: AsyncSession, query: SearchQuery, funnel: dict[str, int] | None
) -> dict[str, Any]:
    """Экономика одного запуска; пишется в ``search_queries.economics``."""
    funnel = dict(funnel or (query.economics or {}).get("funnel") or {})
    costs = await _costs_for_search(session, query.id)
    total = round(sum(c for _s, _st, c in costs), 6)
    by_service: dict[str, float] = {}
    by_stage: dict[str, float] = {}
    discovery = 0.0
    for service, stage, cost in costs:
        by_service[service] = round(by_service.get(service, 0.0) + cost, 6)
        key = stage or "discovery"
        by_stage[key] = round(by_stage.get(key, 0.0) + cost, 6)
        if stage in DISCOVERY_STAGES:
            discovery += cost
    per_lead = max(0.0, total - discovery - by_stage.get("insights", 0.0))

    delivered = int(funnel.get("delivered", query.leads_count or 0) if query.status == "done" else 0)
    wasted: dict[str, float] = {}
    if delivered <= 0:
        reason = "failed" if query.status == "failed" else (
            "duplicates" if funnel.get("duplicates") else "nothing_found"
        )
        wasted[reason] = total
    else:
        found = max(1, int(funnel.get("found", 0)))
        for reason in ("duplicates", "prefiltered", "language", "over_limit"):
            n = int(funnel.get(reason, 0))
            if n:
                wasted[reason] = discovery * n / found
        excluded = int(funnel.get("excluded", 0))
        if excluded:
            wasted["excluded"] = per_lead * excluded / (delivered + excluded)
    wasted = {k: round(v, 6) for k, v in wasted.items() if v > 0}
    wasted_total = round(sum(wasted.values()), 6)
    return {
        "funnel": funnel,
        "requested": query.max_results,
        "delivered": delivered,
        "cost_usd": total,
        "useful_usd": round(total - wasted_total, 6),
        "wasted_usd": wasted_total,
        "wasted_by_reason": wasted,
        "cost_by_service": by_service,
        "cost_by_stage": by_stage,
        "cost_per_delivered_usd": round(total / delivered, 6) if delivered else None,
    }


async def team_economics(
    session: AsyncSession, team_id: uuid.UUID, since: datetime
) -> dict[str, Any]:
    """Сводка за период: все траты команды (поиски и не только),
    полезное и сгоревшее, лиды и себестоимость «под ключ»."""
    by_service_rows = (
        await session.execute(
            select(CostEvent.service, func.sum(CostEvent.cost_usd), func.sum(CostEvent.units))
            .where(CostEvent.team_id == team_id)
            .where(CostEvent.created_at >= since)
            .group_by(CostEvent.service)
        )
    ).all()
    by_stage_rows = (
        await session.execute(
            select(CostEvent.stage, func.sum(CostEvent.cost_usd))
            .where(CostEvent.team_id == team_id)
            .where(CostEvent.created_at >= since)
            .group_by(CostEvent.stage)
        )
    ).all()
    total = round(sum(float(c or 0) for _s, c, _u in by_service_rows), 4)
    searches = (
        await session.execute(
            select(SearchQuery)
            .where(SearchQuery.team_id == team_id)
            .where(SearchQuery.created_at >= since)
            .order_by(SearchQuery.created_at.desc())
        )
    ).scalars().all()

    wasted: dict[str, float] = {}
    search_cost = 0.0
    delivered = 0
    rows = []
    for q in searches:
        eco = q.economics or {}
        search_cost += float(eco.get("cost_usd") or 0)
        delivered += int(eco.get("delivered") or 0)
        for k, v in (eco.get("wasted_by_reason") or {}).items():
            wasted[k] = wasted.get(k, 0.0) + float(v)
        rows.append(
            {
                "id": str(q.id),
                "niche": q.niche,
                "region": q.region,
                "status": q.status,
                "created_at": q.created_at.isoformat() if q.created_at else None,
                "requested": q.max_results,
                "delivered": int(eco.get("delivered") or (q.leads_count if q.status == "done" else 0) or 0),
                "funnel": eco.get("funnel") or {},
                "cost_usd": eco.get("cost_usd"),
                "wasted_usd": eco.get("wasted_usd"),
            }
        )
    wasted_total = round(sum(wasted.values()), 4)
    return {
        "since": since.isoformat(),
        "total_usd": total,
        "search_usd": round(search_cost, 4),
        "other_usd": round(max(0.0, total - search_cost), 4),
        "useful_usd": round(search_cost - wasted_total, 4),
        "wasted_usd": wasted_total,
        "wasted_by_reason": {k: round(v, 4) for k, v in wasted.items()},
        "delivered": delivered,
        # «Под ключ»: все траты на добычу, включая сгоревшее, на одного
        # выданного лида.
        "all_in_per_lead_usd": round(search_cost / delivered, 4) if delivered else None,
        "by_service": [
            {"service": s, "cost_usd": round(float(c or 0), 4), "units": float(u or 0)}
            for s, c, u in sorted(by_service_rows, key=lambda r: -(r[1] or 0))
        ],
        "by_stage": {(st or "other"): round(float(c or 0), 4) for st, c in by_stage_rows},
        "searches": rows[:50],
    }
