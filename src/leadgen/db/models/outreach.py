from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import _JSONB, _UUID, Base, _utcnow


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


class EmailSequence(Base):
    """User-defined follow-up email sequence (Day 1 / Day 3 / Day 7 ...)."""

    __tablename__ = "email_sequences"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(
        _JSONB(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class SequenceEnrollment(Base):
    """Lead enrolled in a sequence — tracks which step is next."""

    __tablename__ = "sequence_enrollments"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    sequence_id: Mapped[uuid.UUID] = mapped_column(
        _UUID(),
        ForeignKey("email_sequences.id", ondelete="CASCADE"),
        nullable=False,
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
        index=True,
    )
    current_step: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False
    )
    next_send_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
