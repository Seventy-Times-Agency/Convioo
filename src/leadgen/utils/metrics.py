"""Prometheus metrics definitions.

Kept in one module so call sites stay lean: ``from leadgen.utils.metrics
import searches_total`` and go. The ``/metrics`` HTTP endpoint scrapes
``prometheus_client.REGISTRY`` which automatically collects everything
declared here.

Naming convention: ``leadgen_<domain>_<what>`` + unit suffix.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ── Search pipeline ─────────────────────────────────────────────────────────
searches_total = Counter(
    "leadgen_searches_total",
    "Total searches started, labelled by terminal status.",
    labelnames=("status",),  # done | failed | timeout | no_results | rate_limited
)

search_duration_seconds = Histogram(
    "leadgen_search_duration_seconds",
    "End-to-end wall time of a search, from confirm to delivered.",
    buckets=(5, 10, 20, 30, 60, 90, 120, 180, 300, 600),
)

leads_discovered_total = Counter(
    "leadgen_leads_discovered_total",
    "Raw leads returned by a collector before dedup/filter.",
    labelnames=("source",),
)

leads_persisted_total = Counter(
    "leadgen_leads_persisted_total",
    "Leads written to the DB after dedup against user_seen_leads.",
)

leads_skipped_total = Counter(
    "leadgen_leads_skipped_total",
    "Leads skipped at the persist step.",
    labelnames=("reason",),  # duplicate | closed_business | missing_source_id
)

# ── External APIs ───────────────────────────────────────────────────────────
external_api_calls_total = Counter(
    "leadgen_external_api_calls_total",
    "Outbound API calls.",
    labelnames=("api", "status"),  # api: google_places_search | google_places_details | website | anthropic
)

external_api_duration_seconds = Histogram(
    "leadgen_external_api_duration_seconds",
    "Outbound API latency.",
    labelnames=("api",),
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30),
)

# ── Bot UX ──────────────────────────────────────────────────────────────────
messages_received_total = Counter(
    "leadgen_messages_received_total",
    "Telegram messages/callbacks handled.",
    labelnames=("kind",),  # message | callback
)

rate_limited_total = Counter(
    "leadgen_rate_limited_total",
    "Actions rejected by the per-user rate limiter.",
    labelnames=("action",),  # search | message
)

active_background_tasks = Gauge(
    "leadgen_active_background_tasks",
    "Searches currently running in the background.",
)
