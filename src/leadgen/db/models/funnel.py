"""Funnel — the central sales entity of a team.

A funnel defines HOW the team works its leads: the touch path (calls
and emails with day offsets), the call script, the email templates,
the no-answer rule, and the GOAL — a free-text target action with an
optional price and an on-reach behaviour. The sales rep's green
button renders from the funnel of the lead they're working, so the
product ships empty: every funnel, goal, price and script is data a
team enters through the UI, never code.

Leads are attached to a funnel in batches from the "База" panel; the
worker executes the touch path (auto emails on schedule, calls
returned to the rep's queue on their day).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import _JSONB, _UUID, Base, _utcnow

# Behaviour when a lead reaches the funnel's goal. Free-form goal
# NAME is any text the team wants; the ACTION is one of a fixed set
# the product knows how to execute.
GOAL_ACTIONS: tuple[str, ...] = (
    "payment_calendar",  # send payment link + calendar slot
    "invoice",           # send an invoice
    "booking",           # book a slot only
    "none",              # just mark the goal reached
)

FUNNEL_STATUSES: tuple[str, ...] = ("draft", "active", "archived")

STEP_KINDS: tuple[str, ...] = ("call", "email")


class Funnel(Base):
    """A team's named touch path + goal definition."""

    __tablename__ = "funnels"
    __table_args__ = (
        UniqueConstraint("team_id", "name", name="uq_funnels_team_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        _UUID(),
        ForeignKey("teams.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="draft", nullable=False
    )

    # Goal — the sales rep's green button. Name is free text ("Платный
    # аудит", "Демо", anything); price optional; action from
    # GOAL_ACTIONS.
    goal_name: Mapped[str] = mapped_column(String(200), nullable=False)
    goal_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    goal_action: Mapped[str] = mapped_column(
        String(32), default="none", nullable=False
    )

    # Call script shown to the rep in call mode. Plain text with the
    # team's own structure; versioning is the team's naming concern.
    script: Mapped[str | None] = mapped_column(Text)

    # No-answer rule: after ``no_answer_attempts`` failed calls on
    # different days → pause ``no_answer_pause_days`` days → lead
    # returns to the free pool.
    no_answer_attempts: Mapped[int] = mapped_column(
        Integer, default=3, nullable=False
    )
    no_answer_pause_days: Mapped[int] = mapped_column(
        Integer, default=14, nullable=False
    )

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    steps: Mapped[list[FunnelStep]] = relationship(
        back_populates="funnel",
        cascade="all, delete-orphan",
        order_by="FunnelStep.order_index",
    )


class FunnelStep(Base):
    """One touch on the path: a call or an email, N days after the
    lead entered the funnel."""

    __tablename__ = "funnel_steps"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    funnel_id: Mapped[uuid.UUID] = mapped_column(
        _UUID(),
        ForeignKey("funnels.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # Day offset from the PREVIOUS touch (mockup: "+1 день", "+3 дня").
    # First step is day 0 by convention.
    day_offset: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Emails only: send automatically on schedule (True) or queue a
    # draft for the rep's approval (False). Ignored for calls.
    auto: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Emails only: the outreach template to render.
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID(),
        ForeignKey("outreach_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Free note shown next to the step ("скрипт: холодный заход v2").
    note: Mapped[str | None] = mapped_column(String(300))
    extra: Mapped[dict[str, Any] | None] = mapped_column(_JSONB())

    funnel: Mapped[Funnel] = relationship(back_populates="steps")
