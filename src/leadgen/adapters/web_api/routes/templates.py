"""``/api/v1/templates`` — user-managed outreach template library.

CRUD over ``OutreachTemplate``. Templates are personal (or team-scoped
when ``team_id`` is set on creation); listing unions personal +
team-visible. Carved out of ``app.py`` so the template surface lives
next to the rest of the CRM domain.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from leadgen.adapters.web_api.schemas import (
    OutreachTemplate as OutreachTemplateSchema,
)
from leadgen.adapters.web_api.schemas import (
    OutreachTemplateCreate,
    OutreachTemplateListResponse,
    OutreachTemplateUpdate,
)
from leadgen.db.models import OutreachTemplate
from leadgen.db.session import session_factory

router = APIRouter(tags=["templates"])


@router.get(
    "/api/v1/templates", response_model=OutreachTemplateListResponse
)
async def list_templates(
    user_id: int,
    team_id: uuid.UUID | None = None,
) -> OutreachTemplateListResponse:
    """User-managed outreach template library.

    Personal call returns only the caller's personal templates. Team
    call (team_id set) unions personal + every template scoped to
    that team — same pattern as memory / leads.
    """
    async with session_factory() as session:
        stmt = select(OutreachTemplate).where(
            OutreachTemplate.user_id == user_id
        )
        if team_id is not None:
            stmt = stmt.where(
                (OutreachTemplate.team_id == team_id)
                | (OutreachTemplate.team_id.is_(None))
            )
        else:
            stmt = stmt.where(OutreachTemplate.team_id.is_(None))
        stmt = stmt.order_by(OutreachTemplate.updated_at.desc())
        rows = (await session.execute(stmt)).scalars().all()
        items = [OutreachTemplateSchema.model_validate(r) for r in rows]
    return OutreachTemplateListResponse(items=items)


@router.post(
    "/api/v1/templates", response_model=OutreachTemplateSchema
)
async def create_template(
    body: OutreachTemplateCreate,
    user_id: int,
) -> OutreachTemplateSchema:
    """Create a new outreach template owned by ``user_id``."""
    async with session_factory() as session:
        row = OutreachTemplate(
            user_id=user_id,
            team_id=body.team_id,
            name=body.name.strip(),
            subject=(body.subject or "").strip() or None,
            body=body.body.strip(),
            tone=(body.tone or "professional").strip().lower() or "professional",
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return OutreachTemplateSchema.model_validate(row)


@router.patch(
    "/api/v1/templates/{template_id}",
    response_model=OutreachTemplateSchema,
)
async def update_template(
    template_id: uuid.UUID,
    body: OutreachTemplateUpdate,
    user_id: int,
) -> OutreachTemplateSchema:
    async with session_factory() as session:
        row = await session.get(OutreachTemplate, template_id)
        if row is None or row.user_id != user_id:
            raise HTTPException(status_code=404, detail="template not found")
        data = body.model_dump(exclude_unset=True)
        if "name" in data and data["name"]:
            row.name = data["name"].strip()
        if "subject" in data:
            row.subject = (data["subject"] or "").strip() or None
        if "body" in data and data["body"]:
            row.body = data["body"].strip()
        if "tone" in data and data["tone"]:
            row.tone = data["tone"].strip().lower()
        row.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(row)
        return OutreachTemplateSchema.model_validate(row)


@router.delete("/api/v1/templates/{template_id}")
async def delete_template(
    template_id: uuid.UUID,
    user_id: int,
) -> dict[str, bool]:
    async with session_factory() as session:
        row = await session.get(OutreachTemplate, template_id)
        if row is None or row.user_id != user_id:
            raise HTTPException(status_code=404, detail="template not found")
        await session.delete(row)
        await session.commit()
    return {"deleted": True}
