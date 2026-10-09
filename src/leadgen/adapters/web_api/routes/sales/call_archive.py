"""Архив звонков по сотруднику и сессии общего ИИ-разбора.

* ``GET  /teams/{id}/call-archive/people``  — чьи звонки можно смотреть
* ``GET  /teams/{id}/call-archive``         — звонки человека за период
* ``POST /teams/{id}/call-reviews``          — разобрать выбранные звонки
* ``GET  /teams/{id}/call-reviews``          — история разборов
* ``GET  /call-reviews/{id}``                — один разбор

Тимлид (manager) и выше; продажник архив не видит. Кто чьи звонки
видит — ``call_review.can_view``.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.routes._helpers import membership
from leadgen.core.services.sales import call_review as cr
from leadgen.db.models import Call, CallReview, Lead, Team, User
from leadgen.db.session import session_factory
from leadgen.utils.tasks import spawn

router = APIRouter(tags=["call-archive"])

#: Разбор, который «идёт» дольше этого, считается оборвавшимся
#: (перезапуск сервера посреди запроса к Claude).
STALE_REVIEW = timedelta(minutes=10)


async def _gate(session, team_id: uuid.UUID, user: User):
    ms = await membership(session, team_id, user.id)
    if ms is None:
        raise HTTPException(status_code=403, detail="not a team member")
    if not cr.can_open_archive(ms.role):
        raise HTTPException(status_code=403, detail="call archive is for team leads and above")
    return ms


def _name(u: User | None) -> str | None:
    if u is None:
        return None
    return u.display_name or " ".join(filter(None, [u.first_name, u.last_name])) or u.email


@router.get("/api/v1/teams/{team_id}/call-archive/people")
async def archive_people(
    team_id: uuid.UUID, current_user: User = Depends(get_current_user)
) -> list[dict[str, Any]]:
    async with session_factory() as session:
        ms = await _gate(session, team_id, current_user)
        people = await cr.viewable_people(session, team_id, current_user.id, ms.role)
        counts = dict(
            (
                await session.execute(
                    select(Call.user_id, func.count(Call.id))
                    .where(Call.team_id == team_id)
                    .where(Call.user_id.in_([p["user_id"] for p in people]))
                    .group_by(Call.user_id)
                )
            ).all()
        )
    for p in people:
        p["calls"] = int(counts.get(p["user_id"], 0))
    return people


@router.get("/api/v1/teams/{team_id}/call-archive")
async def archive_calls(
    team_id: uuid.UUID,
    user_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
    only_talks: bool = False,
    limit: int = 200,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Звонки человека за период (даты включительно, UTC)."""
    async with session_factory() as session:
        ms = await _gate(session, team_id, current_user)
        rep = await membership(session, team_id, user_id)
        if rep is None or not cr.can_view(ms.role, current_user.id, rep.role, user_id):
            raise HTTPException(status_code=403, detail="you can't view this person's calls")
        q = (
            select(Call, Lead.name, Lead.id)
            .outerjoin(Lead, Lead.id == Call.lead_id)
            .where(Call.team_id == team_id)
            .where(Call.user_id == user_id)
        )
        if date_from:
            q = q.where(Call.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
        if date_to:
            q = q.where(
                Call.created_at < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
            )
        if only_talks:
            q = q.where(Call.talk_sec > 0)
        rows = (
            await session.execute(q.order_by(Call.created_at.desc()).limit(max(1, min(limit, 500))))
        ).all()
        team = await session.get(Team, team_id)
        auto_t = bool(team and team.call_auto_transcribe)
        auto_a = bool(team and team.call_auto_analyze)
    calls = []
    talk_total = 0
    for c, lead_name, lead_id in rows:
        a = c.analysis or {}
        talk_total += int(c.talk_sec or 0)
        calls.append(
            {
                "id": str(c.id),
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "lead_id": str(lead_id) if lead_id else None,
                "lead_name": lead_name,
                "to_number": c.to_number,
                "direction": c.direction,
                "state": c.state,
                "talk_sec": c.talk_sec,
                "duration_sec": c.duration_sec,
                "has_recording": bool(c.recording_url),
                "has_transcript": bool(c.transcript),
                "transcript": c.transcript,
                "summary": a.get("summary"),
                "outcome": a.get("suggested_outcome"),
                "quality_score": a.get("quality_score"),
                "objections": a.get("objections") or [],
                "quality_notes": a.get("quality_notes"),
                "rubric": a.get("rubric") or [],
                "too_short": bool(a.get("too_short")),
                "analyzed": bool(a) and not a.get("too_short"),
                "processing": cr.is_processing(c, auto_t, auto_a),
                "error": c.error,
            }
        )
    scored = [c["quality_score"] for c in calls if isinstance(c["quality_score"], (int, float))]
    return {
        "calls": calls,
        "stats": {
            "total": len(calls),
            "talks": sum(1 for c in calls if (c["talk_sec"] or 0) > 0),
            "talk_min": round(talk_total / 60),
            "avg_quality": round(sum(scored) / len(scored), 1) if scored else None,
        },
    }


class ReviewIn(BaseModel):
    call_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=cr.MAX_REVIEW_CALLS)
    focus: str | None = Field(default=None, max_length=500)


def _aware(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


def _review_out(r: CallReview, names: dict[int, str | None]) -> dict[str, Any]:
    status = r.status
    created = r.created_at
    if created is not None and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if status == "running" and created and datetime.now(timezone.utc) - created > STALE_REVIEW:
        status = "failed"
    return {
        "id": str(r.id),
        "status": status,
        "created_at": created.isoformat() if created else None,
        "finished_at": _aware(r.finished_at),
        "created_by": names.get(r.created_by) if r.created_by else None,
        "subject": names.get(r.subject_user_id) if r.subject_user_id else None,
        "subject_user_id": r.subject_user_id,
        "calls": len(r.call_ids or []),
        "call_ids": list(r.call_ids or []),
        "focus": r.focus,
        "result": r.result,
        "error": r.error if status == "failed" else None,
    }


async def _names(session, ids: set[int]) -> dict[int, str | None]:
    if not ids:
        return {}
    rows = (await session.execute(select(User).where(User.id.in_(ids)))).scalars().all()
    return {u.id: _name(u) for u in rows}


@router.post("/api/v1/teams/{team_id}/call-reviews")
async def create_review(
    team_id: uuid.UUID, body: ReviewIn, current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    async with session_factory() as session:
        ms = await _gate(session, team_id, current_user)
        calls = (
            await session.execute(
                select(Call).where(Call.id.in_(body.call_ids)).where(Call.team_id == team_id)
            )
        ).scalars().all()
        if len(calls) != len(set(body.call_ids)):
            raise HTTPException(status_code=404, detail="some calls were not found")
        reps = {c.user_id for c in calls}
        for uid in reps:
            rep = await membership(session, team_id, uid) if uid is not None else None
            if rep is None or not cr.can_view(ms.role, current_user.id, rep.role, uid):
                raise HTTPException(status_code=403, detail="you can't review these calls")
        if not any(c.transcript or (c.recording_url and c.record_consent) for c in calls):
            raise HTTPException(status_code=409, detail="none of the selected calls has a recording")
        review = CallReview(
            team_id=team_id,
            created_by=current_user.id,
            subject_user_id=next(iter(reps)) if len(reps) == 1 else None,
            call_ids=[str(c.id) for c in calls],
            focus=(body.focus or "").strip() or None,
            status="running",
        )
        session.add(review)
        await session.commit()
        names = await _names(session, {current_user.id, *(x for x in reps if x is not None)})
        out = _review_out(review, names)
    spawn(cr.run_review(review.id), name=f"call-review-{review.id}")
    return out


@router.get("/api/v1/teams/{team_id}/call-reviews")
async def list_reviews(
    team_id: uuid.UUID,
    user_id: int | None = None,
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    async with session_factory() as session:
        ms = await _gate(session, team_id, current_user)
        q = select(CallReview).where(CallReview.team_id == team_id)
        if user_id is not None:
            q = q.where(CallReview.subject_user_id == user_id)
        rows = (await session.execute(q.order_by(CallReview.created_at.desc()).limit(100))).scalars().all()
        people = {
            p["user_id"] for p in await cr.viewable_people(session, team_id, current_user.id, ms.role)
        }
        # Разбор виден, если ты видишь того, чьи звонки разбирались, или
        # сам его запускал.
        rows = [
            r for r in rows
            if r.created_by == current_user.id or r.subject_user_id is None or r.subject_user_id in people
        ]
        names = await _names(
            session, {x for r in rows for x in (r.created_by, r.subject_user_id) if x is not None}
        )
        out = [_review_out(r, names) for r in rows]
    for item in out:
        item.pop("result", None)  # список — без тяжёлого итога
    return out


@router.get("/api/v1/call-reviews/{review_id}")
async def get_review(
    review_id: uuid.UUID, current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    async with session_factory() as session:
        review = await session.get(CallReview, review_id)
        if review is None:
            raise HTTPException(status_code=404, detail="review not found")
        ms = await _gate(session, review.team_id, current_user)
        if review.created_by != current_user.id and review.subject_user_id is not None:
            rep = await membership(session, review.team_id, review.subject_user_id)
            if rep is None or not cr.can_view(ms.role, current_user.id, rep.role, review.subject_user_id):
                raise HTTPException(status_code=404, detail="review not found")
        names = await _names(
            session, {x for x in (review.created_by, review.subject_user_id) if x is not None}
        )
        return _review_out(review, names)


@router.post("/api/v1/call-reviews/{review_id}/retry")
async def retry_review(
    review_id: uuid.UUID, current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    """Повторить неудавшийся разбор с теми же звонками и пожеланием."""
    async with session_factory() as session:
        review = await session.get(CallReview, review_id)
        if review is None:
            raise HTTPException(status_code=404, detail="review not found")
        await _gate(session, review.team_id, current_user)
        if review.created_by != current_user.id and review.subject_user_id is not None:
            ms = await membership(session, review.team_id, current_user.id)
            rep = await membership(session, review.team_id, review.subject_user_id)
            if rep is None or not cr.can_view(ms.role, current_user.id, rep.role, review.subject_user_id):
                raise HTTPException(status_code=404, detail="review not found")
        out = _review_out(review, {})
        if out["status"] == "running":
            raise HTTPException(status_code=409, detail="review is still running")
        review.status = "running"
        review.error = None
        review.result = None
        review.finished_at = None
        review.created_at = datetime.now(timezone.utc)
        await session.commit()
        names = await _names(session, {x for x in (review.created_by, review.subject_user_id) if x is not None})
        out = _review_out(review, names)
    spawn(cr.run_review(review.id), name=f"call-review-{review.id}")
    out.pop("result", None)
    return out
