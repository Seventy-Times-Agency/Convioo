"""``/api/v1/teams/{id}/journal`` — журнал действий команды.

Только чтение: записи создаются сервисом ``team_journal`` в точках
самих действий, а редактировать или удалять их нельзя никому — на
этом держится доверие к журналу. Доступ — ``PERM_VIEW_AUDIT_LOG``
(владелец и админ): лента показывает и отклонённые попытки, и смену
потолка затрат, селзам и менеджерам это не адресовано.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.routes._helpers import membership
from leadgen.core.services.team_permissions import (
    PERM_VIEW_AUDIT_LOG,
    has_permission,
)
from leadgen.db.models import JOURNAL_KINDS, TeamActionLog, User
from leadgen.db.session import session_factory

router = APIRouter(tags=["journal"])


class JournalEntry(BaseModel):
    id: uuid.UUID
    at: datetime
    actor_id: int | None
    actor_name: str | None
    actor_role: str | None
    kind: str
    payload: dict[str, Any] | None
    object_label: str | None


class JournalResponse(BaseModel):
    entries: list[JournalEntry]
    kinds: list[str]


@router.get(
    "/api/v1/teams/{team_id}/journal", response_model=JournalResponse
)
async def team_journal(
    team_id: uuid.UUID,
    kind: str | None = None,
    actor_id: int | None = None,
    days: int = Query(default=7, ge=1, le=365),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
) -> JournalResponse:
    async with session_factory() as session:
        ms = await membership(session, team_id, current_user.id)
        if ms is None or not has_permission(ms.role, PERM_VIEW_AUDIT_LOG):
            raise HTTPException(
                status_code=403,
                detail="your role can't view the action journal",
            )
        since = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(TeamActionLog)
            .where(TeamActionLog.team_id == team_id)
            .where(TeamActionLog.created_at >= since)
            .order_by(TeamActionLog.created_at.desc())
            .limit(limit)
        )
        if kind:
            stmt = stmt.where(TeamActionLog.kind == kind)
        if actor_id is not None:
            stmt = stmt.where(TeamActionLog.actor_id == actor_id)
        rows = (await session.execute(stmt)).scalars().all()
    return JournalResponse(
        entries=[
            JournalEntry(
                id=r.id,
                at=r.created_at,
                actor_id=r.actor_id,
                actor_name=r.actor_name,
                actor_role=r.actor_role,
                kind=r.kind,
                payload=r.payload,
                object_label=r.object_label,
            )
            for r in rows
        ],
        kinds=list(JOURNAL_KINDS),
    )
