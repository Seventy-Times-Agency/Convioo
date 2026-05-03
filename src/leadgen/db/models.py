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
    SmallInteger,
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
    # Stamped when the user finishes (or explicitly skips) the in-app
    # 4-step product tour. NULL = the tour will auto-open on next
    # ``/app`` visit; from Settings the user can clear it back to NULL
    # to replay the tour.
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    # Account recovery: optional secondary mailbox the user trusts to
    # always reach them, used by the forgot-email flow to remind them
    # which address their account is registered under.
    recovery_email: Mapped[str | None] = mapped_column(String(255))
    # Brute-force lockout state. ``failed_login_attempts`` resets to 0
    # on every successful login; once it reaches the lockout threshold
    # ``locked_until`` is stamped and login is refused (with the same
    # generic error message) until that time passes.
    failed_login_attempts: Mapped[int] = mapped_column(
        SmallInteger, default=0, nullable=False
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    # Platform-admin flag. Gates ``/api/v1/admin/*`` and the
    # ``/app/admin`` page. Promoted via SQL on Railway — no in-app
    # UI for granting it on day one.
    is_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Stripe link. ``stripe_customer_id`` is set on first checkout so
    # subsequent portal launches and webhook lookups don't need a
    # users-by-email scan. ``plan`` mirrors the active Stripe product
    # ("free" / "pro" / "agency") and ``plan_until`` is the current
    # period-end; both move from webhook events. ``trial_ends_at`` is
    # stamped at registration to grant a 14-day preview that bypasses
    # the quota check.
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64))
    plan: Mapped[str] = mapped_column(
        String(32), default="free", nullable=False
    )
    plan_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    trial_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

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
    # Per-search cap. Null → use the global ``MAX_RESULTS_PER_QUERY``
    # default. Bounded server-side so a single search can't blow the
    # AI budget; SmallInt is plenty for the 5..100 range.
    max_results: Mapped[int | None] = mapped_column(SmallInteger)
    # Geo shape — drives how the discovery query is built.
    # ``city`` (default) and ``metro`` use a circular locationBias
    # centered on ``center_*``; ``state`` and ``country`` use a bbox
    # from Nominatim. Older rows pre-migration default to ``city``.
    scope: Mapped[str] = mapped_column(
        String(16), default="city", nullable=False
    )
    radius_m: Mapped[int | None] = mapped_column(Integer)
    center_lat: Mapped[float | None] = mapped_column(Float)
    center_lon: Mapped[float | None] = mapped_column(Float)
    # Per-search source override. Subset of {google, osm, yelp,
    # foursquare} — NULL means "honour the global *_ENABLED env flags",
    # which is the default. Empty list normalised to NULL upstream so
    # the pipeline only ever sees None or a real subset.
    enabled_sources: Mapped[list[str] | None] = mapped_column(_JSONB())
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
    phone_e164: Mapped[str | None] = mapped_column(String(32))
    domain_root: Mapped[str | None] = mapped_column(String(128))
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


class AffiliateCode(Base):
    """Public slug a partner shares to attribute signups to themselves.

    The ``code`` IS the primary key — it's what shows up in the public
    URL ``/r/{code}``. ``percent_share`` is a hint for the (future)
    Stripe revenue-share automation; today it's just metadata.
    """

    __tablename__ = "affiliate_codes"

    code: Mapped[str] = mapped_column(
        String(64), primary_key=True, index=False
    )
    owner_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str | None] = mapped_column(String(128))
    percent_share: Mapped[int] = mapped_column(
        SmallInteger, default=30, nullable=False
    )
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Referral(Base):
    """One row per signup that arrived through an ``AffiliateCode``.

    ``referred_user_id`` is unique so re-using a different /r/ URL
    can't double-count the same human. ``first_paid_at`` will be
    stamped by the Stripe webhook handler when the referred user
    becomes a paying customer.
    """

    __tablename__ = "referrals"
    __table_args__ = (
        UniqueConstraint(
            "referred_user_id", name="uq_referrals_referred_user"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("affiliate_codes.code", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    referred_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    signed_up_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    first_paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


class UserIntegrationCredential(Base):
    """Encrypted credentials for an outbound provider (Notion / Gmail / etc).

    One row per (user, provider). ``token_ciphertext`` holds the
    Fernet-encrypted upstream token; the ``config`` JSONB carries
    provider-specific settings (e.g. Notion's ``database_id``).
    The plaintext token is never persisted — even a full DB dump
    leaks nothing that an attacker can replay.
    """

    __tablename__ = "user_integration_credentials"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "provider", name="uq_user_integration_owner_provider"
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
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    token_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict[str, Any] | None] = mapped_column(_JSONB())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class UserApiKey(Base):
    """Long-lived bearer token a user issues to themselves.

    Plaintext is shown once at creation and never persisted. ``token_hash``
    is the SHA-256 of the token; ``token_preview`` is a non-sensitive
    prefix/suffix stub for the UI ("convioo_pk_abc…xyz") so the user
    can recognise which key they're looking at without leaking it.
    """

    __tablename__ = "user_api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False
    )
    token_preview: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


class UserSession(Base):
    """A live login on a single device.

    The opaque session token (32 bytes of secrets.token_urlsafe) is
    stored ONLY in the user's httpOnly cookie. The DB keeps the
    SHA-256 hash so a database leak doesn't yield active sessions.

    ``device_fingerprint`` is SHA-256(user_agent || ip_subnet/24);
    it lets the login flow detect "first time we see this device" and
    fire a security-alert email without storing the raw IP forever.
    """

    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False
    )
    device_fingerprint: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


class Webhook(Base):
    """Outbound webhook subscription owned by a single user.

    On a registered event, the dispatcher POSTs JSON to ``target_url``
    and includes ``X-Convioo-Signature: sha256=<hex>``, the HMAC-SHA256
    of the body using ``secret``. Five consecutive failures auto-flip
    ``active`` to false so a dead URL stops retrying forever.
    """

    __tablename__ = "webhooks"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    secret: Mapped[str] = mapped_column(String(128), nullable=False)
    event_types: Mapped[list[str]] = mapped_column(
        _JSONB(), nullable=False, default=list
    )
    description: Mapped[str | None] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    failure_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    last_delivery_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_delivery_status: Mapped[int | None] = mapped_column(SmallInteger)
    last_failure_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_failure_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class StripeEvent(Base):
    """Idempotency log for processed Stripe webhook events.

    Stripe retries delivery on any non-2xx, so a successful upgrade
    that times out on the response can show up again. Inserting the
    event id with a unique PK lets us reject the second copy with a
    cheap ``IntegrityError`` instead of double-applying it.
    """

    __tablename__ = "stripe_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class OAuthCredential(Base):
    """Encrypted OAuth tokens for outbound providers (Gmail / Outlook).

    One row per (user, provider). Both access_token and refresh_token
    are Fernet-encrypted; ``expires_at`` is stamped when we exchange
    the auth code so refresh-on-demand can decide whether the access
    token is still alive. Scope is recorded so we can re-prompt the
    user if the integration ever needs broader permissions.
    """

    __tablename__ = "oauth_credentials"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "provider", name="uq_oauth_owner_provider"
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
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    access_token_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_ciphertext: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    scope: Mapped[str | None] = mapped_column(Text)
    account_email: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
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


class SavedSearch(Base):
    """A bookmarked search query, optionally recurring on a schedule.

    The schedule field is a coarse label ("daily", "weekly",
    "biweekly", "monthly") rather than a cron expression — keeps the
    UI dropdown matching what we store, and the worker job consults
    only ``next_run_at`` so cron parsing stays out of the hot path.
    """

    __tablename__ = "saved_searches"

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
    niche: Mapped[str] = mapped_column(String(256), nullable=False)
    region: Mapped[str] = mapped_column(String(256), nullable=False)
    target_languages: Mapped[list[str] | None] = mapped_column(_JSONB())
    scope: Mapped[str] = mapped_column(
        String(16), default="city", nullable=False
    )
    radius_m: Mapped[int | None] = mapped_column(Integer)
    max_results: Mapped[int | None] = mapped_column(SmallInteger)
    schedule: Mapped[str | None] = mapped_column(String(16))
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_leads_count: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
