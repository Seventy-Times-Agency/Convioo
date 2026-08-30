"""``/api/v1/teams/{team_id}/funnels*`` + ``/api/v1/funnels/*`` —
the funnel entity (Wave 1).

A funnel is the team's central sales object: touch path, goal
(free text + optional price + on-reach action), call script and
no-answer rule. Managing funnels is a manager+ capability; a sales
rep reads the funnel of a lead they work via
``GET /api/v1/leads/{lead_id}/funnel`` (registered here too) so the
green button and the touch path render from data, never code.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.routes._helpers import membership
from leadgen.core.services.funnel_engine import attach_lead
from leadgen.core.services.team_permissions import (
    PERM_ASSIGN_LEADS,
    PERM_MANAGE_FUNNELS,
    has_permission,
    is_sales,
)
from leadgen.db.models import (
    FUNNEL_STATUSES,
    GOAL_ACTIONS,
    STEP_KINDS,
    Funnel,
    FunnelStep,
    Lead,
    LeadActivity,
    SearchQuery,
    User,
)
from leadgen.db.session import session_factory

router = APIRouter(tags=["funnels"])


# ── schemas ────────────────────────────────────────────────────────────


class FunnelStepIn(BaseModel):
    kind: str
    day_offset: int = Field(default=0, ge=0, le=365)
    auto: bool = False
    template_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=300)


class FunnelStepOut(FunnelStepIn):
    id: uuid.UUID
    order_index: int


class FunnelCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    goal_name: str = Field(..., min_length=1, max_length=200)
    goal_price: float | None = Field(default=None, ge=0)
    goal_action: str = "none"
    script: str | None = None
    objections: list[dict[str, str]] | None = None
    status: str = "draft"
    no_answer_attempts: int = Field(default=3, ge=1, le=10)
    no_answer_pause_days: int = Field(default=14, ge=1, le=365)
    steps: list[FunnelStepIn] = Field(default_factory=list, max_length=30)


class FunnelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    goal_name: str | None = Field(default=None, min_length=1, max_length=200)
    goal_price: float | None = Field(default=None, ge=0)
    goal_action: str | None = None
    script: str | None = None
    objections: list[dict[str, str]] | None = None
    status: str | None = None
    no_answer_attempts: int | None = Field(default=None, ge=1, le=10)
    no_answer_pause_days: int | None = Field(default=None, ge=1, le=365)
    # Full replacement when provided.
    steps: list[FunnelStepIn] | None = Field(default=None, max_length=30)


class FunnelOut(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    name: str
    status: str
    goal_name: str
    goal_price: float | None
    goal_action: str
    script: str | None
    # Пары «возражение → ответ» для правой колонки экрана прозвона.
    objections: list[dict[str, str]] | None = None
    no_answer_attempts: int
    no_answer_pause_days: int
    leads_count: int = 0
    goals_reached: int = 0
    steps: list[FunnelStepOut]
    created_at: datetime


class FunnelAssignRequest(BaseModel):
    lead_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=500)
    owner_user_id: int | None = None


class FunnelAssignResponse(BaseModel):
    assigned: int


# ── helpers ────────────────────────────────────────────────────────────


def _validate_enums(
    *, goal_action: str | None, status: str | None, steps: list[FunnelStepIn] | None
) -> None:
    if goal_action is not None and goal_action not in GOAL_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"goal_action must be one of {', '.join(GOAL_ACTIONS)}",
        )
    if status is not None and status not in FUNNEL_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of {', '.join(FUNNEL_STATUSES)}",
        )
    for step in steps or []:
        if step.kind not in STEP_KINDS:
            raise HTTPException(
                status_code=400,
                detail=f"step kind must be one of {', '.join(STEP_KINDS)}",
            )


async def _funnel_out(session, funnel: Funnel) -> FunnelOut:
    leads_count = int(
        (
            await session.execute(
                select(func.count(Lead.id))
                .where(Lead.funnel_id == funnel.id)
                .where(Lead.deleted_at.is_(None))
            )
        ).scalar()
        or 0
    )
    goals = int(
        (
            await session.execute(
                select(func.count(Lead.id))
                .where(Lead.funnel_id == funnel.id)
                .where(Lead.goal_reached_at.is_not(None))
            )
        ).scalar()
        or 0
    )
    steps = sorted(funnel.steps, key=lambda s: s.order_index)
    return FunnelOut(
        id=funnel.id,
        team_id=funnel.team_id,
        name=funnel.name,
        status=funnel.status,
        goal_name=funnel.goal_name,
        goal_price=(
            float(funnel.goal_price) if funnel.goal_price is not None else None
        ),
        goal_action=funnel.goal_action,
        script=funnel.script,
        objections=funnel.objections or None,
        no_answer_attempts=funnel.no_answer_attempts,
        no_answer_pause_days=funnel.no_answer_pause_days,
        leads_count=leads_count,
        goals_reached=goals,
        steps=[
            FunnelStepOut(
                id=s.id,
                order_index=s.order_index,
                kind=s.kind,
                day_offset=s.day_offset,
                auto=s.auto,
                template_id=s.template_id,
                note=s.note,
            )
            for s in steps
        ],
        created_at=funnel.created_at,
    )


async def _reload(session, funnel_id: uuid.UUID) -> Funnel:
    """Re-select a funnel with steps eagerly loaded (post-commit)."""
    return (
        await session.execute(
            select(Funnel)
            .where(Funnel.id == funnel_id)
            .options(sa.orm.selectinload(Funnel.steps))
        )
    ).scalar_one()


async def _manager_funnel(
    session, funnel_id: uuid.UUID, user_id: int
) -> Funnel:
    funnel = (
        await session.execute(
            select(Funnel)
            .where(Funnel.id == funnel_id)
            .options(sa.orm.selectinload(Funnel.steps))
        )
    ).scalar_one_or_none()
    if funnel is None:
        raise HTTPException(status_code=404, detail="funnel not found")
    ms = await membership(session, funnel.team_id, user_id)
    if ms is None or not has_permission(ms.role, PERM_MANAGE_FUNNELS):
        raise HTTPException(
            status_code=403, detail="your role can't manage funnels"
        )
    return funnel


def _apply_steps(funnel: Funnel, steps: list[FunnelStepIn]) -> None:
    funnel.steps.clear()
    for i, s in enumerate(steps):
        funnel.steps.append(
            FunnelStep(
                order_index=i,
                kind=s.kind,
                day_offset=s.day_offset,
                auto=s.auto,
                template_id=s.template_id,
                note=(s.note or None),
            )
        )


# ── team-scoped CRUD ───────────────────────────────────────────────────


@router.get(
    "/api/v1/teams/{team_id}/funnels", response_model=list[FunnelOut]
)
async def list_funnels(
    team_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> list[FunnelOut]:
    """List the team's funnels. Any member may read the list (a rep
    sees names/goals — the Воронки management screen itself is
    gated in the UI and every mutation is manager+ on the server)."""
    async with session_factory() as session:
        ms = await membership(session, team_id, current_user.id)
        if ms is None:
            raise HTTPException(status_code=403, detail="not a team member")
        funnels = (
            (
                await session.execute(
                    select(Funnel)
                    .where(Funnel.team_id == team_id)
                    .options(sa.orm.selectinload(Funnel.steps))
                    .order_by(Funnel.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        return [await _funnel_out(session, f) for f in funnels]


@router.post("/api/v1/teams/{team_id}/funnels", response_model=FunnelOut)
async def create_funnel(
    team_id: uuid.UUID,
    body: FunnelCreate,
    current_user: User = Depends(get_current_user),
) -> FunnelOut:
    _validate_enums(
        goal_action=body.goal_action, status=body.status, steps=body.steps
    )
    async with session_factory() as session:
        ms = await membership(session, team_id, current_user.id)
        if ms is None or not has_permission(ms.role, PERM_MANAGE_FUNNELS):
            raise HTTPException(
                status_code=403, detail="your role can't manage funnels"
            )
        dup = (
            await session.execute(
                select(Funnel.id)
                .where(Funnel.team_id == team_id)
                .where(Funnel.name == body.name.strip())
                .limit(1)
            )
        ).scalar_one_or_none()
        if dup is not None:
            raise HTTPException(
                status_code=409, detail="a funnel with this name exists"
            )
        funnel = Funnel(
            team_id=team_id,
            name=body.name.strip(),
            status=body.status,
            goal_name=body.goal_name.strip(),
            goal_price=body.goal_price,
            goal_action=body.goal_action,
            script=body.script,
            objections=body.objections,
            no_answer_attempts=body.no_answer_attempts,
            no_answer_pause_days=body.no_answer_pause_days,
            created_by_user_id=current_user.id,
        )
        _apply_steps(funnel, body.steps)
        session.add(funnel)
        await session.commit()
        funnel = await _reload(session, funnel.id)
        return await _funnel_out(session, funnel)


@router.patch("/api/v1/funnels/{funnel_id}", response_model=FunnelOut)
async def update_funnel(
    funnel_id: uuid.UUID,
    body: FunnelUpdate,
    current_user: User = Depends(get_current_user),
) -> FunnelOut:
    _validate_enums(
        goal_action=body.goal_action, status=body.status, steps=body.steps
    )
    async with session_factory() as session:
        funnel = await _manager_funnel(session, funnel_id, current_user.id)
        data = body.model_dump(exclude_unset=True)
        if "name" in data and body.name:
            funnel.name = body.name.strip()
        if "goal_name" in data and body.goal_name:
            funnel.goal_name = body.goal_name.strip()
        if "goal_price" in data:
            funnel.goal_price = body.goal_price
        if "goal_action" in data and body.goal_action:
            funnel.goal_action = body.goal_action
        if "script" in data:
            funnel.script = body.script
        if "objections" in data:
            funnel.objections = body.objections
        if "status" in data and body.status:
            funnel.status = body.status
        if "no_answer_attempts" in data and body.no_answer_attempts:
            funnel.no_answer_attempts = body.no_answer_attempts
        if "no_answer_pause_days" in data and body.no_answer_pause_days:
            funnel.no_answer_pause_days = body.no_answer_pause_days
        if body.steps is not None:
            _apply_steps(funnel, body.steps)
        await session.commit()
        funnel = await _reload(session, funnel.id)
        return await _funnel_out(session, funnel)


@router.post(
    "/api/v1/funnels/{funnel_id}/duplicate", response_model=FunnelOut
)
async def duplicate_funnel(
    funnel_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> FunnelOut:
    async with session_factory() as session:
        src = await _manager_funnel(session, funnel_id, current_user.id)
        base = f"{src.name} (копия)"
        name = base
        n = 2
        while (
            await session.execute(
                select(Funnel.id)
                .where(Funnel.team_id == src.team_id)
                .where(Funnel.name == name)
                .limit(1)
            )
        ).scalar_one_or_none() is not None:
            name = f"{base} {n}"
            n += 1
        copy = Funnel(
            team_id=src.team_id,
            name=name,
            status="draft",
            goal_name=src.goal_name,
            goal_price=src.goal_price,
            goal_action=src.goal_action,
            script=src.script,
            objections=src.objections,
            no_answer_attempts=src.no_answer_attempts,
            no_answer_pause_days=src.no_answer_pause_days,
            created_by_user_id=current_user.id,
        )
        for s in sorted(src.steps, key=lambda x: x.order_index):
            copy.steps.append(
                FunnelStep(
                    order_index=s.order_index,
                    kind=s.kind,
                    day_offset=s.day_offset,
                    auto=s.auto,
                    template_id=s.template_id,
                    note=s.note,
                )
            )
        session.add(copy)
        await session.commit()
        copy = await _reload(session, copy.id)
        return await _funnel_out(session, copy)


@router.delete("/api/v1/funnels/{funnel_id}")
async def delete_funnel(
    funnel_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    """Delete a funnel. Attached leads are detached (funnel state
    cleared), not deleted."""
    async with session_factory() as session:
        funnel = await _manager_funnel(session, funnel_id, current_user.id)
        await session.execute(
            sa.update(Lead)
            .where(Lead.funnel_id == funnel.id)
            .values(funnel_id=None, funnel_step=0, next_touch_at=None)
        )
        await session.delete(funnel)
        await session.commit()
    return {"ok": True}


# ── lead distribution (the База panel's "Назначить") ───────────────────


@router.post(
    "/api/v1/funnels/{funnel_id}/assign", response_model=FunnelAssignResponse
)
async def assign_leads_to_funnel(
    funnel_id: uuid.UUID,
    body: FunnelAssignRequest,
    current_user: User = Depends(get_current_user),
) -> FunnelAssignResponse:
    """Batch-assign leads into this funnel, optionally to a rep:
    выбор → селз → воронка → назначить. Manager+ only. Leads must
    belong to the funnel's team; foreign ids are dropped silently."""
    async with session_factory() as session:
        funnel = (
            await session.execute(
                select(Funnel)
                .where(Funnel.id == funnel_id)
                .options(sa.orm.selectinload(Funnel.steps))
            )
        ).scalar_one_or_none()
        if funnel is None:
            raise HTTPException(status_code=404, detail="funnel not found")
        ms = await membership(session, funnel.team_id, current_user.id)
        if ms is None or not has_permission(ms.role, PERM_ASSIGN_LEADS):
            raise HTTPException(
                status_code=403, detail="your role can't assign leads"
            )
        if body.owner_user_id is not None:
            target_ms = await membership(
                session, funnel.team_id, body.owner_user_id
            )
            if target_ms is None:
                raise HTTPException(
                    status_code=400,
                    detail="owner_user_id must be a team member",
                )

        rows = (
            (
                await session.execute(
                    select(Lead)
                    .join(SearchQuery, SearchQuery.id == Lead.query_id)
                    .where(Lead.id.in_(body.lead_ids))
                    .where(SearchQuery.team_id == funnel.team_id)
                    .where(Lead.deleted_at.is_(None))
                )
            )
            .scalars()
            .all()
        )
        for lead in rows:
            previous_owner = lead.owner_user_id
            attach_lead(lead, funnel)
            if body.owner_user_id is not None:
                lead.owner_user_id = body.owner_user_id
            session.add(
                LeadActivity(
                    lead_id=lead.id,
                    user_id=current_user.id,
                    team_id=funnel.team_id,
                    kind="assigned",
                    payload={
                        "from": previous_owner,
                        "to": lead.owner_user_id,
                        "funnel_id": str(funnel.id),
                        "funnel_name": funnel.name,
                    },
                )
            )
        await session.commit()

        # Пакет назначен → селзу (Wave 1, события).
        if body.owner_user_id is not None and rows:
            try:
                from leadgen.core.services.team_events import batch_assigned

                await batch_assigned(
                    session,
                    team_id=funnel.team_id,
                    rep_id=body.owner_user_id,
                    count=len(rows),
                    funnel_name=funnel.name,
                )
            except Exception:  # noqa: BLE001 — уведомление не роняет назначение
                pass
        return FunnelAssignResponse(assigned=len(rows))


# ── the rep's view: funnel of a lead ──────────────────────────────────


@router.get("/api/v1/leads/{lead_id}/funnel", response_model=FunnelOut | None)
async def lead_funnel(
    lead_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> FunnelOut | None:
    """The funnel behind a lead the caller may work — renders the
    green button, the script and the touch path in call mode."""
    async with session_factory() as session:
        lead = await session.get(Lead, lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="lead not found")
        search = await session.get(SearchQuery, lead.query_id)
        allowed = search is not None and search.user_id == current_user.id
        if not allowed and search is not None and search.team_id is not None:
            ms = await membership(
                session, search.team_id, current_user.id
            )
            allowed = ms is not None and (
                not is_sales(ms.role)
                or lead.owner_user_id == current_user.id
            )
        if not allowed:
            raise HTTPException(status_code=404, detail="lead not found")
        if lead.funnel_id is None:
            return None
        funnel = (
            await session.execute(
                select(Funnel)
                .where(Funnel.id == lead.funnel_id)
                .options(sa.orm.selectinload(Funnel.steps))
            )
        ).scalar_one_or_none()
        if funnel is None:
            return None
        return await _funnel_out(session, funnel)
