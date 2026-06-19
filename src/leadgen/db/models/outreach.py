from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
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


class EmailDailySend(Base):
    """Per-day outbound counter that powers warmup + anti-spam caps.

    One row per (user, send_date). The daily ceiling is not stored here
    — it is derived from how long the user's sending mailbox has been
    connected (warmup ramp), so the same counter row works regardless
    of which cap applies on a given day. The send path increments
    ``sent_count`` and refuses to send once it reaches the computed cap.
    """

    __tablename__ = "email_daily_sends"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "send_date", name="uq_email_daily_sends_user_date"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    send_date: Mapped[date] = mapped_column(Date, nullable=False)
    sent_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class EmailMessage(Base):
    """One synced email (inbound or outbound) from a connected mailbox.

    Powers the unified Inbox. Threads are derived by grouping on
    ``(user_id, provider, provider_thread_id)``; the unique constraint on
    the provider message id makes the sync idempotent (upsert on re-fetch).
    ``lead_id`` is best-effort matched by counterpart email so a thread can
    deep-link into the CRM. ``headers`` keeps Message-ID / In-Reply-To /
    References so a reply can be threaded correctly by the provider.
    """

    __tablename__ = "email_messages"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "provider",
            "provider_message_id",
            name="uq_email_messages_provider_msg",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    account_email: Mapped[str | None] = mapped_column(String(320))
    provider_thread_id: Mapped[str] = mapped_column(
        String(256), nullable=False, index=True
    )
    provider_message_id: Mapped[str] = mapped_column(
        String(256), nullable=False
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID(),
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    from_email: Mapped[str | None] = mapped_column(String(320))
    to_email: Mapped[str | None] = mapped_column(String(320))
    subject: Mapped[str | None] = mapped_column(String(998))
    snippet: Mapped[str | None] = mapped_column(String(512))
    body_text: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    message_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    headers: Mapped[dict[str, Any] | None] = mapped_column(_JSONB())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
