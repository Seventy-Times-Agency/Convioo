"""``/api/v1/leads/{id}/tasks``, ``/api/v1/tasks/*``, ``/api/v1/users/me/tasks`` — lead task management."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.schemas import LeadTask as LeadTaskSchema
from leadgen.adapters.web_api.schemas import (
    LeadTaskCreate,
    LeadTaskListResponse,
    LeadTaskUpdate,
)
from leadgen.db.models import Lead, LeadActivity, LeadTask, SearchQuery, User
from leadgen.db.session import session_factory

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tasks"])


@router.get(
    "/api/v1/leads/{lead_id}/tasks",
    response_model=LeadTaskListResponse,
)
async def list_lead_tasks(
    lead_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> LeadTaskListResponse:
    user_id = current_user.id
    async with session_factory() as session:
        stmt = (
            select(LeadTask)
            .where(LeadTask.lead_id == lead_id)
            .where(LeadTask.user_id == user_id)
            .order_by(
                LeadTask.done_at.is_(None).desc(),
                LeadTask.due_at.asc().nullslast(),
                LeadTask.created_at.desc(),
            )
        )
        rows = (await session.execute(stmt)).scalars().all()
        items = [LeadTaskSchema.model_validate(r) for r in rows]
    return LeadTaskListResponse(items=items)


@router.post(
    "/api/v1/leads/{lead_id}/tasks",
    response_model=LeadTaskSchema,
)
async def create_lead_task(
    lead_id: uuid.UUID,
    body: LeadTaskCreate,
    current_user: User = Depends(get_current_user),
) -> LeadTaskSchema:
    user_id = current_user.id
    async with session_factory() as session:
        row = LeadTask(
            lead_id=lead_id,
            user_id=user_id,
            content=body.content.strip(),
            due_at=body.due_at,
        )
        session.add(row)
        search = (
            await session.execute(
                select(SearchQuery)
                .join(Lead, Lead.query_id == SearchQuery.id)
                .where(Lead.id == lead_id)
                .limit(1)
            )
        ).scalar_one_or_none()
        session.add(
            LeadActivity(
                lead_id=lead_id,
                user_id=user_id,
                team_id=search.team_id if search else None,
                kind="task",
                payload={
                    "content": body.content.strip()[:200],
                    "due_at": body.due_at.isoformat() if body.due_at else None,
                },
            )
        )
        await session.commit()
        await session.refresh(row)
        return LeadTaskSchema.model_validate(row)


@router.patch(
    "/api/v1/tasks/{task_id}",
    response_model=LeadTaskSchema,
)
async def update_lead_task(
    task_id: uuid.UUID,
    body: LeadTaskUpdate,
    current_user: User = Depends(get_current_user),
) -> LeadTaskSchema:
    user_id = current_user.id
    async with session_factory() as session:
        row = await session.get(LeadTask, task_id)
        if row is None or row.user_id != user_id:
            raise HTTPException(status_code=404, detail="task not found")
        data = body.model_dump(exclude_unset=True)
        if "content" in data and data["content"]:
            row.content = data["content"].strip()
        if "due_at" in data:
            row.due_at = data["due_at"]
        if "done" in data and data["done"] is not None:
            row.done_at = (
                datetime.now(timezone.utc) if data["done"] else None
            )
        await session.commit()
        await session.refresh(row)
        return LeadTaskSchema.model_validate(row)


@router.delete("/api/v1/tasks/{task_id}")
async def delete_lead_task(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    user_id = current_user.id
    async with session_factory() as session:
        row = await session.get(LeadTask, task_id)
        if row is None or row.user_id != user_id:
            return {"deleted": False}
        await session.delete(row)
        await session.commit()
    return {"deleted": True}


@router.get(
    "/api/v1/users/me/tasks",
    response_model=LeadTaskListResponse,
)
async def list_my_tasks(
    open_only: bool = True,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
) -> LeadTaskListResponse:
    """Today's-tasks widget feed: open tasks across every lead."""
    user_id = current_user.id
    limit = max(1, min(limit, 500))
    async with session_factory() as session:
        stmt = select(LeadTask).where(LeadTask.user_id == user_id)
        if open_only:
            stmt = stmt.where(LeadTask.done_at.is_(None))
        stmt = stmt.order_by(
            LeadTask.due_at.asc().nullslast(),
            LeadTask.created_at.desc(),
        ).limit(limit)
        rows = (await session.execute(stmt)).scalars().all()
        items = [LeadTaskSchema.model_validate(r) for r in rows]
    return LeadTaskListResponse(items=items)
