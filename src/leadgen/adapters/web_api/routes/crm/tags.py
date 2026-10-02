"""``/api/v1/tags`` + ``/api/v1/leads/{id}/tags`` — user-defined chips.

Tags are personal by default and team-scoped when created with a
``team_id``; assignment to a lead is many-to-many via
``lead_tag_assignments``. Carved out of ``app.py``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.routes._helpers import (
    can_manage_tag as _can_manage_tag,
)
from leadgen.adapters.web_api.routes._helpers import (
    membership as _membership,
)
from leadgen.adapters.web_api.schemas import (
    LeadTagCreate,
    LeadTagListResponse,
    LeadTagsAssignRequest,
    LeadTagSchema,
    LeadTagUpdate,
)
from leadgen.db.models import (
    Lead,
    LeadTag,
    LeadTagAssignment,
    SearchQuery,
    User,
)
from leadgen.db.session import session_factory

router = APIRouter(tags=["tags"])


@router.get("/api/v1/tags", response_model=LeadTagListResponse)
async def list_tags(
    team_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
) -> LeadTagListResponse:
    """Return the caller's tag palette.

    Personal palette by default; pass ``team_id`` to get the shared
    team palette. The endpoint enforces team membership so an outsider
    can't enumerate someone else's chips.
    """
    async with session_factory() as session:
        stmt = select(LeadTag).order_by(LeadTag.created_at.asc())
        if team_id is not None:
            membership = await _membership(session, team_id, current_user.id)
            if membership is None:
                raise HTTPException(status_code=403, detail="forbidden")
            stmt = stmt.where(LeadTag.team_id == team_id)
        else:
            stmt = stmt.where(LeadTag.user_id == current_user.id).where(
                LeadTag.team_id.is_(None)
            )
        rows = (await session.execute(stmt)).scalars().all()
    return LeadTagListResponse(
        items=[
            LeadTagSchema(
                id=t.id, name=t.name, color=t.color, team_id=t.team_id
            )
            for t in rows
        ]
    )


@router.post("/api/v1/tags", response_model=LeadTagSchema)
async def create_tag(
    body: LeadTagCreate,
    current_user: User = Depends(get_current_user),
) -> LeadTagSchema:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    color = (body.color or "slate").strip().lower()
    async with session_factory() as session:
        if body.team_id is not None:
            membership = await _membership(
                session, body.team_id, current_user.id
            )
            if membership is None:
                raise HTTPException(status_code=403, detail="forbidden")
        # Standard SQL treats NULLs as distinct in unique constraints,
        # which would let two personal tags share a name. Pre-check
        # explicitly so the conflict surfaces the same way on Postgres
        # and SQLite.
        collision_stmt = select(LeadTag).where(
            func.lower(LeadTag.name) == name.lower()
        )
        if body.team_id is None:
            collision_stmt = collision_stmt.where(
                LeadTag.user_id == current_user.id
            ).where(LeadTag.team_id.is_(None))
        else:
            collision_stmt = collision_stmt.where(
                LeadTag.team_id == body.team_id
            )
        existing = (
            await session.execute(collision_stmt.limit(1))
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail="tag with this name already exists",
            )
        tag = LeadTag(
            user_id=current_user.id,
            team_id=body.team_id,
            name=name,
            color=color,
        )
        session.add(tag)
        await session.commit()
        await session.refresh(tag)
    return LeadTagSchema(
        id=tag.id, name=tag.name, color=tag.color, team_id=tag.team_id
    )


@router.patch("/api/v1/tags/{tag_id}", response_model=LeadTagSchema)
async def update_tag(
    tag_id: uuid.UUID,
    body: LeadTagUpdate,
    current_user: User = Depends(get_current_user),
) -> LeadTagSchema:
    async with session_factory() as session:
        tag = await session.get(LeadTag, tag_id)
        if tag is None:
            raise HTTPException(status_code=404, detail="tag not found")
        if not await _can_manage_tag(session, tag, current_user.id):
            raise HTTPException(status_code=403, detail="forbidden")
        if body.name is not None:
            cleaned = body.name.strip()
            if not cleaned:
                raise HTTPException(
                    status_code=400, detail="name cannot be empty"
                )
            collision_stmt = (
                select(LeadTag.id)
                .where(LeadTag.id != tag.id)
                .where(func.lower(LeadTag.name) == cleaned.lower())
            )
            if tag.team_id is None:
                collision_stmt = collision_stmt.where(
                    LeadTag.user_id == tag.user_id
                ).where(LeadTag.team_id.is_(None))
            else:
                collision_stmt = collision_stmt.where(
                    LeadTag.team_id == tag.team_id
                )
            if (
                await session.execute(collision_stmt.limit(1))
            ).scalar_one_or_none() is not None:
                raise HTTPException(
                    status_code=409,
                    detail="tag with this name already exists",
                )
            tag.name = cleaned
        if body.color is not None:
            tag.color = body.color.strip().lower() or "slate"
        await session.commit()
        await session.refresh(tag)
    return LeadTagSchema(
        id=tag.id, name=tag.name, color=tag.color, team_id=tag.team_id
    )


@router.delete("/api/v1/tags/{tag_id}")
async def delete_tag(
    tag_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    async with session_factory() as session:
        tag = await session.get(LeadTag, tag_id)
        if tag is None:
            raise HTTPException(status_code=404, detail="tag not found")
        if not await _can_manage_tag(session, tag, current_user.id):
            raise HTTPException(status_code=403, detail="forbidden")
        await session.delete(tag)
        await session.commit()
    return {"ok": True}


@router.put(
    "/api/v1/leads/{lead_id}/tags",
    response_model=LeadTagListResponse,
)
async def assign_lead_tags(
    lead_id: uuid.UUID,
    body: LeadTagsAssignRequest,
    current_user: User = Depends(get_current_user),
) -> LeadTagListResponse:
    """Replace the lead's tag set with the supplied list.

    Authorisation: caller must own the parent search query (or be a
    member of the team that does). Tag ids must belong to the caller
    (personal) or the same team — we don't allow attaching a foreign
    team's tag to a shared lead.
    """
    async with session_factory() as session:
        lead = await session.get(Lead, lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="lead not found")
        search = await session.get(SearchQuery, lead.query_id)
        if search is None:
            raise HTTPException(status_code=404, detail="search not found")
        allowed = search.user_id == current_user.id
        if not allowed and search.team_id is not None:
            allowed = (
                await _membership(session, search.team_id, current_user.id)
            ) is not None
        if not allowed:
            raise HTTPException(status_code=403, detail="forbidden")

        requested_ids = list(dict.fromkeys(body.tag_ids))
        tag_rows: list[LeadTag] = []
        if requested_ids:
            tags_stmt = select(LeadTag).where(LeadTag.id.in_(requested_ids))
            tag_rows = list((await session.execute(tags_stmt)).scalars().all())
            if len(tag_rows) != len(requested_ids):
                raise HTTPException(
                    status_code=404, detail="some tags not found"
                )
            for tag in tag_rows:
                tag_owned_personally = (
                    tag.user_id == current_user.id and tag.team_id is None
                )
                tag_owned_by_lead_team = (
                    tag.team_id is not None
                    and tag.team_id == search.team_id
                )
                if not (tag_owned_personally or tag_owned_by_lead_team):
                    raise HTTPException(
                        status_code=403,
                        detail="tag is not available in this scope",
                    )

        await session.execute(
            LeadTagAssignment.__table__.delete().where(
                LeadTagAssignment.lead_id == lead_id
            )
        )
        for tag in tag_rows:
            session.add(
                LeadTagAssignment(lead_id=lead_id, tag_id=tag.id)
            )
        await session.commit()

    return LeadTagListResponse(
        items=[
            LeadTagSchema(
                id=t.id, name=t.name, color=t.color, team_id=t.team_id
            )
            for t in tag_rows
        ]
    )
