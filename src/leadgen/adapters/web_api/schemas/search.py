"""Search-related request / response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

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

    The caller is the authenticated session — a legacy ``user_id``
    field in the payload is ignored.
    """

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

    The caller is the authenticated session — a legacy ``user_id``
    field in the payload is ignored.
    """

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


class NicheTaxonomyEntry(BaseModel):
    """Single suggestion returned by the public niche autocomplete."""

    id: str
    label: str
    category: str | None = None


class NicheTaxonomyResponse(BaseModel):
    """Response shape for ``GET /api/v1/niches`` (public autocomplete).

    Distinct from ``NicheSuggestionsResponse`` — that one runs Claude
    against the user's profile to *invent* niches; this one is a
    static dictionary lookup feeding the search-form combobox.
    """

    items: list[NicheTaxonomyEntry]
    query: str
    language: str


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


class SearchCreate(BaseModel):
    # The search owner is the authenticated session — a legacy
    # ``user_id`` field in the payload is ignored.
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
    limit: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description="Per-search lead cap. Caller picks 5/10/20/30/50; "
        "absent → server default (MAX_RESULTS_PER_QUERY). Bounded so "
        "a single search can't blow the AI budget.",
    )
    scope: str | None = Field(
        default=None,
        max_length=16,
        description="Geo shape: 'city' (default), 'metro' (city + radius), "
        "'state', or 'country'. Drives how the discovery query is "
        "built. Anything else falls back to 'city'.",
    )
    radius_km: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description="Radius in km when scope ∈ {city, metro}. Bounded "
        "to 100 km so locationRestriction stays cheap.",
    )
    enabled_sources: list[str] | None = Field(
        default=None,
        max_length=8,
        description="Per-search override: subset of "
        "{'google','osm','yelp','foursquare'} the user wants to query "
        "this run. Lets the caller skip a source that's hot-rate-limited "
        "today without rotating env vars. ``None`` (default) = honour "
        "the global *_ENABLED env flags. Empty list = silly, treated "
        "as ``None`` server-side.",
    )


class CityEntryResponse(BaseModel):
    id: str
    name: str
    country: str
    lat: float
    lon: float
    population: int


class CityListResponse(BaseModel):
    items: list[CityEntryResponse]
    query: str
    language: str


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
    archived_at: datetime | None = None


class SearchCreateResponse(BaseModel):
    id: uuid.UUID
    queued: bool = Field(
        ...,
        description="True = enqueued on arq/Redis. False = running inline in the "
        "API process via asyncio.create_task (works when Redis isn't configured).",
    )


class SavedSearchSchema(BaseModel):
    id: str
    name: str
    team_id: str | None
    niche: str
    region: str
    target_languages: list[str] | None
    scope: str
    radius_m: int | None
    max_results: int | None
    schedule: str | None
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_leads_count: int | None
    active: bool
    created_at: datetime
    updated_at: datetime


class SavedSearchListResponse(BaseModel):
    items: list[SavedSearchSchema]


class SavedSearchCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field(..., min_length=1, max_length=256)
    region: str = Field(..., min_length=1, max_length=256)
    target_languages: list[str] | None = None
    scope: str = Field("city", pattern=r"^(city|metro|state|country)$")
    radius_m: int | None = Field(default=None, ge=1000, le=200_000)
    max_results: int | None = Field(default=None, ge=1, le=100)
    # Off / daily / weekly / biweekly / monthly. ``None`` and
    # ``"off"`` are equivalent and mean "no auto-run".
    schedule: str | None = Field(default=None)
    team_id: str | None = None


class SavedSearchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    schedule: str | None = None
    active: bool | None = None
    max_results: int | None = Field(default=None, ge=1, le=100)
    radius_m: int | None = Field(default=None, ge=1000, le=200_000)


class DashboardStats(BaseModel):
    """Aggregate numbers for /app dashboard hero strip."""

    sessions_total: int
    sessions_running: int
    leads_total: int
    hot_total: int
    warm_total: int
    cold_total: int


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


class SearchPreflightResponse(BaseModel):
    blocked: bool
    matches: list[PriorTeamSearch] = Field(default_factory=list)


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
