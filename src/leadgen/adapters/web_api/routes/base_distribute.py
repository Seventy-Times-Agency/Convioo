"""``POST /teams/{id}/base/distribute`` — раздача сырья селзам.

Три режима одной ручки:

* ``auto`` — всё сырьё Базы, честной змейкой по скору;
* ``selected`` — выбранные лиды, той же змейкой;
* ``manual`` — выбранные лиды конкретному селзу.

Змейка: лиды сортируются по скору и раздаются по кругу туда-обратно
(1..N, N..1) — у каждого селза выравнивается и количество, и сумма
скора. Первым получает наименее загруженный. Воронка опциональна:
с ней лид входит в путь касаний, без неё просто встаёт в очередь.

Лид после раздачи ОСТАЁТСЯ в Базе с пометкой «у кого» — в CRM его
переносит первое касание, не раздача.
"""

from __future__ import annotations

import uuid
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.routes._helpers import membership
from leadgen.core.services import team_journal
from leadgen.core.services.funnel_engine import attach_lead
from leadgen.core.services.squads import visible_member_ids
from leadgen.core.services.team_permissions import (
    PERM_ASSIGN_LEADS,
    has_permission,
    is_sales,
    normalize_role,
)
from leadgen.db.models import (
    Funnel,
    Lead,
    LeadActivity,
    SearchQuery,
    TeamMembership,
    User,
)
from leadgen.db.models.journal import JK_BATCH_ASSIGNED
from leadgen.db.session import session_factory

router = APIRouter(tags=["base"])


class DistributeRequest(BaseModel):
    mode: str = Field(pattern="^(auto|selected|manual)$")
    lead_ids: list[uuid.UUID] | None = None
    #: Только для manual: кому именно.
    owner_user_id: int | None = None
    #: Опционально: воронка, в которую входят розданные лиды.
    funnel_id: uuid.UUID | None = None


class DistributeResponse(BaseModel):
    assigned: int
    #: Имя → сколько получил; фронт показывает раскладку.
    split: dict[str, int]


def snake_split(
    leads: list[Lead], rep_ids: list[int]
) -> dict[uuid.UUID, int]:
    """Честная змейка: по скору вниз, по кругу туда-обратно."""
    ordered = sorted(leads, key=lambda l: -(l.score_ai or 0))  # noqa: E741
    n = len(rep_ids)
    out: dict[uuid.UUID, int] = {}
    for i, lead in enumerate(ordered):
        lap, pos = divmod(i, n)
        rep = rep_ids[pos] if lap % 2 == 0 else rep_ids[n - 1 - pos]
        out[lead.id] = rep
    return out


@router.post(
    "/api/v1/teams/{team_id}/base/distribute",
    response_model=DistributeResponse,
)
async def distribute_base(
    team_id: uuid.UUID,
    body: DistributeRequest,
    current_user: User = Depends(get_current_user),
) -> DistributeResponse:
    async with session_factory() as session:
        ms = await membership(session, team_id, current_user.id)
        if ms is None or not has_permission(ms.role, PERM_ASSIGN_LEADS):
            raise HTTPException(
                status_code=403, detail="your role can't distribute leads"
            )
        scope_ids = await visible_member_ids(session, team_id, current_user.id)

        # Целевые селзы — в зоне видимости раздающего.
        members = (
            await session.execute(
                select(TeamMembership, User)
                .join(User, User.id == TeamMembership.user_id)
                .where(TeamMembership.team_id == team_id)
            )
        ).all()
        reps = [
            (mem, u)
            for mem, u in members
            if is_sales(mem.role)
            and (scope_ids is None or u.id in scope_ids)
        ]
        rep_name = {
            u.id: (u.display_name or u.first_name or f"#{u.id}")
            for _mem, u in reps
        }

        funnel: Funnel | None = None
        if body.funnel_id is not None:
            funnel = (
                await session.execute(
                    select(Funnel)
                    .where(Funnel.id == body.funnel_id)
                    .where(Funnel.team_id == team_id)
                    .options(selectinload(Funnel.steps))
                )
            ).scalar_one_or_none()
            if funnel is None:
                raise HTTPException(
                    status_code=400, detail="funnel not found in this team"
                )

        # Сырьё Базы: статус «Новый». Раздача не выносит из Базы —
        # выносит первое касание.
        stmt = (
            select(Lead)
            .join(SearchQuery, SearchQuery.id == Lead.query_id)
            .where(SearchQuery.team_id == team_id)
            .where(Lead.deleted_at.is_(None))
            .where(Lead.archived_at.is_(None))
            .where(Lead.lead_status == "new")
        )
        if body.mode == "auto":
            stmt = stmt.where(Lead.owner_user_id.is_(None))
        else:
            if not body.lead_ids:
                raise HTTPException(
                    status_code=400, detail="lead_ids is required"
                )
            stmt = stmt.where(Lead.id.in_(body.lead_ids))
        leads = list((await session.execute(stmt)).scalars())
        if not leads:
            return DistributeResponse(assigned=0, split={})

        if body.mode == "manual":
            if body.owner_user_id is None:
                raise HTTPException(
                    status_code=400,
                    detail="owner_user_id is required for manual mode",
                )
            target_ms = await membership(
                session, team_id, body.owner_user_id
            )
            if target_ms is None:
                raise HTTPException(
                    status_code=400,
                    detail="owner_user_id must be a team member",
                )
            target_user = await session.get(User, body.owner_user_id)
            assignment = {lead.id: body.owner_user_id for lead in leads}
            rep_name[body.owner_user_id] = (
                (target_user.display_name or target_user.email)
                if target_user is not None
                else str(body.owner_user_id)
            )
        else:
            if not reps:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "no sales reps to distribute to — invite reps "
                        "or assign them to your squad first"
                    ),
                )
            # Наименее загруженные получают первыми.
            load = Counter(
                (
                    await session.execute(
                        select(Lead.owner_user_id)
                        .join(
                            SearchQuery,
                            SearchQuery.id == Lead.query_id,
                        )
                        .where(SearchQuery.team_id == team_id)
                        .where(Lead.deleted_at.is_(None))
                        .where(Lead.owner_user_id.is_not(None))
                    )
                ).scalars()
            )
            rep_ids = sorted(
                (u.id for _mem, u in reps), key=lambda uid: load.get(uid, 0)
            )
            assignment = snake_split(leads, rep_ids)

        split: Counter[str] = Counter()
        for lead in leads:
            new_owner = assignment[lead.id]
            lead.owner_user_id = new_owner
            if funnel is not None:
                attach_lead(lead, funnel)
            split[rep_name.get(new_owner, str(new_owner))] += 1
            session.add(
                LeadActivity(
                    lead_id=lead.id,
                    user_id=current_user.id,
                    team_id=team_id,
                    kind="assigned",
                    payload={
                        "to": new_owner,
                        "mode": body.mode,
                        "funnel_id": (
                            str(funnel.id) if funnel is not None else None
                        ),
                    },
                )
            )

        await team_journal.record(
            session,
            team_id,
            JK_BATCH_ASSIGNED,
            actor=current_user,
            actor_role=normalize_role(ms.role),
            payload={
                "count": len(leads),
                "assignee": (
                    next(iter(split)) if len(split) == 1 else None
                ),
                "auto": body.mode == "auto",
                "split": ", ".join(
                    f"{name} — {n}" for name, n in split.most_common()
                ),
                "funnel": funnel.name if funnel is not None else None,
            },
        )
        await session.commit()
        return DistributeResponse(
            assigned=len(leads), split=dict(split)
        )
