"""Admin dashboard schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AdminTopUser(BaseModel):
    user_id: int
    name: str
    email: str | None
    plan: str
    queries_used: int
    is_admin: bool


class AdminOverview(BaseModel):
    """``GET /api/v1/admin/overview`` payload — high-level platform health."""

    users_total: int
    users_paid: int
    users_trialing: int
    teams_total: int
    searches_last_7d: int
    searches_running: int
    leads_last_7d: int
    failed_searches_last_24h: int
    top_users_by_searches: list[AdminTopUser]
    searches_today: int = 0
    leads_today: int = 0
    pipeline_value_usd: float = 0.0
    db_latency_ms: float = 0.0
    source_breakdown: dict[str, int] = {}


class SlowSearchEntry(BaseModel):
    """One row of the slowest-searches list on the admin quality dashboard."""

    search_id: str
    niche: str
    region: str
    duration_seconds: float
    leads_count: int
    status: str
    user_id: int | None
    finished_at: datetime | None


class AdminQuality(BaseModel):
    """``GET /api/v1/admin/quality`` payload — ops/quality metrics.

    The dashboard explicitly does NOT show MRR or revenue. Its job is
    to surface platform-quality signals: external-API health, error
    rates, queue depth, and the slowest searches that need attention.
    """

    # Anthropic spend (sourced from prometheus counters at scrape-time).
    anthropic_calls_total: int
    anthropic_calls_failed: int
    # Pessimistic estimate: $0.005 per Haiku call (~1.5k input + 700
    # output tokens at Haiku 4.5 rates). Off by 2-3x is fine — the
    # purpose is "is the bill spiking?", not invoice accuracy.
    anthropic_estimated_spend_usd: float

    # Search reliability (last 24h).
    searches_total_24h: int
    searches_failed_24h: int
    searches_failure_rate_24h: float

    # Queue health (instantaneous).
    queue_pending: int
    queue_running: int

    # Slowest searches (last 24h, top 10 by wall-clock duration).
    slowest_searches: list[SlowSearchEntry]
