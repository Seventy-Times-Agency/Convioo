"""``/api/v1/segments`` — saved CRM filter views (smart bookmarks).

Each segment is either personal (``team_id`` null) or team-scoped.
Listing unions the caller's personal segments + every segment scoped
to a team they belong to. Carved out of ``app.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.schemas import (
    LeadSegmentCreate,
    LeadSegmentListResponse,
    LeadSegmentSchema,
    LeadSegmentUpdate,
)
from leadgen.db.models import LeadSegment, TeamMembership, User
from leadgen.db.session import session_factory

router = APIRouter(tags=["segments"])


def _to_schema(row: LeadSegment) -> LeadSegmentSchema:
    return LeadSegmentSchema(
        id=str(row.id),
        name=row.name,
        team_id=str(row.team_id) if row.team_id else None,
        filter_json=row.filter_json or {},
        sort_order=row.sort_order,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/api/v1/segments", response_model=LeadSegmentListResponse)
async def list_segments(
    current_user: User = Depends(get_current_user),
) -> LeadSegmentListResponse:
    """Return private segments + every team-scoped segment the user
    sees through their memberships, ordered by ``sort_order``."""
    async with session_factory() as session:
        team_ids = (
            (
                await session.execute(
                    select(TeamMembership.team_id).where(
                        TeamMembership.user_id == current_user.id
                    )
                )
            )
            .scalars()
            .all()
        )
        stmt = select(LeadSegment).where(
            sa.or_(
                sa.and_(
                    LeadSegment.user_id == current_user.id,
                    LeadSegment.team_id.is_(None),
                ),
                LeadSegment.team_id.in_(team_ids) if team_ids else sa.false(),
            )
        ).order_by(LeadSegment.sort_order, LeadSegment.created_at)
        rows = (await session.execute(stmt)).scalars().all()
    return LeadSegmentListResponse(items=[_to_schema(r) for r in rows])


@router.post("/api/v1/segments", response_model=LeadSegmentSchema)
async def create_segment(
    body: LeadSegmentCreate,
    current_user: User = Depends(get_current_user),
) -> LeadSegmentSchema:
    """Save a new segment for the current user."""
    team_uuid: uuid.UUID | None = None
    if body.team_id:
        try:
            team_uuid = uuid.UUID(body.team_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="invalid team_id"
            ) from exc

    async with session_factory() as session:
        if team_uuid is not None:
            # Make sure the user actually belongs to that team —
            # otherwise they could attach a private bookmark to
            # somebody else's workspace.
            membership = (
                await session.execute(
                    select(TeamMembership)
                    .where(TeamMembership.user_id == current_user.id)
                    .where(TeamMembership.team_id == team_uuid)
                )
            ).scalar_one_or_none()
            if membership is None:
                raise HTTPException(
                    status_code=403, detail="not a team member"
                )
        row = LeadSegment(
            user_id=current_user.id,
            team_id=team_uuid,
            name=body.name.strip(),
            filter_json=body.filter_json or {},
            sort_order=body.sort_order,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return _to_schema(row)


@router.patch(
    "/api/v1/segments/{segment_id}",
    response_model=LeadSegmentSchema,
)
async def update_segment(
    segment_id: uuid.UUID,
    body: LeadSegmentUpdate,
    current_user: User = Depends(get_current_user),
) -> LeadSegmentSchema:
    async with session_factory() as session:
        row = await session.get(LeadSegment, segment_id)
        if row is None or row.user_id != current_user.id:
            raise HTTPException(
                status_code=404, detail="segment not found"
            )
        if body.name is not None:
            row.name = body.name.strip()
        if body.filter_json is not None:
            row.filter_json = body.filter_json
        if body.sort_order is not None:
            row.sort_order = body.sort_order
        row.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(row)
    return _to_schema(row)


@router.delete("/api/v1/segments/{segment_id}")
async def delete_segment(
    segment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    async with session_factory() as session:
        row = await session.get(LeadSegment, segment_id)
        if row is None or row.user_id != current_user.id:
            raise HTTPException(
                status_code=404, detail="segment not found"
            )
        await session.delete(row)
        await session.commit()
    return {"ok": True}
