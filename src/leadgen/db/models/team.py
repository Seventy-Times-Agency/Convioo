from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import _UUID, Base, _utcnow


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
