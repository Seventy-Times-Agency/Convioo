"""Lightweight async cache for collector results.

Backed by Redis when ``REDIS_URL`` is set, otherwise an in-process
TTL'd dict. Either way the API is the same — call sites don't have
to branch on whether Redis is available.

We use this for two things today:

* **Geocode results** (``geocode_region``) — Nominatim is shared
  infrastructure with soft rate limits, and the same niche/city
  combos get queried over and over once a few users overlap.
* **Place details** (Google Places) — these hit the Enterprise SKU
  on Google's side, so a 7-day cache pays for itself fast.

Cache values are JSON-encoded; non-JSON-serialisable inputs raise on
write. Misses (and any Redis failure) return ``None`` — callers fall
back to the live lookup.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from typing import Any

from leadgen.config import get_settings

logger = logging.getLogger(__name__)


# 7 days for coords (city boundaries shift slowly), 14 days for
# place details (rating + reviews drift, but not catastrophically —
# the enrichment pipeline is rerun on the lead the next time the
# user reopens it).
GEOCODE_TTL_SEC = 7 * 24 * 60 * 60
PLACE_DETAILS_TTL_SEC = 14 * 24 * 60 * 60


_INMEM: dict[str, tuple[float, str]] = {}
_REDIS: Any = None
_REDIS_LOCK = asyncio.Lock()
_REDIS_FAILED = False  # don't keep retrying after the first connect failure


async def _redis() -> Any | None:
    """Return a cached redis-asyncio client, or None if unavailable.

    We import lazily so the module loads in environments without
    ``redis`` installed (local dev, tests). ``REDIS_URL`` empty also
    means we stay on the in-process dict.
    """
    global _REDIS, _REDIS_FAILED
    if _REDIS_FAILED:
        return None
    if _REDIS is not None:
        return _REDIS
    settings = get_settings()
    if not settings.redis_url:
        return None
    async with _REDIS_LOCK:
        if _REDIS is not None:
            return _REDIS
        try:
            from redis.asyncio import Redis  # type: ignore[import-not-found]

            _REDIS = Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=2.0,
                socket_timeout=2.0,
            )
            # Cheap probe — surfaces auth / DNS failures before the
            # first real cache call.
            await _REDIS.ping()
        except Exception as exc:  # noqa: BLE001 — degrade gracefully
            logger.warning("cache: redis unavailable, falling back to in-memory: %s", exc)
            _REDIS = None
            _REDIS_FAILED = True
            return None
    return _REDIS


def _ns(namespace: str, key: str) -> str:
    return f"convioo:{namespace}:{key}"


async def get_json(namespace: str, key: str) -> Any | None:
    """Return the cached JSON value, or ``None`` on miss / decode error."""
    full = _ns(namespace, key)
    redis = await _redis()
    if redis is not None:
        try:
            raw = await redis.get(full)
        except Exception as exc:  # noqa: BLE001
            logger.debug("cache.get redis failure key=%s err=%s", full, exc)
            raw = None
        if raw is not None:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None
    # Fall back to the in-memory tier (also acts as the only tier
    # when Redis is unset).
    cached = _INMEM.get(full)
    if cached is None:
        return None
    expires_at, raw = cached
    if expires_at < time.time():
        _INMEM.pop(full, None)
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def set_json(
    namespace: str, key: str, value: Any, ttl_sec: int
) -> None:
    """Store ``value`` under ``namespace/key`` for ``ttl_sec`` seconds."""
    if ttl_sec <= 0:
        return
    full = _ns(namespace, key)
    try:
        raw = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as exc:
        logger.warning("cache.set: not JSON-serialisable key=%s err=%s", full, exc)
        return
    redis = await _redis()
    if redis is not None:
        try:
            await redis.set(full, raw, ex=ttl_sec)
            return
        except Exception as exc:  # noqa: BLE001
            logger.debug("cache.set redis failure key=%s err=%s", full, exc)
    _INMEM[full] = (time.time() + ttl_sec, raw)


def clear_inmem() -> None:
    """Drop the in-process cache. Tests use this; not for prod paths."""
    _INMEM.clear()


async def reset_for_tests() -> None:
    """Reset both tiers and the lazy Redis singleton (test fixture)."""
    global _REDIS, _REDIS_FAILED
    _INMEM.clear()
    if _REDIS is not None:
        with contextlib.suppress(Exception):
            await _REDIS.aclose()
    _REDIS = None
    _REDIS_FAILED = False
