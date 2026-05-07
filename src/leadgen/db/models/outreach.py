from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, _UUID, _utcnow


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
