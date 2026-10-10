"""Действия над выбранными лидами в «Базе».

``POST /api/v1/teams/{team_id}/base/bulk`` с ``action``:

* ``unassign`` — вернуть в базу: снять с продажника, лид снова свободный;
  история звонков и касаний остаётся;
* ``archive`` / ``unarchive`` — в архив и обратно (из архива лид в поиске
  больше не всплывёт, как и при архиве по одному);
* ``restore_contact`` — из «Нет контакта» обратно в работу: статус
  «новый», без продажника;
* ``delete`` — удалить (мягко, как удаление по одному). Только владелец,
  технический и РОП.

Раздавать и забирать — тимлид и выше (право ``assign_leads``); тимлид с
группой — только лиды своей группы и свободные.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.routes._helpers import membership
from leadgen.core.services.account.squads import visible_member_ids
from leadgen.core.services.account.team_permissions import (
    PERM_ASSIGN_LEADS,
    ROLE_ADMIN,
    ROLE_OWNER,
    ROLE_TECH,
    has_permission,
    normalize_role,
)
from leadgen.core.services.crm.lead_archive import archive_lead, unarchive_lead
from leadgen.db.models import Lead, LeadActivity, SearchQuery, User
from leadgen.db.session import session_factory

router = APIRouter(tags=["base"])

Action = Literal["unassign", "archive", "unarchive", "restore_contact", "delete"]


class BulkIn(BaseModel):
    lead_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=1000)
    action: Action


@router.post("/api/v1/teams/{team_id}/base/bulk")
async def base_bulk(
    team_id: uuid.UUID,
    body: BulkIn,
    current_user: User = Depends(get_current_user),
) -> dict[str, int]:
    async with session_factory() as session:
        ms = await membership(session, team_id, current_user.id)
        if ms is None:
            raise HTTPException(status_code=403, detail="not a team member")
        if not has_permission(ms.role, PERM_ASSIGN_LEADS):
            raise HTTPException(status_code=403, detail="the base is a manager's tool")
        if body.action == "delete" and normalize_role(ms.role) not in (ROLE_OWNER, ROLE_TECH, ROLE_ADMIN):
            raise HTTPException(status_code=403, detail="only the owner or head of sales can delete leads")

        q = (
            select(Lead, SearchQuery)
            .join(SearchQuery, SearchQuery.id == Lead.query_id)
            .where(Lead.id.in_(body.lead_ids))
            .where(SearchQuery.team_id == team_id)
            .where(Lead.deleted_at.is_(None))
        )
        scope_ids = await visible_member_ids(session, team_id, current_user.id)
        if scope_ids is not None:
            q = q.where(Lead.owner_user_id.in_(scope_ids) | Lead.owner_user_id.is_(None))
        rows = (await session.execute(q)).all()

        now = datetime.now(timezone.utc)
        changed = 0
        for lead, search in rows:
            if body.action == "unassign":
                if lead.owner_user_id is None and lead.next_touch_at is None:
                    continue
                previous = lead.owner_user_id
                lead.owner_user_id = None
                lead.next_touch_at = None
                lead.no_answer_count = 0
                session.add(
                    LeadActivity(
                        lead_id=lead.id,
                        user_id=current_user.id,
                        team_id=team_id,
                        kind="assigned",
                        payload={"from": previous, "to": None, "returned_to_base": True},
                    )
                )
            elif body.action == "archive":
                if lead.archived_at is not None:
                    continue
                await archive_lead(session, lead, search)
            elif body.action == "unarchive":
                if lead.archived_at is None:
                    continue
                await unarchive_lead(lead)
            elif body.action == "restore_contact":
                previous_status = lead.lead_status
                lead.lead_status = "new"
                lead.owner_user_id = None
                lead.next_touch_at = None
                lead.no_answer_count = 0
                session.add(
                    LeadActivity(
                        lead_id=lead.id,
                        user_id=current_user.id,
                        team_id=team_id,
                        kind="status",
                        payload={"from": previous_status, "to": "new", "restored_from_no_contact": True},
                    )
                )
            elif body.action == "delete":
                lead.deleted_at = now
            changed += 1
        await session.commit()
    return {"changed": changed, "found": len(rows)}
