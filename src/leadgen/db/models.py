from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import CHAR, TypeDecorator


class _JSONB(TypeDecorator):
    """JSONB in Postgres, plain JSON everywhere else (SQLite test harness)."""

    impl = JSONB
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class _UUID(TypeDecorator):
    """UUID in Postgres, CHAR(36) in SQLite so unit tests don't need pg."""

    impl = UUID
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is None or dialect.name == "postgresql":
            return value
        return str(value)

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if value is None or dialect.name == "postgresql":
            return value
        return uuid.UUID(value)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    # Telegram user id fits into BIGINT
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    email: Mapped[str | None] = mapped_column(String(255))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    language_code: Mapped[str | None] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    queries_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    queries_limit: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    # User profile — filled during onboarding, used to personalize AI advice
    display_name: Mapped[str | None] = mapped_column(String(64))
    age_range: Mapped[str | None] = mapped_column(String(16))
    # Optional. One of: 'male' | 'female' | 'other'. Drives Henry's
    # grammatical agreement (он/она) — never used for any kind of
    # filtering or personalisation beyond that.
    gender: Mapped[str | None] = mapped_column(String(16))
    business_size: Mapped[str | None] = mapped_column(String(32))
    profession: Mapped[str | None] = mapped_column(Text)
    service_description: Mapped[str | None] = mapped_column(Text)
    home_region: Mapped[str | None] = mapped_column(String(200))
    niches: Mapped[list[str] | None] = mapped_column(_JSONB())
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    queries: Mapped[list[SearchQuery]] = relationship(back_populates="user")


class SearchQuery(Base):
    __tablename__ = "search_queries"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID(),
        ForeignKey("teams.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    niche: Mapped[str] = mapped_column(String(256), nullable=False)
    region: Mapped[str] = mapped_column(String(256), nullable=False)
    target_languages: Mapped[list[str] | None] = mapped_column(_JSONB())
    status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False, index=True
    )
    # Where the search was launched from. Drives post-run cleanup: Telegram
    # searches purge Lead rows after delivery to keep storage tight, web
    # searches keep them so the CRM can show them.
    source: Mapped[str] = mapped_column(
        String(16), default="telegram", nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    leads_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)

    # Aggregated analytics produced after enrichment
    avg_score: Mapped[float | None] = mapped_column(Float)
    hot_leads_count: Mapped[int | None] = mapped_column(Integer)
    analysis_summary: Mapped[dict[str, Any] | None] = mapped_column(_JSONB())

    user: Mapped[User] = relationship(back_populates="queries")
    leads: Mapped[list[Lead]] = relationship(
        back_populates="query", cascade="all, delete-orphan"
    )


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
    last_touched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    query: Mapped[SearchQuery] = relationship(back_populates="leads")


class Team(Base):
    """A workspace that multiple users share.

    Every user belongs to at least one team (their personal one created
    on signup). Agencies / small squads use teams to share a quota
    bucket, a lead-history pool and a CRM board. Nothing else in the
    product depends on teams yet — this is the seam for the web UI
    and the future paid tiers.
    """

    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    plan: Mapped[str] = mapped_column(String(32), default="free", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    # Quota lives on the team so a 5-seat agency shares 30 searches/mo
    # rather than each seat getting their own bucket.
    queries_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    queries_limit: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    memberships: Mapped[list[TeamMembership]] = relationship(
        back_populates="team", cascade="all, delete-orphan"
    )


class TeamMembership(Base):
    """Join table between ``User`` and ``Team``, carrying the member's role.

    Roles today: ``owner`` (billing + admin), ``member`` (run searches),
    ``viewer`` (read-only client-share view). Role logic lives in
    TeamService once the web API needs it.
    """

    __tablename__ = "team_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "team_id", name="uq_membership_user_team"),
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
    team_id: Mapped[uuid.UUID] = mapped_column(
        _UUID(),
        ForeignKey("teams.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(32), default="member", nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    team: Mapped[Team] = relationship(back_populates="memberships")


class TeamInvite(Base):
    """Short-lived invite token an owner hands a prospective teammate.

    The owner generates one via ``POST /teams/{id}/invites``; the
    backend returns a URL containing ``token``. Anyone holding the URL
    can claim it via ``POST /teams/invites/{token}/accept`` while
    ``expires_at`` is in the future and ``accepted_at`` is null. After
    acceptance both columns are stamped and the row is effectively
    spent — re-using the same URL fails with a clear error.
    """

    __tablename__ = "team_invites"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        _UUID(),
        ForeignKey("teams.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(32), default="member", nullable=False)
    token: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    created_by_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    accepted_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TeamSeenLead(Base):
    """Per-team fingerprint of every (source, source_id) ever returned.

    Mirrors ``UserSeenLead`` but at team granularity: when a search
    runs in team mode, the pipeline filters Google Maps results
    against this table so the same place never appears in two
    teammates' CRMs. ``first_user_id`` and ``first_seen_at`` record
    who claimed the lead first, useful for the "already in team"
    breadcrumb on the UI.
    """

    __tablename__ = "team_seen_leads"

    team_id: Mapped[uuid.UUID] = mapped_column(
        _UUID(),
        ForeignKey("teams.id", ondelete="CASCADE"),
        primary_key=True,
    )
    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    first_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


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


class EmailVerificationToken(Base):
    """Short-lived single-use token for email verification or password reset.

    ``kind`` discriminates the purpose so future flows (password
    reset, email-change) reuse the same table. ``used_at`` flips the
    moment the user clicks the link, making the token spent.
    """

    __tablename__ = "email_verification_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(16), default="verify", nullable=False)
    token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pending_email: Mapped[str | None] = mapped_column(String(255))


class AssistantMemory(Base):
    """Persistent memory for the floating Henry assistant.

    Two kinds of entries:
    - ``summary`` — Henry's distilled recap of a recent dialogue
      session (1-3 sentences). Written every N user messages.
    - ``fact`` — a single durable fact extracted from the dialogue
      (e.g. "продаёт SEO для дантистов в Берлине", "целевой
      сегмент — премиум-стоматологии"). Written alongside summaries.

    A row is scoped to a user and optionally to a team:
    - ``team_id`` IS NULL → personal-mode memory (only the user sees it).
    - ``team_id`` IS NOT NULL → team-scoped memory; available to every
      member of the team so Henry can coordinate (e.g. owner notes
      about the team strategy).
    """

    __tablename__ = "assistant_memories"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID(),
        ForeignKey("teams.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict[str, Any] | None] = mapped_column(_JSONB())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class UserSeenLead(Base):
    """Per-user history of every (source, source_id) ever delivered.

    Lets us dedup results so re-running the same search (or an overlapping
    one) doesn't hand the same companies back to the user. The raw ``Lead``
    rows get deleted after each run for storage hygiene; this table is the
    lightweight long-lived memory.
    """

    __tablename__ = "user_seen_leads"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class OutreachTemplate(Base):
    """Reusable cold-email / follow-up / breakup template.

    Each row is owned by a user; team_id is optional and lets a team
    owner publish templates the whole team sees. ``tone`` mirrors the
    enum used by ``draft-email`` so Henry can adapt the same template
    across registers; ``body`` is plain text with optional ``{name}`` /
    ``{niche}`` / ``{region}`` placeholders that the apply-on-lead
    flow substitutes when the user copies the template into a real
    outreach.
    """

    __tablename__ = "outreach_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID(),
        ForeignKey("teams.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    tone: Mapped[str] = mapped_column(
        String(32), default="professional", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
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


class UserAuditLog(Base):
    """Append-only audit trail of security-relevant user actions.

    Captures sign-in, profile updates, GDPR exports, account deletions,
    team-membership changes, etc. The ``ip`` column is best-effort —
    populated from request headers when available, NULL otherwise.
    """

    __tablename__ = "user_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(256))
    payload: Mapped[dict[str, Any] | None] = mapped_column(_JSONB())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class UserEmailAccount(Base):
    """OAuth-linked mailbox a user can send outreach through.

    Provider is currently always ``"google"`` (Gmail send scope) — the
    column is kept generic so Microsoft/Outlook can plug in later. One
    user may connect multiple addresses; ``(user_id, provider, email)``
    is unique.
    """

    __tablename__ = "user_email_accounts"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "provider", "email", name="uq_user_email_account"
        ),
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
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    scopes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    access_token: Mapped[str | None] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    token_encrypted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserKnowledgeFile(Base):
    """A user-uploaded document (PDF or text) Henry uses as context.

    The binary itself is discarded after extraction — we keep the
    plain-text rendering in ``content_text`` since that's the only
    thing the prompts ever see. Stored per-user; rendered into a
    compact block at prompt-build time, capped at ~5000 chars so
    even multi-PDF users stay under model context limits.
    """

    __tablename__ = "user_knowledge_files"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class LeadFeedback(Base):
    """A user's "this lead is / isn't a fit" verdict.

    Unique per (user_id, lead_id) — voting again replaces the prior
    verdict, never appends. Verdicts are surfaced in the AI scoring +
    cold-email prompts so Claude can mirror the user's actual taste
    instead of generic ICP heuristics.
    """

    __tablename__ = "lead_feedback"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "lead_id", name="uq_lead_feedback_user_lead"
        ),
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
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
