"""``/api/v1/sequences`` — follow-up email sequence CRUD + enrollment.

Sequences are user-defined templates of email steps spread over days
(Day 0 / Day 3 / Day 7 by default). Enrolling a lead schedules the
first step at ``now + step[0].day`` and the arq worker advances each
enrollment one step at a time, completing when the last step is sent.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from leadgen.adapters.web_api.auth import enforce_rate_limit, get_current_user
from leadgen.db.models import EmailSequence, Lead, SequenceEnrollment, User
from leadgen.db.session import session_factory
from leadgen.utils.rate_limit import sequence_create_limiter

router = APIRouter(prefix="/api/v1", tags=["sequences"])


class SequenceStep(BaseModel):
    day: int
    subject: str
    body: str


class SequenceCreate(BaseModel):
    name: str
    steps: list[SequenceStep]


class EnrollRequest(BaseModel):
    lead_id: str


@router.post("/sequences")
async def create_sequence(
    data: SequenceCreate,
    user: User = Depends(get_current_user),
) -> dict:
    enforce_rate_limit(
        sequence_create_limiter, f"user:{user.id}", retry_hint=60
    )
    if not data.steps:
        raise HTTPException(status_code=400, detail="steps cannot be empty")
    async with session_factory() as session:
        seq = EmailSequence(
            user_id=user.id,
            name=data.name,
            steps=[s.model_dump() for s in data.steps],
        )
        session.add(seq)
        await session.commit()
        await session.refresh(seq)
    return {
        "id": str(seq.id),
        "name": seq.name,
        "steps_count": len(data.steps),
    }


@router.get("/sequences")
async def list_sequences(
    user: User = Depends(get_current_user),
) -> list[dict]:
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(EmailSequence).where(
                    EmailSequence.user_id == user.id
                )
            )
        ).scalars().all()
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "steps": s.steps,
            "created_at": s.created_at.isoformat(),
        }
        for s in rows
    ]


@router.delete("/sequences/{seq_id}")
async def delete_sequence(
    seq_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    async with session_factory() as session:
        seq = await session.get(EmailSequence, uuid.UUID(seq_id))
        if seq is None or seq.user_id != user.id:
            raise HTTPException(status_code=404, detail="Not found")
        await session.delete(seq)
        await session.commit()
    return {"deleted": seq_id}


@router.post("/sequences/{seq_id}/enroll")
async def enroll_lead(
    seq_id: str,
    data: EnrollRequest,
    user: User = Depends(get_current_user),
) -> dict:
    async with session_factory() as session:
        seq = await session.get(EmailSequence, uuid.UUID(seq_id))
        if seq is None or seq.user_id != user.id:
            raise HTTPException(status_code=404, detail="Sequence not found")

        lead = await session.get(Lead, uuid.UUID(data.lead_id))
        if lead is None:
            raise HTTPException(status_code=404, detail="Lead not found")

        steps = seq.steps or []
        if not steps:
            raise HTTPException(
                status_code=400, detail="Sequence has no steps"
            )

        delay_days = int(steps[0].get("day", 0))
        next_send = datetime.now(timezone.utc) + timedelta(days=delay_days)

        enrollment = SequenceEnrollment(
            sequence_id=seq.id,
            lead_id=lead.id,
            user_id=user.id,
            current_step=0,
            status="active",
            next_send_at=next_send,
        )
        session.add(enrollment)
        await session.commit()
        await session.refresh(enrollment)

    return {
        "enrollment_id": str(enrollment.id),
        "next_send_at": next_send.isoformat(),
        "steps_total": len(steps),
    }


@router.get("/sequences/{seq_id}/enrollments")
async def list_enrollments(
    seq_id: str,
    user: User = Depends(get_current_user),
) -> list[dict]:
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(SequenceEnrollment).where(
                    SequenceEnrollment.sequence_id == uuid.UUID(seq_id),
                    SequenceEnrollment.user_id == user.id,
                )
            )
        ).scalars().all()
    return [
        {
            "id": str(e.id),
            "lead_id": str(e.lead_id),
            "current_step": e.current_step,
            "status": e.status,
            "next_send_at": (
                e.next_send_at.isoformat() if e.next_send_at else None
            ),
        }
        for e in rows
    ]
