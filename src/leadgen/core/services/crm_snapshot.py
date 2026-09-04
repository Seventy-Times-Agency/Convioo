"""Живое состояние CRM для Henry.

Раньше ассистент знал состав команды и «кто мы», но не видел, что
происходит прямо сейчас — и на вопрос «как у нас дела» мог только
рассуждать. Этот снимок собирается в момент сообщения и режется по
той же ролевой линзе, что и экраны: селз видит своё, тимлид — свою
команду и свободный пул, РОП и владелец — всю компанию. ИИ не
получает ничего, чего этот человек не увидел бы в интерфейсе.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.core.services.squads import visible_member_ids
from leadgen.core.services.team_permissions import is_sales
from leadgen.db.models import (
    Lead,
    LeadActivity,
    SearchQuery,
    Team,
    TeamMembership,
)

HOT_SCORE = 75


async def build(
    session: AsyncSession, team_id: uuid.UUID, user_id: int
) -> dict[str, Any] | None:
    """Снимок CRM для ассистента, или None вне команды."""
    ms = (
        await session.execute(
            select(TeamMembership)
            .where(TeamMembership.team_id == team_id)
            .where(TeamMembership.user_id == user_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if ms is None:
        return None

    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    base = (
        select(Lead)
        .join(SearchQuery, SearchQuery.id == Lead.query_id)
        .where(SearchQuery.team_id == team_id)
        .where(Lead.deleted_at.is_(None))
        .where(Lead.archived_at.is_(None))
    )
    scope = "company"
    if is_sales(ms.role):
        scope = "own"
        base = base.where(Lead.owner_user_id == user_id)
    else:
        scope_ids = await visible_member_ids(session, team_id, user_id)
        if scope_ids is not None:
            scope = "squad"
            base = base.where(
                Lead.owner_user_id.in_(scope_ids)
                | Lead.owner_user_id.is_(None)
            )

    leads = (await session.execute(base)).scalars().all()
    active = [lead for lead in leads if lead.goal_reached_at is None]

    def _aware(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    overdue = sum(
        1
        for lead in active
        if lead.next_touch_at is not None
        and _aware(lead.next_touch_at) <= now
    )
    hot = sorted(
        (
            lead
            for lead in active
            if (lead.score_ai or 0) >= HOT_SCORE
        ),
        key=lambda lead: -(lead.score_ai or 0),
    )

    # Звонки сегодня — по той же линзе: чьи активности видим, тех и
    # считаем (селз — свои, тимлид — команды, РОП — все).
    acts_stmt = (
        select(LeadActivity)
        .where(LeadActivity.team_id == team_id)
        .where(LeadActivity.kind == "call")
        .where(LeadActivity.created_at >= day_start)
    )
    if scope == "own":
        acts_stmt = acts_stmt.where(LeadActivity.user_id == user_id)
    elif scope == "squad":
        acts_stmt = acts_stmt.where(
            LeadActivity.user_id.in_(scope_ids)
        )
    acts = (await session.execute(acts_stmt)).scalars().all()
    goals_today = sum(
        1 for a in acts if (a.payload or {}).get("outcome") == "goal"
    )

    running = (
        (
            await session.execute(
                select(SearchQuery)
                .where(SearchQuery.team_id == team_id)
                .where(SearchQuery.status.in_(["pending", "running"]))
                .limit(3)
            )
        )
        .scalars()
        .all()
    )

    team = await session.get(Team, team_id)

    return {
        "as_of": now.isoformat(timespec="minutes"),
        "scope": scope,
        "total": len(leads),
        "free": sum(1 for lead in leads if lead.owner_user_id is None),
        "in_work": sum(
            1 for lead in leads if lead.owner_user_id is not None
        ),
        "hot": len(hot),
        "top_hot": [
            {"name": lead.name, "score": int(lead.score_ai or 0)}
            for lead in hot[:3]
        ],
        "overdue_callbacks": overdue,
        "dials_today": len(acts),
        "goals_today": goals_today,
        "running_searches": [
            f"{q.niche} · {q.region}" for q in running
        ],
        "token_balance": int(getattr(team, "token_balance", 0) or 0),
    }
