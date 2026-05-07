from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import _JSONB, _UUID, Base, _utcnow


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("query_id", "source", "source_id", name="uq_leads_query_source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    query_id: Mapped[uuid.UUID] = mapped_column(
        _UUID(),
        ForeignKey("search_queries.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    website: Mapped[str | None] = mapped_column(String(512))
    phone: Mapped[str | None] = mapped_column(String(64))
    address: Mapped[str | None] = mapped_column(String(512))
    category: Mapped[str | None] = mapped_column(String(128))
    rating: Mapped[float | None] = mapped_column(Float)
    reviews_count: Mapped[int | None] = mapped_column(Integer)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(256), nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(_JSONB(), default=dict)

    # Enrichment / AI analysis fields (populated for top-N leads)
    enriched: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    score_ai: Mapped[float | None] = mapped_column(Float)
    tags: Mapped[list[str] | None] = mapped_column(_JSONB())
    summary: Mapped[str | None] = mapped_column(Text)
    advice: Mapped[str | None] = mapped_column(Text)
    strengths: Mapped[list[str] | None] = mapped_column(_JSONB())
    weaknesses: Mapped[list[str] | None] = mapped_column(_JSONB())
    red_flags: Mapped[list[str] | None] = mapped_column(_JSONB())
    website_meta: Mapped[dict[str, Any] | None] = mapped_column(_JSONB())
    social_links: Mapped[dict[str, str] | None] = mapped_column(_JSONB())
    reviews_summary: Mapped[str | None] = mapped_column(Text)
    score_components: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # CRM state — populated only when the lead is viewed/worked in the web UI.
    # Kept on the Lead row rather than a separate events table to keep the
    # CRM page reading from a single query; move to an event log once history
    # becomes a product feature.
    lead_status: Mapped[str] = mapped_column(
        String(16), default="new", nullable=False, index=True
    )
    owner_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)
    deal_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    rating_snapshots: Mapped[list | None] = mapped_column(JSON, nullable=True)
    last_touched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    # Soft-delete: hidden from the CRM but kept on disk so audit + the
    # blacklisted ``UserSeenLead`` row that references it stay valid.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    # Set when the user explicitly chose "delete and never show again".
    # Outlives ``deleted_at`` (which can be cleared to undelete) so the
    # forever-block survives an undo.
    blacklisted: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    query: Mapped[SearchQuery] = relationship(back_populates="leads")  # noqa: F821


class LeadMark(Base):
    """Per-user colour mark on a lead.

    Each user picks their own colour for their own reasons; the mark
    is invisible to every other user, even teammates working the same
    shared CRM. Use this for personal triage on top of the shared
    ``Lead.lead_status``.
    """

    __tablename__ = "lead_marks"
    __table_args__ = (
        UniqueConstraint("user_id", "lead_id", name="uq_lead_marks_user_lead"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        _UUID(),
        ForeignKey("leads.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    color: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class LeadTag(Base):
    """User-defined tag (chip) attached to leads.

    Personal when ``team_id`` is NULL; team-scoped when set so the
    whole team sees the same chip palette. ``name`` is unique within
    its owner so two members of a team can't end up with two
    conflicting "Ready to call" tags. The ``color`` is just a token
    the SPA maps to a real hex — the backend doesn't validate colours.
    """

    __tablename__ = "lead_tags"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "team_id", "name", name="uq_lead_tags_owner_name"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID(),
        ForeignKey("teams.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    color: Mapped[str] = mapped_column(
        String(16), default="slate", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class LeadTagAssignment(Base):
    """Many-to-many link between a Lead and a LeadTag.

    Composite PK so the same tag can't get attached twice in race-y
    upserts. CASCADE ondelete on both sides keeps the table clean
    when leads or tags get removed.
    """

    __tablename__ = "lead_tag_assignments"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        _UUID(),
        ForeignKey("leads.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        _UUID(),
        ForeignKey("lead_tags.id", ondelete="CASCADE"),
        primary_key=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class LeadStatus(Base):
    """Per-team lead status palette (replaces hard-coded enum for teams).

    Personal-mode searches (no team_id on parent SearchQuery) keep
    using the legacy hard-coded keys (new/contacted/replied/won/
    archived). For team-mode searches, ``Lead.lead_status`` MUST be
    one of the keys in this team's palette.

    The five default keys are seeded by migration 0028 so existing
    leads stay valid; the team owner can rename / recolor / reorder /
    add / remove freely afterwards.
    """

    __tablename__ = "lead_statuses"
    __table_args__ = (
        UniqueConstraint(
            "team_id", "key", name="uq_lead_statuses_team_key"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        _UUID(),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    color: Mapped[str] = mapped_column(
        String(16), default="slate", nullable=False
    )
    order_index: Mapped[int] = mapped_column(
        SmallInteger, default=0, nullable=False
    )
    is_terminal: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class LeadCustomField(Base):
    """User-defined extra column on a lead.

    Schemaless on purpose: the user types whatever ``key`` they want
    in the UI ("decision_maker", "deal_value", "next_step") and the
    value is stored as text. Scoped per (lead, user) so two members
    of a team can keep different notes on the same shared lead
    without overwriting each other.
    """

    __tablename__ = "lead_custom_fields"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        _UUID(),
        ForeignKey("leads.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "lead_id", "user_id", "key",
            name="uq_lead_custom_fields_owner_key",
        ),
    )


class LeadActivity(Base):
    """Append-only timeline event on a lead.

    ``kind`` ∈ {created, status, notes, assigned, mark, custom_field,
    task}. ``payload`` is kind-specific (e.g. ``{"from": "new",
    "to": "contacted"}`` for status changes). Used to render the per-
    lead timeline + the team activity feed.
    """

    __tablename__ = "lead_activities"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        _UUID(),
        ForeignKey("leads.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID(),
        ForeignKey("teams.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(_JSONB())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class LeadTask(Base):
    """Reminder / task attached to a lead.

    ``due_at`` may be NULL for "do this whenever" notes, but most
    rows will have it. ``done_at`` flips the moment the user ticks
    the checkbox; we keep the row instead of deleting so the activity
    log can reference completed work.
    """

    __tablename__ = "lead_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        _UUID(),
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class LeadSegment(Base):
    """Saved CRM filter bundle the user can apply with one click.

    ``filter_json`` is intentionally schema-less so the frontend can
    grow new filter axes without a migration. Today we round-trip
    {status, tag_ids, temp, smartFilter, search, sort}; tomorrow
    add ``score_min``, ``created_after`` etc. without touching SQL.

    Owned by a user, optionally scoped to a team. When ``team_id``
    is set everyone on the team can see the segment in their sidebar;
    when null it's private to the owner.
    """

    __tablename__ = "lead_segments"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID(),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    filter_json: Mapped[dict[str, Any]] = mapped_column(
        _JSONB(), default=dict, nullable=False
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class UserSeenLead(Base):
    """Per-user history of every (source, source_id) ever delivered.

    Lets us dedup results so re-running the same search (or an overlapping
    one) doesn't hand the same companies back to the user. The raw ``Lead``
    rows get deleted after each run for storage hygiene; this table is the
    lightweight long-lived memory.

    ``phone_e164`` and ``domain_root`` are dedup axes layered on top of
    the place-id key: the same business often appears under a slightly
    different Google listing (rebrand, address tweak, duplicate import),
    so matching by phone or website domain catches what the place-id
    miss.
    """

    __tablename__ = "user_seen_leads"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    phone_e164: Mapped[str | None] = mapped_column(String(32))
    domain_root: Mapped[str | None] = mapped_column(String(128))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
