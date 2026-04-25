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
    language_code: Mapped[str | None] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    queries_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    queries_limit: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    # User profile — filled during onboarding, used to personalize AI advice
    display_name: Mapped[str | None] = mapped_column(String(64))
    age_range: Mapped[str | None] = mapped_column(String(16))
    business_size: Mapped[str | None] = mapped_column(String(32))
    profession: Mapped[str | None] = mapped_column(String(200))
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
    niche: Mapped[str] = mapped_column(String(256), nullable=False)
    region: Mapped[str] = mapped_column(String(256), nullable=False)
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    team: Mapped[Team] = relationship(back_populates="memberships")


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
