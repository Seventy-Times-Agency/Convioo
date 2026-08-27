"""Outreach template schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OutreachTemplate(BaseModel):
    """User-managed reusable email / outreach boilerplate.

    Bodies may contain ``{name}`` / ``{niche}`` / ``{region}``
    placeholders; the frontend substitutes them when the user applies
    a template to a specific lead.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: int
    team_id: uuid.UUID | None
    name: str
    subject: str | None
    body: str
    tone: str
    created_at: datetime
    updated_at: datetime


class OutreachTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    subject: str | None = Field(default=None, max_length=255)
    body: str = Field(..., min_length=1, max_length=4000)
    tone: str = Field(default="professional", max_length=32)
    team_id: uuid.UUID | None = None


class OutreachTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    subject: str | None = Field(default=None, max_length=255)
    body: str | None = Field(default=None, min_length=1, max_length=4000)
    tone: str | None = Field(default=None, max_length=32)


class OutreachTemplateListResponse(BaseModel):
    items: list[OutreachTemplate]


class BulkDraftEmailRequest(BaseModel):
    """``POST /api/v1/leads/bulk-draft`` — generate cold-email drafts in batch.

    ``language`` overrides the email language for the whole batch
    ("ru" / "uk" / "en"); null means "follow the UI language".
    """

    lead_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=20)
    tone: str | None = Field(default="professional", max_length=32)
    extra_context: str | None = Field(default=None, max_length=400)
    language: str | None = Field(default=None, pattern="^(ru|uk|en)$")


class BulkDraftEmailItem(BaseModel):
    lead_id: uuid.UUID
    subject: str | None = None
    body: str | None = None
    error: str | None = None


class BulkDraftEmailResponse(BaseModel):
    items: list[BulkDraftEmailItem]
