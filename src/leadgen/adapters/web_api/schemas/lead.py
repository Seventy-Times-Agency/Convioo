"""Lead-related request / response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Imported here to avoid circular imports with search.py
_WEB_DEMO_USER_ID: int = 0


class LeadTagSchema(BaseModel):
    """One user-defined tag (chip) attached to leads."""

    id: uuid.UUID
    name: str
    color: str
    team_id: uuid.UUID | None = None


class LeadTagListResponse(BaseModel):
    items: list[LeadTagSchema]


class LeadTagCreate(BaseModel):
    """``POST /api/v1/tags`` — create a tag for personal or team use."""

    name: str = Field(..., min_length=1, max_length=64)
    color: str | None = Field(default=None, max_length=16)
    team_id: uuid.UUID | None = None


class LeadTagUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    color: str | None = Field(default=None, max_length=16)


class LeadTagsAssignRequest(BaseModel):
    """Replace the lead's tag set with this exact list of tag ids."""

    tag_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)


class LeadStatusSchema(BaseModel):
    """One row in a team's lead-status palette."""

    id: uuid.UUID
    key: str
    label: str
    color: str
    order_index: int
    is_terminal: bool


class LeadStatusListResponse(BaseModel):
    items: list[LeadStatusSchema]


class LeadStatusCreate(BaseModel):
    key: str = Field(..., min_length=1, max_length=32)
    label: str = Field(..., min_length=1, max_length=64)
    color: str | None = Field(default=None, max_length=16)
    is_terminal: bool = False


class LeadStatusUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=64)
    color: str | None = Field(default=None, max_length=16)
    order_index: int | None = Field(default=None, ge=0, le=999)
    is_terminal: bool | None = None


class LeadStatusReorderRequest(BaseModel):
    """Bulk reorder — payload is the desired ordered list of ids."""

    ordered_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=50)


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


class LeadSegmentSchema(BaseModel):
    id: str
    name: str
    team_id: str | None
    filter_json: dict[str, Any]
    sort_order: int
    created_at: datetime
    updated_at: datetime


class LeadSegmentListResponse(BaseModel):
    items: list[LeadSegmentSchema]


class LeadSegmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    filter_json: dict[str, Any] = Field(default_factory=dict)
    team_id: str | None = None
    sort_order: int = 0


class LeadSegmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    filter_json: dict[str, Any] | None = None
    sort_order: int | None = None


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
    score_components: dict | None = None
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
    deal_value: float | None = None
    last_touched_at: datetime | None

    # Caller-specific colour mark (personal, never shared). Populated
    # on read by joining lead_marks on the requesting user_id.
    mark_color: str | None = None
    # Resolved colour + label of the lead's status from the team's
    # palette (for team-mode leads). Personal-mode leads get the
    # default-palette resolution. Empty when the lead's status doesn't
    # match any palette row (legacy / orphaned data).
    lead_status_color: str | None = None
    lead_status_label: str | None = None
    # User-defined tag chips (distinct from ``tags`` above which holds
    # the AI-generated hot/warm/cold/size labels). Populated by the
    # /api/v1/leads list endpoint when tags are joined in.
    user_tags: list[LeadTagSchema] = Field(default_factory=list)

    # ``archived_at`` is null for active CRM rows, set for rows in
    # the Archive zone (see ``leadgen.core.services.lead_archive``).
    # Frontend uses it to render the restore action and to badge
    # archived rows when they're surfaced via search results.
    archived_at: datetime | None = None

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


class LeadEmailDraftResponse(BaseModel):
    subject: str
    body: str
    tone: str
    # Surfaced when deep_research=true so the UI can show the user
    # what Henry leaned on while writing the email.
    notable_facts: list[str] = Field(default_factory=list)
    recent_signal: str | None = None


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
    deal_value: float | None = Field(default=None, ge=0)


class LeadListResponse(BaseModel):
    """Cross-session lead list for the /app/leads CRM page."""

    leads: list[LeadResponse]
    total: int
    sessions_by_id: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Map of session_id → {niche, region} so the CRM can show "
        "each row's parent session without a second round-trip.",
    )


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

    user_id: int = Field(default=_WEB_DEMO_USER_ID)
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
