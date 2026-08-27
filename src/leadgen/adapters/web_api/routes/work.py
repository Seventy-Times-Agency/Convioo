"""``/api/v1/work/*`` — the sales rep's call-mode surface (Wave 1).

The queue orders the rep's assigned leads the way the mockup reads:
перезвоны (due callbacks) → горячие (score ≥ 75) → остальные. The
one-button outcome endpoint applies the funnel engine's rules (
no-answer rule, callback scheduling, goal stamping) and writes the
timeline activity, so the screen's three states stay thin clients.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.routes._helpers import membership
from leadgen.core.services.funnel_engine import (
    CALL_OUTCOMES,
    apply_call_outcome,
)
from leadgen.core.services.team_permissions import is_sales
from leadgen.db.models import (
    Funnel,
    Lead,
    LeadActivity,
    SearchQuery,
    User,
)
from leadgen.db.session import session_factory

router = APIRouter(tags=["work"])

HOT_SCORE = 75.0


class QueueLead(BaseModel):
    id: uuid.UUID
    name: str
    phone: str | None
    score: float | None
    bucket: str  # callback | hot | rest
    next_touch_at: datetime | None
    lead_status: str
    funnel_id: uuid.UUID | None
    business_language: str | None = None


class WorkQueueResponse(BaseModel):
    callbacks: list[QueueLead]
    hot: list[QueueLead]
    rest: list[QueueLead]
    total: int


class CallOutcomeRequest(BaseModel):
    outcome: str
    callback_at: datetime | None = None
    note: str | None = Field(default=None, max_length=4000)


class CallOutcomeResponse(BaseModel):
    ok: bool = True
    result: dict[str, Any]


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes even for timezone=True columns —
    normalise to UTC before comparing."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _bucket_of(lead: Lead, now: datetime) -> str:
    due = _aware(lead.next_touch_at)
    if due is not None and due <= now:
        return "callback"
    if (lead.score_ai or 0) >= HOT_SCORE:
        return "hot"
    return "rest"


@router.get("/api/v1/work/queue", response_model=WorkQueueResponse)
async def work_queue(
    team_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=300),
    current_user: User = Depends(get_current_user),
) -> WorkQueueResponse:
    """The caller's call queue inside a team: their assigned,
    unfinished leads bucketed перезвоны → горячие → остальные."""
    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        ms = await membership(session, team_id, current_user.id)
        if ms is None:
            raise HTTPException(status_code=403, detail="not a team member")
        rows = (
            (
                await session.execute(
                    select(Lead)
                    .join(SearchQuery, SearchQuery.id == Lead.query_id)
                    .where(SearchQuery.team_id == team_id)
                    .where(Lead.owner_user_id == current_user.id)
                    .where(Lead.deleted_at.is_(None))
                    .where(Lead.archived_at.is_(None))
                    .where(Lead.goal_reached_at.is_(None))
                    .order_by(
                        Lead.next_touch_at.asc().nullslast(),
                        Lead.score_ai.desc().nullslast(),
                    )
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )

    buckets: dict[str, list[QueueLead]] = {
        "callback": [],
        "hot": [],
        "rest": [],
    }
    for lead in rows:
        b = _bucket_of(lead, now)
        buckets[b].append(
            QueueLead(
                id=lead.id,
                name=lead.name,
                phone=lead.phone,
                score=lead.score_ai,
                bucket=b,
                next_touch_at=lead.next_touch_at,
                lead_status=lead.lead_status,
                funnel_id=lead.funnel_id,
                business_language=lead.business_language,
            )
        )
    buckets["callback"].sort(key=lambda q: _aware(q.next_touch_at) or now)
    return WorkQueueResponse(
        callbacks=buckets["callback"],
        hot=buckets["hot"],
        rest=buckets["rest"],
        total=len(rows),
    )


@router.post(
    "/api/v1/leads/{lead_id}/call-outcome",
    response_model=CallOutcomeResponse,
)
async def call_outcome(
    lead_id: uuid.UUID,
    body: CallOutcomeRequest,
    current_user: User = Depends(get_current_user),
) -> CallOutcomeResponse:
    """One-button outcome from call mode. Applies the funnel rules
    (no-answer → 3 tries → pause → free pool; callback; thinking →
    next touch; goal → stamp + goal config back) and writes the
    ``call`` activity with the rep's note."""
    if body.outcome not in CALL_OUTCOMES:
        raise HTTPException(
            status_code=400,
            detail=f"outcome must be one of {', '.join(CALL_OUTCOMES)}",
        )
    async with session_factory() as session:
        lead = await session.get(Lead, lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="lead not found")
        search = await session.get(SearchQuery, lead.query_id)
        allowed = search is not None and search.user_id == current_user.id
        team_id = search.team_id if search is not None else None
        if not allowed and team_id is not None:
            ms = await membership(session, team_id, current_user.id)
            allowed = ms is not None and (
                not is_sales(ms.role)
                or lead.owner_user_id == current_user.id
            )
        if not allowed:
            raise HTTPException(status_code=404, detail="lead not found")

        funnel: Funnel | None = None
        if lead.funnel_id is not None:
            funnel = (
                await session.execute(
                    select(Funnel)
                    .where(Funnel.id == lead.funnel_id)
                    .options(selectinload(Funnel.steps))
                )
            ).scalar_one_or_none()

        result = apply_call_outcome(
            lead,
            funnel,
            body.outcome,
            callback_at=body.callback_at,
        )
        if body.note:
            result["note"] = True

        session.add(
            LeadActivity(
                lead_id=lead.id,
                user_id=current_user.id,
                team_id=team_id,
                kind="call",
                payload={
                    "outcome": body.outcome,
                    "note": (body.note or None),
                    **{
                        k: v
                        for k, v in result.items()
                        if k not in ("outcome", "note")
                    },
                },
            )
        )
        await session.commit()
        return CallOutcomeResponse(ok=True, result=result)
