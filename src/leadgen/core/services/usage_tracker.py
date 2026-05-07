"""Per-user, per-service API usage tracker.

Convioo's variable cost is dominated by Google Places (Text Search +
Place Details) and Anthropic Claude. This module gives the rest of
the codebase a single, no-fuss API for *recording* a billable call
and *aggregating* what a given user has spent during a window — so
the admin dashboard can spot a runaway tenant before the monthly
Google invoice does.

Design choices:

* **No new DB migration.** Storage is the existing cache backend —
  Redis when ``REDIS_URL`` is set, otherwise the in-process dict
  shim from ``leadgen.utils.cache``. Counters are namespaced by
  ``(user_id, service, day_bucket)`` so a 30-day window is a small
  range scan in either tier.
* **Context-scoped user id.** Collectors don't take a user-id
  parameter today and we don't want to thread it through every
  call site. ``set_active_user(...)`` writes into a
  :class:`contextvars.ContextVar` that the recorder reads — async
  tasks inherit the value automatically.
* **Cost is computed once, here.** Pricing is centralised in
  ``UNIT_COST_USD`` so a Google SKU change is a one-line edit, not
  a hunt across collectors.

Usage is fire-and-forget: any error is logged and swallowed —
billing telemetry must not break the user-facing search.
"""

from __future__ import annotations

import contextvars
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from leadgen.utils import cache as _cache

logger = logging.getLogger(__name__)


# Pricing as of 2026-05 (per Google Maps Platform pricing + Anthropic
# Claude Haiku 4.5 list price). Adjust here when SKUs move.
#
# Google Places (New) "Pro" SKU pricing is $0.025 per Text Search
# request and $0.020 per Place Details request when reviews are not
# requested. Reviews bump it to the Enterprise SKU at $0.028 — we
# always request reviews, so 0.028 is the right number for us today.
#
# Anthropic Haiku 4.5 list pricing: $1 / MTok input, $5 / MTok
# output, $0.10 / MTok cache read (90% off input), $1.25 / MTok
# cache write (25% premium for the first creation).
UNIT_COST_USD: dict[str, float] = {
    "google_text_search": 0.025,
    "google_place_details": 0.028,
    "claude_input_tokens": 1.0 / 1_000_000,
    "claude_output_tokens": 5.0 / 1_000_000,
    "claude_cache_read_tokens": 0.10 / 1_000_000,
    "claude_cache_write_tokens": 1.25 / 1_000_000,
}

# Keep counters for ~35 days so a calendar-month rollup always has
# the data it needs even with timezone wiggle.
_USAGE_TTL_SEC = 35 * 24 * 60 * 60

# 30-day lookback for "monthly" aggregates. Calendar-month math is
# noisy across DST and short months — a rolling window is closer to
# what an operator actually wants when triaging "who blew up our
# bill today".
_MONTH_WINDOW_DAYS = 30

# ContextVar so collectors don't have to grow user_id parameters.
_ACTIVE_USER: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "convioo_active_user", default=None
)


@dataclass(slots=True)
class UsageSummary:
    """Aggregated usage for a (user, window) pair."""

    user_id: str
    window: str
    units_by_service: dict[str, int]
    cost_usd_by_service: dict[str, float]
    total_cost_usd: float


def set_active_user(user_id: str | int | None) -> contextvars.Token[str | None]:
    """Bind the current async context to ``user_id``.

    Returns a token the caller can pass to :func:`reset_active_user`
    to restore the previous value (typical pattern: ``try/finally``
    around a search run).
    """
    value = str(user_id) if user_id is not None else None
    return _ACTIVE_USER.set(value)


def reset_active_user(token: contextvars.Token[str | None]) -> None:
    _ACTIVE_USER.reset(token)


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _bucket_keys(user_id: str, service: str, days: int) -> list[str]:
    """Return the cache keys covering the trailing ``days`` for one user/service."""
    today = datetime.now(timezone.utc)
    keys = []
    for i in range(days):
        day = today.fromordinal(today.toordinal() - i)
        keys.append(f"{user_id}:{service}:{day.strftime('%Y%m%d')}")
    return keys


async def record(service: str, units: int = 1) -> None:
    """Record ``units`` of ``service`` against the active user.

    Silently no-ops when no user is bound to the context (e.g. a
    one-off CLI run or a webhook delivery firing outside a request).
    Errors in the cache backend are logged at debug and swallowed —
    we never want billing telemetry to break a search.
    """
    if units <= 0:
        return
    user_id = _ACTIVE_USER.get()
    if not user_id:
        return
    key = f"{user_id}:{service}:{_today_key()}"
    try:
        existing = await _cache.get_json("usage", key)
        current = int(existing) if isinstance(existing, (int, float)) else 0
        await _cache.set_json("usage", key, current + units, _USAGE_TTL_SEC)
    except Exception as exc:  # noqa: BLE001 — telemetry must never raise
        logger.debug("usage_tracker.record swallowed err=%s", exc)


async def record_claude_usage(usage_obj: Any) -> None:
    """Pull token counts off an Anthropic ``Usage`` object and record them.

    The SDK exposes ``input_tokens``, ``output_tokens``, and the two
    cache fields ``cache_creation_input_tokens`` /
    ``cache_read_input_tokens`` once prompt caching is in play. Each
    is recorded under its own service slug so cost aggregation can
    apply the right per-token price.
    """
    if usage_obj is None:
        return
    pairs = (
        ("claude_input_tokens", "input_tokens"),
        ("claude_output_tokens", "output_tokens"),
        ("claude_cache_write_tokens", "cache_creation_input_tokens"),
        ("claude_cache_read_tokens", "cache_read_input_tokens"),
    )
    for service, attr in pairs:
        value = getattr(usage_obj, attr, 0) or 0
        if value:
            await record(service, int(value))


async def get_user_usage(
    user_id: str | int, *, window: str = "today"
) -> UsageSummary:
    """Aggregate one user's usage for ``today`` or ``month`` (rolling 30d)."""
    uid = str(user_id)
    days = 1 if window == "today" else _MONTH_WINDOW_DAYS
    units: dict[str, int] = {}
    for service in UNIT_COST_USD:
        total = 0
        for key in _bucket_keys(uid, service, days):
            try:
                value = await _cache.get_json("usage", key)
                if isinstance(value, (int, float)):
                    total += int(value)
            except Exception as exc:  # noqa: BLE001
                logger.debug("usage_tracker.get swallowed err=%s", exc)
        if total:
            units[service] = total
    cost = {
        service: round(count * UNIT_COST_USD.get(service, 0.0), 6)
        for service, count in units.items()
    }
    return UsageSummary(
        user_id=uid,
        window=window,
        units_by_service=units,
        cost_usd_by_service=cost,
        total_cost_usd=round(sum(cost.values()), 4),
    )
