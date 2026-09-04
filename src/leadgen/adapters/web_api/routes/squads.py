"""``/api/v1/teams/{id}/squads`` — команды внутри компании.

Управляют РОП и владелец (``can_manage_members``). Назначение
тимлида автоматически привязывает его к команде; удаление команды
отпускает людей в общий пул (FK SET NULL), лиды не трогаются.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.routes._helpers import membership
from leadgen.core.services import team_journal
from leadgen.core.services.team_permissions import can_manage_members
from leadgen.db.models import TeamMembership, TeamSquad, User
from leadgen.db.models.journal import (
    JK_SQUAD_CREATED,
    JK_SQUAD_DELETED,
    JK_SQUAD_UPDATED,
)
from leadgen.db.session import session_factory

router = APIRouter(tags=["squads"])


class SquadOut(BaseModel):
    id: uuid.UUID
    name: str
    lead_user_id: int | None
    lead_name: str | None = None
    member_count: int = 0
    created_at: datetime


class SquadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    lead_user_id: int | None = None


class SquadUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    lead_user_id: int | None = None


class SquadListResponse(BaseModel):
    squads: list[SquadOut]


async def _require_admin(session, team_id: uuid.UUID, user_id: int):
    ms = await membership(session, team_id, user_id)
    if ms is None or not can_manage_members(ms.role):
        raise HTTPException(
            status_code=403,
            detail="only the owner or head of sales manages squads",
        )
    return ms


async def _squad_out(session, squad: TeamSquad) -> SquadOut:
    count = (
        await session.execute(
            select(func.count(TeamMembership.id)).where(
                TeamMembership.squad_id == squad.id
            )
        )
    ).scalar_one()
    lead_name = None
    if squad.lead_user_id is not None:
        lead = await session.get(User, squad.lead_user_id)
        if lead is not None:
            lead_name = lead.display_name or lead.email
    return SquadOut(
        id=squad.id,
        name=squad.name,
        lead_user_id=squad.lead_user_id,
        lead_name=lead_name,
        member_count=int(count),
        created_at=squad.created_at,
    )


@router.get(
    "/api/v1/teams/{team_id}/squads", response_model=SquadListResponse
)
async def list_squads(
    team_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> SquadListResponse:
    """Список команд — любому участнику компании: селзу тоже видно,
    в какой он команде."""
    async with session_factory() as session:
        ms = await membership(session, team_id, current_user.id)
        if ms is None:
            raise HTTPException(status_code=403, detail="not a team member")
        squads = (
            (
                await session.execute(
                    select(TeamSquad)
                    .where(TeamSquad.team_id == team_id)
                    .order_by(TeamSquad.created_at)
                )
            )
            .scalars()
            .all()
        )
        return SquadListResponse(
            squads=[await _squad_out(session, sq) for sq in squads]
        )


@router.post(
    "/api/v1/teams/{team_id}/squads", response_model=SquadOut
)
async def create_squad(
    team_id: uuid.UUID,
    body: SquadCreate,
    current_user: User = Depends(get_current_user),
) -> SquadOut:
    async with session_factory() as session:
        ms = await _require_admin(session, team_id, current_user.id)
        dup = (
            await session.execute(
                select(TeamSquad.id)
                .where(TeamSquad.team_id == team_id)
                .where(TeamSquad.name == body.name.strip())
                .limit(1)
            )
        ).scalar_one_or_none()
        if dup is not None:
            raise HTTPException(
                status_code=409, detail="a squad with this name exists"
            )
        lead_ms = None
        if body.lead_user_id is not None:
            lead_ms = await membership(session, team_id, body.lead_user_id)
            if lead_ms is None:
                raise HTTPException(
                    status_code=400,
                    detail="lead_user_id must be a team member",
                )
        squad = TeamSquad(
            team_id=team_id,
            name=body.name.strip(),
            lead_user_id=body.lead_user_id,
        )
        session.add(squad)
        await session.flush()
        # Тимлид принадлежит своей команде — привязываем сразу.
        if lead_ms is not None:
            lead_ms.squad_id = squad.id
        await team_journal.record(
            session,
            team_id,
            JK_SQUAD_CREATED,
            actor=current_user,
            actor_role=ms.role,
            payload={"name": squad.name},
        )
        await session.commit()
        return await _squad_out(session, squad)


async def _load_admin_squad(
    session, squad_id: uuid.UUID, user_id: int
) -> tuple[TeamSquad, TeamMembership]:
    squad = await session.get(TeamSquad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="squad not found")
    ms = await _require_admin(session, squad.team_id, user_id)
    return squad, ms


@router.patch("/api/v1/squads/{squad_id}", response_model=SquadOut)
async def update_squad(
    squad_id: uuid.UUID,
    body: SquadUpdate,
    current_user: User = Depends(get_current_user),
) -> SquadOut:
    async with session_factory() as session:
        squad, ms = await _load_admin_squad(session, squad_id, current_user.id)
        data = body.model_dump(exclude_unset=True)
        if "name" in data and body.name:
            squad.name = body.name.strip()
        if "lead_user_id" in data:
            if body.lead_user_id is not None:
                lead_ms = await membership(
                    session, squad.team_id, body.lead_user_id
                )
                if lead_ms is None:
                    raise HTTPException(
                        status_code=400,
                        detail="lead_user_id must be a team member",
                    )
                lead_ms.squad_id = squad.id
            squad.lead_user_id = body.lead_user_id
        await team_journal.record(
            session,
            squad.team_id,
            JK_SQUAD_UPDATED,
            actor=current_user,
            actor_role=ms.role,
            payload={"name": squad.name},
        )
        await session.commit()
        return await _squad_out(session, squad)


@router.delete("/api/v1/squads/{squad_id}")
async def delete_squad(
    squad_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    """Распустить команду: люди уходят в общий пул, лиды остаются
    за теми, кто их вёл."""
    async with session_factory() as session:
        squad, ms = await _load_admin_squad(session, squad_id, current_user.id)
        # SET NULL сработает и сам, но SQLite в тестах без FK-каскадов
        # надёжнее отвязать явно.
        members = (
            (
                await session.execute(
                    select(TeamMembership).where(
                        TeamMembership.squad_id == squad.id
                    )
                )
            )
            .scalars()
            .all()
        )
        for m in members:
            m.squad_id = None
        await team_journal.record(
            session,
            squad.team_id,
            JK_SQUAD_DELETED,
            actor=current_user,
            actor_role=ms.role,
            payload={"name": squad.name},
        )
        await session.delete(squad)
        await session.commit()
    return {"ok": True}
