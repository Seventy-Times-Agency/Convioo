from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, _JSONB, _UUID, _utcnow


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

    user: Mapped["User"] = relationship(back_populates="queries")
    leads: Mapped[list["Lead"]] = relationship(
        back_populates="query", cascade="all, delete-orphan"
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
