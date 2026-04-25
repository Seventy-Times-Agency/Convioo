"""Pydantic models for the web API's request/response bodies."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str
    db: bool
    commit: str


# ── Auth ────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=128)
    last_name: str = Field(..., min_length=1, max_length=128)


class LoginRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=128)
    last_name: str = Field(..., min_length=1, max_length=128)


class AuthUser(BaseModel):
    """Trimmed user payload returned to the SPA after register/login.

    No token yet — auth state lives in localStorage on the client until
    real session management lands. This is enough to scope API calls to
    the right ``user_id`` and to know whether the user has finished the
    onboarding questionnaire.
    """

    user_id: int
    first_name: str
    last_name: str
    onboarded: bool = False


# ── User profile (web onboarding) ───────────────────────────────────


class UserProfile(BaseModel):
    """Full personalisation profile that feeds Claude during analysis.

    Mirrors the fields the Telegram bot collects in its 6-step
    onboarding so web searches reach the same prompt quality.
    """

    user_id: int
    first_name: str
    last_name: str
    display_name: str | None
    age_range: str | None
    business_size: str | None
    profession: str | None
    service_description: str | None
    home_region: str | None
    niches: list[str] | None
    language_code: str | None
    onboarded: bool


class UserProfileUpdate(BaseModel):
    """PATCH payload for /api/v1/users/{id}. All fields optional.

    Sending ``service_description`` triggers a Claude normalisation pass
    on the server so ``profession`` ends up clean and short, matching
    what the Telegram bot stores.
    """

    display_name: str | None = Field(default=None, max_length=128)
    age_range: str | None = Field(default=None, max_length=16)
    business_size: str | None = Field(default=None, max_length=32)
    service_description: str | None = Field(default=None, max_length=2000)
    home_region: str | None = Field(default=None, max_length=200)
    niches: list[str] | None = Field(default=None, max_length=20)
    language_code: str | None = Field(default=None, max_length=8)


# ── Searches ────────────────────────────────────────────────────────


# Magic user id for open-demo web searches (no auth yet). Telegram ids
# start at 1, so 0 is free. Seeded by migration 20260424_0006.
WEB_DEMO_USER_ID: int = 0


class ConsultMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=2000)


class ConsultRequest(BaseModel):
    """One round-trip of the search-composer dialogue.

    The client owns the full conversation history and ships it on
    every turn so the backend stays stateless.
    """

    user_id: int
    messages: list[ConsultMessage] = Field(default_factory=list, max_length=40)


class ConsultResponse(BaseModel):
    reply: str
    niche: str | None = None
    region: str | None = None
    ideal_customer: str | None = None
    exclusions: str | None = None
    ready: bool = False


class SearchCreate(BaseModel):
    user_id: int = Field(
        default=WEB_DEMO_USER_ID,
        description="Telegram user id that owns the query. Web searches "
        "use the synthetic demo user (id=0) until auth lands.",
    )
    team_id: uuid.UUID | None = Field(
        default=None,
        description="When set, the search belongs to this team and "
        "appears in the shared CRM for every member. Caller must be "
        "a member; otherwise a 403 is returned.",
    )
    niche: str = Field(..., min_length=2, max_length=256)
    region: str = Field(..., min_length=2, max_length=256)
    language_code: str | None = Field(
        default=None,
        description="BCP-47 language hint for Google Places (e.g. 'en', 'uk').",
    )
    profession: str | None = Field(
        default=None,
        max_length=1000,
        description="What the caller sells — feeds Claude when it scores each lead.",
    )


class SearchSummary(BaseModel):
    id: uuid.UUID
    user_id: int
    niche: str
    region: str
    status: str
    source: str
    created_at: datetime
    finished_at: datetime | None
    leads_count: int
    avg_score: float | None
    hot_leads_count: int | None
    error: str | None
    insights: str | None = Field(
        default=None,
        description="High-level Claude summary for this search, pulled from "
        "analysis_summary['insights']. None until the run completes.",
    )


class SearchCreateResponse(BaseModel):
    id: uuid.UUID
    queued: bool = Field(
        ...,
        description="True = enqueued on arq/Redis. False = running inline in the "
        "API process via asyncio.create_task (works when Redis isn't configured).",
    )


# ── Leads ───────────────────────────────────────────────────────────


class LeadResponse(BaseModel):
    """What the web UI needs to render a lead card / detail modal / CRM row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    query_id: uuid.UUID

    name: str
    category: str | None
    address: str | None
    phone: str | None
    website: str | None
    rating: float | None
    reviews_count: int | None

    # Enrichment / AI
    score_ai: float | None
    tags: list[str] | None
    summary: str | None
    advice: str | None
    strengths: list[str] | None
    weaknesses: list[str] | None
    red_flags: list[str] | None
    social_links: dict[str, str] | None

    # CRM
    lead_status: str
    owner_user_id: int | None
    notes: str | None
    last_touched_at: datetime | None

    # Caller-specific colour mark (personal, never shared). Populated
    # on read by joining lead_marks on the requesting user_id.
    mark_color: str | None = None

    created_at: datetime


class LeadMarkRequest(BaseModel):
    """PUT /api/v1/leads/{id}/mark — set or clear the caller's mark.

    ``color`` null clears the mark. The colour string is opaque to the
    backend (the frontend hands out the swatch palette); we just store
    whatever short token we receive so users can extend later.
    """

    user_id: int
    color: str | None = Field(default=None, max_length=16)


class LeadUpdate(BaseModel):
    """PATCH payload for /api/v1/leads/{id}. All fields optional."""

    lead_status: str | None = Field(
        default=None,
        description="One of: new | contacted | replied | won | archived.",
    )
    owner_user_id: int | None = Field(
        default=None, description="Assignee user id. null clears the assignment."
    )
    notes: str | None = Field(default=None, max_length=10000)


class LeadListResponse(BaseModel):
    """Cross-session lead list for the /app/leads CRM page."""

    leads: list[LeadResponse]
    total: int
    sessions_by_id: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Map of session_id → {niche, region} so the CRM can show "
        "each row's parent session without a second round-trip.",
    )


# ── Dashboard stats ─────────────────────────────────────────────────


class DashboardStats(BaseModel):
    """Aggregate numbers for /app dashboard hero strip."""

    sessions_total: int
    sessions_running: int
    leads_total: int
    hot_total: int
    warm_total: int
    cold_total: int


# ── Teams + invites ─────────────────────────────────────────────────


class TeamMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    role: str
    initials: str
    color: str
    email: str | None = None
    last_active: str | None = None


class TeamSummary(BaseModel):
    """One team a user belongs to, with their role on it."""

    id: uuid.UUID
    name: str
    plan: str
    role: str
    member_count: int
    created_at: datetime


class TeamCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    owner_user_id: int


class TeamDetailResponse(BaseModel):
    id: uuid.UUID
    name: str
    plan: str
    created_at: datetime
    role: str  # the caller's role on this team
    members: list[TeamMemberResponse]


class InviteCreateRequest(BaseModel):
    by_user_id: int
    role: str = Field(default="member", max_length=32)
    ttl_seconds: int = Field(default=600, ge=60, le=86400)


class InviteResponse(BaseModel):
    """Invite payload shown to the owner who just generated it."""

    token: str
    team_id: uuid.UUID
    team_name: str
    role: str
    expires_at: datetime


class InvitePreview(BaseModel):
    """Limited preview a non-member sees before accepting."""

    team_id: uuid.UUID
    team_name: str
    role: str
    expires_at: datetime
    expired: bool
    accepted: bool


class InviteAcceptRequest(BaseModel):
    user_id: int


class TeamMemberSummary(BaseModel):
    """Owner-facing roll-up of one teammate's activity.

    Powers the "see each member's CRM" panel on the owner's team
    page; click a row and the workspace switches to viewing that
    member's data via ``member_user_id`` on the list endpoints.
    """

    user_id: int
    name: str
    role: str
    sessions_total: int
    leads_total: int
    hot_total: int
