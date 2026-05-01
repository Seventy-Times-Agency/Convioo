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
    email: str = Field(..., min_length=4, max_length=255)
    password: str = Field(..., min_length=8, max_length=200)
    age_range: str | None = Field(default=None, max_length=16)
    gender: str | None = Field(default=None, max_length=16)
    # Invite code. When REGISTRATION_PASSWORD env var is set on the
    # server, this MUST match — otherwise registration is rejected.
    # Lets the founder keep the public-facing site closed while still
    # demoing the product to invited people.
    registration_password: str | None = Field(default=None, max_length=200)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=4, max_length=255)
    password: str = Field(..., min_length=1, max_length=200)


class VerifyEmailRequest(BaseModel):
    token: str = Field(..., min_length=8, max_length=128)


class ResendVerificationRequest(BaseModel):
    email: str = Field(..., min_length=4, max_length=255)


class ChangeEmailRequest(BaseModel):
    """Initiate an email change. Requires the current password to
    confirm the request actually came from the signed-in user."""

    new_email: str = Field(..., min_length=4, max_length=255)
    password: str = Field(..., min_length=1, max_length=200)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=200)
    new_password: str = Field(..., min_length=8, max_length=200)


class AuthUser(BaseModel):
    """Trimmed user payload returned to the SPA after register/login.

    The session JWT is set as an httpOnly cookie by the backend. The
    JSON payload only carries the data the SPA needs to render: who
    the user is, whether their email is verified (gates search
    creation), and whether they finished onboarding.
    """

    user_id: int
    first_name: str
    last_name: str
    email: str | None = None
    email_verified: bool = False
    onboarded: bool = False
    # Set by /auth/register and /users/{id}/change-email so the SPA
    # can surface "we couldn't send the verification email — try resend".
    # ``None`` on /auth/login (no email was attempted in this request).
    verification_email_sent: bool | None = None


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
    gender: str | None
    business_size: str | None
    profession: str | None
    service_description: str | None
    home_region: str | None
    niches: list[str] | None
    language_code: str | None
    onboarded: bool
    # Search quota — surfaced on the dashboard as a progress bar so
    # users see how close they are to the limit before they hit it.
    queries_used: int = 0
    queries_limit: int = 0


class UserProfileUpdate(BaseModel):
    """PATCH payload for /api/v1/users/{id}. All fields optional.

    Sending ``service_description`` triggers a Claude normalisation pass
    on the server so ``profession`` ends up clean and short, matching
    what the Telegram bot stores.
    """

    display_name: str | None = Field(default=None, max_length=128)
    age_range: str | None = Field(default=None, max_length=16)
    gender: str | None = Field(default=None, max_length=16)
    business_size: str | None = Field(default=None, max_length=32)
    # Cap at 800 chars — Pydantic rejects with a clear 422 if the user
    # bypasses the frontend counter, and the DB column is now TEXT
    # (migration 0017) so there's no silent overflow at the SQL layer.
    service_description: str | None = Field(default=None, max_length=800)
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
    every turn so the backend stays stateless. ``current_*`` fields
    carry the slot values the frontend already shows in the form so
    Claude doesn't re-extract from scratch and accidentally
    overwrite settled answers with stray phrases from the latest
    user reply.
    """

    user_id: int
    messages: list[ConsultMessage] = Field(default_factory=list, max_length=40)
    current_niche: str | None = None
    current_region: str | None = None
    current_ideal_customer: str | None = None
    current_exclusions: str | None = None
    last_asked_slot: str | None = Field(
        default=None,
        description="Slot Henry was waiting on after his previous turn — "
        "one of niche/region/ideal_customer/exclusions. Echoed back so "
        "Henry can map the user's reply to the right slot instead of "
        "guessing.",
    )


class ConsultResponse(BaseModel):
    reply: str
    niche: str | None = None
    region: str | None = None
    ideal_customer: str | None = None
    exclusions: str | None = None
    ready: bool = False
    last_asked_slot: str | None = None


class PendingAction(BaseModel):
    """A mutation Henry has proposed and is asking the user to confirm.

    Confirm-before-write flow: instead of mutating profile/team state
    silently, Henry returns a list of ``PendingAction`` items. The
    frontend renders them inline ("Записать в профиль: …") and the
    user either clicks confirm/cancel or types «да» / «нет» in chat.
    On the next turn the client echoes ``pending_actions`` back and
    the backend keyword-detects confirmation and applies them.

    ``kind`` ∈ {"profile_patch", "team_description", "member_description"}.
    ``payload`` is kind-specific — validated by the action applier
    rather than the schema, so we can extend without churning Pydantic.
    ``summary`` is the 1-line human description shown next to the
    confirm/cancel buttons.
    """

    kind: str = Field(..., max_length=64)
    summary: str = Field(..., max_length=400)
    payload: dict[str, Any] = Field(default_factory=dict)


class AssistantRequest(BaseModel):
    """One round-trip of the floating in-product assistant chat.

    ``team_id`` flips Henry into team-context mode: he gets the team
    description + per-member descriptions in his system prompt and
    drops the personal-profile-edit ability.

    ``pending_actions`` is the list Henry returned on his previous
    turn — echoed back by the client so the backend can detect a
    one-word confirmation from the user and apply the actions.
    """

    user_id: int
    team_id: uuid.UUID | None = None
    messages: list[ConsultMessage] = Field(default_factory=list, max_length=40)
    awaiting_field: str | None = Field(
        default=None,
        description="Profile / team field Henry was waiting on after his "
        "previous turn. Echoed back so Henry maps a short reply to that "
        "field instead of guessing — e.g. user says 'Berlin' answering "
        "a region question, not a niche.",
    )
    pending_actions: list[PendingAction] | None = Field(
        default=None,
        max_length=10,
        description="Actions Henry proposed last turn that the user "
        "may now confirm or refuse with a short reply.",
    )


class AssistantMemberDescription(BaseModel):
    user_id: int
    description: str


class AssistantResponse(BaseModel):
    """Response shape for the floating assistant chat.

    ``pending_actions`` — what Henry wants to write but hasn't yet,
    awaiting user confirmation in the chat.
    ``applied_actions`` — what was just applied this turn (because
    the user confirmed actions that came in via the request).
    """

    reply: str
    mode: str = "personal"  # personal | team_member | team_owner
    suggestion_summary: str | None = None
    awaiting_field: str | None = None
    pending_actions: list[PendingAction] | None = None
    applied_actions: list[PendingAction] | None = None


class AssistantMemoryItem(BaseModel):
    """One row from the assistant memory store, surfaced for transparency."""

    id: uuid.UUID
    kind: str
    content: str
    team_id: uuid.UUID | None
    created_at: datetime


class AssistantMemoryListResponse(BaseModel):
    items: list[AssistantMemoryItem]


class AssistantMemoryDeleteResponse(BaseModel):
    deleted: int


class NicheSuggestionsResponse(BaseModel):
    """Niche options Henry proposes for the user's profile.

    Driven off ``service_description`` (or ``profession`` as a
    fallback). Already-saved niches are excluded server-side so the
    list always shows fresh ideas.
    """

    suggestions: list[str]


class SearchAxisOption(BaseModel):
    """One ready-to-launch search configuration Henry proposes.

    Surfaced on /app/search as a card the user can one-click into
    the form. ``rationale`` is the short "why" that goes under the
    card — keeps the choice intentional, not arbitrary.
    """

    niche: str
    region: str
    ideal_customer: str | None = None
    exclusions: str | None = None
    rationale: str | None = None


class SearchAxesResponse(BaseModel):
    options: list[SearchAxisOption]


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


class LeadCustomField(BaseModel):
    """User-defined extra column on a lead."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lead_id: uuid.UUID
    user_id: int
    key: str
    value: str | None
    updated_at: datetime


class LeadCustomFieldUpsert(BaseModel):
    key: str = Field(..., min_length=1, max_length=64)
    value: str | None = Field(default=None, max_length=2000)


class LeadCustomFieldsResponse(BaseModel):
    items: list[LeadCustomField]


class LeadActivity(BaseModel):
    """One row from the lead timeline."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lead_id: uuid.UUID
    user_id: int
    team_id: uuid.UUID | None
    kind: str
    payload: dict[str, Any] | None = None
    created_at: datetime


class LeadActivityListResponse(BaseModel):
    items: list[LeadActivity]


class LeadTask(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lead_id: uuid.UUID
    user_id: int
    content: str
    due_at: datetime | None
    done_at: datetime | None
    created_at: datetime


class LeadTaskCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)
    due_at: datetime | None = None


class LeadTaskUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=1000)
    due_at: datetime | None = None
    # Send {"done": true} to mark complete, {"done": false} to reopen.
    done: bool | None = None


class LeadTaskListResponse(BaseModel):
    items: list[LeadTask]


class DecisionMaker(BaseModel):
    """One decision-maker contact extracted from a lead's website."""

    name: str
    role: str | None = None
    email: str | None = None
    linkedin: str | None = None


class DecisionMakersResponse(BaseModel):
    items: list[DecisionMaker] = Field(default_factory=list)


class CsvImportRow(BaseModel):
    """One row of a CSV upload — minimum is ``name``.

    ``website`` and ``region`` give the AI scorer something to lean
    on. Any other column parsed from the CSV ends up under
    ``extras`` (key → value text) and is preserved as custom fields
    on the resulting lead.
    """

    name: str = Field(..., min_length=1, max_length=512)
    website: str | None = Field(default=None, max_length=512)
    region: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=64)
    category: str | None = Field(default=None, max_length=128)
    extras: dict[str, str] = Field(default_factory=dict)


class CsvImportRequest(BaseModel):
    """JSON-shaped CSV import body.

    The browser parses the CSV client-side and ships parsed rows
    here so the server doesn't need a multipart route.
    """

    user_id: int = Field(default=WEB_DEMO_USER_ID)
    team_id: uuid.UUID | None = None
    label: str = Field(
        default="CSV import",
        min_length=1,
        max_length=120,
        description="What to call the synthetic search session this "
        "import lands under (shows up in /app/sessions).",
    )
    rows: list[CsvImportRow] = Field(..., min_length=1, max_length=500)


class CsvImportResponse(BaseModel):
    search_id: uuid.UUID
    inserted: int
    skipped: int


class CsvMappingSuggestRequest(BaseModel):
    """Hand a few CSV column headers + sample cells to Claude for mapping.

    The browser parses the file and sends the first row of headers plus
    up to 3 sample rows so the AI can see "Company / Org / Brand" labels
    matched against actual values like "Acme Inc" and confidently map
    them to the canonical CsvImportRow fields.
    """

    headers: list[str] = Field(..., min_length=1, max_length=64)
    samples: list[list[str]] = Field(default_factory=list, max_length=5)


class CsvMappingSuggestion(BaseModel):
    """Per-header AI suggestion."""

    header: str
    field: str  # "name" | "website" | "region" | "phone" | "category" | "extras" | "skip"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class CsvMappingSuggestResponse(BaseModel):
    items: list[CsvMappingSuggestion]
    used_ai: bool


class LeadFeedbackRequest(BaseModel):
    """Record / update a fit / not-fit verdict for one lead."""

    user_id: int = Field(..., ge=0)
    verdict: str = Field(..., min_length=2, max_length=16)
    reason: str | None = Field(default=None, max_length=500)


class LeadFeedbackResponse(BaseModel):
    lead_id: uuid.UUID
    verdict: str
    reason: str | None = None


class ICPFeedbackExample(BaseModel):
    verdict: str
    lead_name: str
    lead_category: str | None = None
    lead_address: str | None = None
    reason: str | None = None


class ICPSnapshotResponse(BaseModel):
    fit_count: int
    not_fit_count: int
    recent_examples: list[ICPFeedbackExample]


class WeeklyCheckinResponse(BaseModel):
    """Henry's read on the user's recent CRM activity.

    Surfaced as a dashboard card — ``summary`` is the paragraph,
    ``highlights`` are the punchy one-liner chips.
    """

    summary: str
    highlights: list[str] = Field(default_factory=list)
    leads_total: int
    hot_total: int
    new_this_week: int
    untouched_14d: int
    sessions_this_week: int


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
    target_languages: list[str] | None = Field(
        default=None,
        description="Optional list of BCP-47 language codes the lead "
        "should operate in (e.g. ['ru','uk'] to keep only Russian / "
        "Ukrainian-speaking businesses). Filters Google Maps results "
        "with a script heuristic and feeds the AI scorer.",
        max_length=10,
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

    # Best-known contact email for outreach. Populated on read by
    # picking the first non-generic address from website_meta.emails.
    # NOT persisted as a column — derived view.
    email: str | None = None

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


class LeadBulkUpdateRequest(BaseModel):
    """PATCH /api/v1/leads/bulk — apply the same change to many leads.

    Either ``lead_status`` or ``mark_color`` (or both) must be set.
    ``mark_color`` null clears the caller's mark across all rows.
    """

    user_id: int
    lead_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=500)
    lead_status: str | None = Field(default=None, max_length=16)
    set_mark_color: bool = Field(
        default=False,
        description="When true, ``mark_color`` is applied (including "
        "null = clear). When false, marks are left untouched.",
    )
    mark_color: str | None = Field(default=None, max_length=16)


class LeadBulkUpdateResponse(BaseModel):
    updated: int


class LeadEmailDraftRequest(BaseModel):
    """POST body for /leads/{id}/draft-email — Henry writes a cold email.

    ``tone`` ∈ {"professional", "casual", "bold"} (default professional).
    ``extra_context`` lets the salesperson add a one-liner like
    "they just opened a new branch" so the model can lean on it.
    ``deep_research`` triggers a fresh website re-fetch + Claude
    extraction of notable facts before the email prompt runs, so the
    opener can quote something specific the lead actually has on their
    site instead of leaning on cached enrichment.
    """

    user_id: int
    tone: str = Field(default="professional", max_length=32)
    extra_context: str | None = Field(default=None, max_length=600)
    deep_research: bool = False
    # When true, ask Claude for two distinct openers in one call so the
    # user can A/B test reply rates. Adds ~30% to the email-prompt cost
    # but halves Henry's per-test request count.
    with_variant: bool = False


class LeadEmailVariant(BaseModel):
    subject: str
    body: str


class LeadEmailDraftResponse(BaseModel):
    subject: str
    body: str
    tone: str
    # Surfaced when deep_research=true so the UI can show the user
    # what Henry leaned on while writing the email.
    notable_facts: list[str] = Field(default_factory=list)
    recent_signal: str | None = None
    # When the request had with_variant=true, the second alternative
    # opener for A/B testing. None when single-variant was requested.
    variant_b: LeadEmailVariant | None = None


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
    description: str | None = None
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
    description: str | None = None
    plan: str
    created_at: datetime
    role: str  # the caller's role on this team
    members: list[TeamMemberResponse]


class TeamUpdateRequest(BaseModel):
    """Owner-only PATCH for the team's editable fields."""

    by_user_id: int
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class MembershipUpdateRequest(BaseModel):
    """Owner-only PATCH for one teammate's description / role.

    Sets the short note Henry uses to introduce the member to the
    rest of the team ("Анна — закрывает стоматологии в EU").
    """

    by_user_id: int
    description: str | None = Field(default=None, max_length=1000)
    role: str | None = Field(default=None, max_length=32)


class PriorTeamSearch(BaseModel):
    """One earlier search in this team that already covered the
    same niche+region — surfaced by the preflight endpoint so the
    UI can hard-block a duplicate run."""

    search_id: uuid.UUID
    user_id: int
    user_name: str
    niche: str
    region: str
    leads_count: int
    created_at: datetime


class SearchPreflightResponse(BaseModel):
    blocked: bool
    matches: list[PriorTeamSearch] = Field(default_factory=list)


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


class AuditLogEntry(BaseModel):
    """Single row from ``user_audit_logs`` for the profile page."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action: str
    ip: str | None = None
    user_agent: str | None = None
    payload: dict[str, Any] | None = None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogEntry]


class AccountDeleteRequest(BaseModel):
    """Confirmation payload for account deletion.

    The user types their email into the modal; we compare against the
    stored value before purging anything.
    """

    confirm_email: str = Field(..., min_length=3, max_length=320)
    password: str | None = Field(default=None, max_length=200)


class AccountDeleteResponse(BaseModel):
    deleted: bool


# ── Email integrations (Google OAuth + Gmail send) ──────────────────


class ConnectedEmailAccount(BaseModel):
    id: str
    provider: str
    email: str
    display_name: str | None = None
    connected_at: datetime
    revoked: bool = False


class IntegrationsStatusResponse(BaseModel):
    """What the SPA needs to render the Settings → Integrations panel."""

    google_configured: bool
    accounts: list[ConnectedEmailAccount]


class IntegrationConnectStartResponse(BaseModel):
    authorize_url: str


class LeadSendEmailRequest(BaseModel):
    """Outbound email sent through the user's Gmail account."""

    user_id: int = Field(..., ge=0)
    account_id: str | None = Field(default=None, max_length=64)
    subject: str = Field(..., min_length=1, max_length=512)
    body: str = Field(..., min_length=1, max_length=20000)
    # Override the recipient. When omitted, the lead's primary email
    # (``leads.email``) is used.
    to: str | None = Field(default=None, max_length=255)
    # Which side of an A/B test this send corresponds to. Logged into
    # LeadActivity.payload so the analytics dashboard can compute reply
    # rates per variant. None when the user didn't run an A/B test.
    variant: str | None = Field(default=None, max_length=2)


class LeadSendEmailResponse(BaseModel):
    sent: bool
    message_id: str | None = None
    thread_id: str | None = None
    error: str | None = None


class LeadDuplicateMatch(BaseModel):
    """One previously-seen lead that fingerprints to the same business."""

    lead_id: uuid.UUID
    session_id: uuid.UUID
    session_niche: str
    session_region: str
    session_created_at: datetime
    matched_on: str  # "phone" | "domain"


class LeadDuplicatesResponse(BaseModel):
    """Cross-session matches surfaced in the lead detail view."""

    items: list[LeadDuplicateMatch]
