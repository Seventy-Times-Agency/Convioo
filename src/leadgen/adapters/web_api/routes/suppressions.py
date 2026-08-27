"""``/api/v1/suppressions`` — recipient do-not-contact list.

A per-user opt-out store consulted by the outreach send paths before
every send. Lets a user honour an unsubscribe / "please stop" request so
the same business email re-scraped in a later search is never contacted
again (GDPR right-to-object / CAN-SPAM opt-out).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.core.services.suppression import (
    add_suppression,
    list_suppressions,
    normalize_email,
    remove_suppression,
)
from leadgen.db.models import User
from leadgen.db.session import session_factory

router = APIRouter(tags=["suppressions"])


class SuppressionSchema(BaseModel):
    email: str
    reason: str | None = None
    source: str | None = None
    created_at: datetime


class SuppressionListResponse(BaseModel):
    items: list[SuppressionSchema]


class SuppressionCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    reason: str | None = Field(default=None, max_length=64)


@router.get("/api/v1/suppressions", response_model=SuppressionListResponse)
async def list_suppressed(
    current_user: User = Depends(get_current_user),
) -> SuppressionListResponse:
    async with session_factory() as session:
        rows = await list_suppressions(session, user_id=current_user.id)
    return SuppressionListResponse(
        items=[
            SuppressionSchema(
                email=r.email,
                reason=r.reason,
                source=r.source,
                created_at=r.created_at,
            )
            for r in rows
        ]
    )


@router.post("/api/v1/suppressions", response_model=SuppressionSchema)
async def create_suppression(
    body: SuppressionCreate,
    current_user: User = Depends(get_current_user),
) -> SuppressionSchema:
    if not normalize_email(body.email):
        raise HTTPException(status_code=400, detail="email is required")
    async with session_factory() as session:
        row = await add_suppression(
            session,
            user_id=current_user.id,
            email=body.email,
            reason=body.reason,
            source="manual",
        )
        await session.commit()
        # add_suppression returns the existing or new row; never None here
        # because we validated a non-empty email above.
        assert row is not None
        return SuppressionSchema(
            email=row.email,
            reason=row.reason,
            source=row.source,
            created_at=row.created_at,
        )


@router.delete("/api/v1/suppressions/{email}", status_code=204)
async def delete_suppression(
    email: str,
    current_user: User = Depends(get_current_user),
) -> None:
    async with session_factory() as session:
        removed = await remove_suppression(
            session, user_id=current_user.id, email=email
        )
        await session.commit()
    if not removed:
        raise HTTPException(status_code=404, detail="not suppressed")
