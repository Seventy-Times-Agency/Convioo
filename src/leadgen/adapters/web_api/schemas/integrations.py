"""Integration schemas: Notion, HubSpot, Pipedrive, Gmail, Outlook, API keys."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

# ── Notion ───────────────────────────────────────────────────────────

class NotionIntegrationStatus(BaseModel):
    """Read-only view of a saved Notion connection.

    Token is never echoed — only a masked stub for UI display so an
    XSS leak doesn't yield the upstream secret.
    """

    connected: bool
    token_preview: str | None = None
    database_id: str | None = None
    workspace_name: str | None = None
    owner_email: str | None = None
    auth_type: str | None = None  # "oauth" | "internal" | None
    updated_at: datetime | None = None


class NotionAuthorizeResponse(BaseModel):
    url: str
    state: str


class NotionDatabase(BaseModel):
    """One row in the database picker after OAuth install."""

    id: str
    title: str
    icon: str | None = None
    url: str | None = None


class NotionDatabaseList(BaseModel):
    items: list[NotionDatabase]


class NotionConnectRequest(BaseModel):
    """Internal-token path: supply both token + database_id."""

    token: str = Field(..., min_length=10, max_length=200)
    database_id: str = Field(..., min_length=10, max_length=128)


class NotionSetDatabaseRequest(BaseModel):
    """OAuth path: token already saved; just set/update the database_id."""

    database_id: str = Field(..., min_length=10, max_length=128)


class NotionExportRequest(BaseModel):
    """``POST /api/v1/leads/export-to-notion`` — push selected leads."""

    lead_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=200)


class NotionExportItem(BaseModel):
    lead_id: uuid.UUID
    notion_url: str | None = None
    error: str | None = None


class NotionExportResponse(BaseModel):
    items: list[NotionExportItem]
    success_count: int
    failure_count: int


# ── HubSpot ──────────────────────────────────────────────────────────

class HubspotIntegrationStatus(BaseModel):
    """Read-only view of a saved HubSpot OAuth connection.

    Tokens are never echoed (encrypted at rest); only the portal id
    and a masked preview of the access token are surfaced to the UI.
    """

    connected: bool
    portal_id: int | None = None
    account_email: str | None = None
    scope: str | None = None
    expires_at: datetime | None = None


class HubspotAuthorizeResponse(BaseModel):
    url: str
    state: str


class HubspotExportRequest(BaseModel):
    """``POST /api/v1/leads/export-to-hubspot`` — push selected leads."""

    lead_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=200)


class HubspotExportItem(BaseModel):
    lead_id: uuid.UUID
    contact_id: str | None = None
    error: str | None = None


class HubspotExportResponse(BaseModel):
    items: list[HubspotExportItem]
    success_count: int
    failure_count: int


# ── Pipedrive ────────────────────────────────────────────────────────

class PipedriveIntegrationStatus(BaseModel):
    """Read-only view of a saved Pipedrive OAuth connection."""

    connected: bool
    api_domain: str | None = None
    account_email: str | None = None
    scope: str | None = None
    expires_at: datetime | None = None
    default_pipeline_id: int | None = None
    default_stage_id: int | None = None


class PipedriveAuthorizeResponse(BaseModel):
    url: str
    state: str


class PipedriveConfigUpdate(BaseModel):
    """``PUT /api/v1/integrations/pipedrive/config``."""

    default_pipeline_id: int = Field(..., ge=1)
    default_stage_id: int = Field(..., ge=1)


class PipedriveStageView(BaseModel):
    id: int
    name: str
    pipeline_id: int
    order_nr: int


class PipedrivePipelineView(BaseModel):
    id: int
    name: str
    stages: list[PipedriveStageView] = Field(default_factory=list)


class PipedrivePipelinesResponse(BaseModel):
    items: list[PipedrivePipelineView]


class PipedriveExportRequest(BaseModel):
    lead_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=200)


class PipedriveExportItem(BaseModel):
    lead_id: uuid.UUID
    person_id: str | None = None
    deal_id: str | None = None
    error: str | None = None


class PipedriveExportResponse(BaseModel):
    items: list[PipedriveExportItem]
    success_count: int
    failure_count: int


# ── Gmail ────────────────────────────────────────────────────────────

class GmailIntegrationStatus(BaseModel):
    """``GET /api/v1/oauth/gmail`` payload."""

    connected: bool
    account_email: str | None = None
    scope: str | None = None
    expires_at: datetime | None = None


class GmailAuthorizeResponse(BaseModel):
    """``GET /api/v1/oauth/gmail/authorize`` payload — frontend redirects here."""

    url: str
    state: str


class GmailSendRequest(BaseModel):
    """``POST /api/v1/leads/{id}/send-email`` body."""

    subject: str = Field(..., min_length=1, max_length=255)
    body: str = Field(..., min_length=1, max_length=20000)
    # Optional: caller can override the recipient (e.g. when the lead
    # has multiple addresses on file). Defaults to the lead's primary
    # email picked up from ``Lead.email``.
    to: str | None = Field(default=None, max_length=255)
    # Which provider to send through. Defaults to "gmail" for backwards
    # compatibility with callers that predate the Outlook integration.
    provider: str | None = Field(default=None, pattern="^(gmail|outlook)$")


class GmailSendResponse(BaseModel):
    """Returned after a successful send — Gmail's message id."""

    message_id: str
    thread_id: str | None = None
    sent_at: datetime


# ── Outlook ──────────────────────────────────────────────────────────

class OutlookIntegrationStatus(BaseModel):
    """``GET /api/v1/oauth/outlook`` payload — mirrors Gmail."""

    connected: bool
    account_email: str | None = None
    scope: str | None = None
    expires_at: datetime | None = None


class OutlookAuthorizeResponse(BaseModel):
    """``GET /api/v1/oauth/outlook/authorize`` payload — SPA redirects here."""

    url: str
    state: str


# ── API keys ─────────────────────────────────────────────────────────

class ApiKeySchema(BaseModel):
    """Read-only view of an issued API key (no plaintext token)."""

    id: uuid.UUID
    label: str | None
    token_preview: str
    created_at: datetime
    last_used_at: datetime | None
    revoked: bool


class ApiKeyListResponse(BaseModel):
    items: list[ApiKeySchema]


class ApiKeyCreateRequest(BaseModel):
    label: str | None = Field(default=None, max_length=128)


class ApiKeyCreatedResponse(BaseModel):
    """One-time response that includes the plaintext token.

    The SPA must show this to the user immediately and warn that it
    won't be retrievable later. Subsequent reads only return the
    masked preview.
    """

    id: uuid.UUID
    token: str
    label: str | None
    token_preview: str
    created_at: datetime


# ── Webhooks ─────────────────────────────────────────────────────────

class WebhookSchema(BaseModel):
    """Read-only view of a webhook subscription. The plaintext secret
    is shown only once at creation; subsequent reads expose a short
    preview so the user can recognise it without leaking the full
    value."""

    id: uuid.UUID
    target_url: str
    event_types: list[str]
    description: str | None
    active: bool
    failure_count: int
    secret_preview: str
    last_delivery_at: datetime | None
    last_delivery_status: int | None
    last_failure_at: datetime | None
    last_failure_message: str | None
    created_at: datetime


class WebhookListResponse(BaseModel):
    items: list[WebhookSchema]


class WebhookCreateRequest(BaseModel):
    target_url: str = Field(..., min_length=10, max_length=2048)
    event_types: list[str] = Field(..., min_length=1, max_length=20)
    description: str | None = Field(default=None, max_length=200)


class WebhookCreatedResponse(WebhookSchema):
    """One-time payload that exposes the plaintext secret."""

    secret: str


class WebhookUpdateRequest(BaseModel):
    target_url: str | None = Field(default=None, min_length=10, max_length=2048)
    event_types: list[str] | None = Field(default=None, min_length=1, max_length=20)
    description: str | None = Field(default=None, max_length=200)
    active: bool | None = None


# ── Affiliate ────────────────────────────────────────────────────────

class AffiliateCodeSchema(BaseModel):
    code: str
    name: str | None = None
    percent_share: int
    active: bool
    created_at: datetime
    referrals_count: int = 0
    paid_referrals_count: int = 0


class AffiliateCodeCreateRequest(BaseModel):
    """``POST /api/v1/affiliate/codes``.

    Empty ``code`` lets the server generate a random slug; otherwise
    the caller picks (constrained to URL-safe characters).
    """

    code: str | None = Field(default=None, min_length=3, max_length=64)
    name: str | None = Field(default=None, max_length=128)


class AffiliateCodeUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    active: bool | None = None


class AffiliateOverview(BaseModel):
    """``GET /api/v1/affiliate`` — per-user dashboard payload."""

    codes: list[AffiliateCodeSchema]
    total_referrals: int
    total_paid_referrals: int
