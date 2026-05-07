"""Cross-user, cross-collector cache for raw lead lists.

Google Places already caches its Text Search response inside the
collector (see ``leadgen.collectors.google_places``). This module is
the same idea for the *other* discovery sources — OSM, Yelp,
Foursquare — so two tenants searching the same (niche, geo) within a
short window share a single billable lookup. The 950/day Foursquare
free quota in particular would otherwise burn out on the second
power user of the day.

Storage piggybacks on ``leadgen.utils.cache``: Redis when configured,
in-process dict otherwise. ``RawLead`` is shuttled through JSON
(``dataclasses.asdict``) so the deserialised objects are byte-for-
byte equivalent to a fresh fetch.

Pattern used by call sites:

    leads = await cached_collector_run(
        source="osm",
        key=cache_key,
        ttl_sec=12 * 3600,
        fetcher=lambda: discover_with_lock(...),
    )

When cached, ``fetcher`` is never awaited and no network call fires.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from typing import Any

from leadgen.collectors.google_places import RawLead
from leadgen.utils import cache as _cache

logger = logging.getLogger(__name__)


# 12h is the sweet spot for local-business discovery: long enough that
# a daily search rotation hits warm cache, short enough that a freshly
# opened business shows up by tomorrow morning. Adjust per-source via
# the ``ttl_sec`` argument when needed.
DEFAULT_TTL_SEC = 12 * 60 * 60


def _serialize(leads: list[RawLead]) -> list[dict[str, Any]]:
    return [asdict(lead) for lead in leads]


def _deserialize(payload: Any) -> list[RawLead] | None:
    if not isinstance(payload, list):
        return None
    out: list[RawLead] = []
    for row in payload:
        if not isinstance(row, dict):
            return None
        try:
            out.append(RawLead(**row))
        except (TypeError, ValueError) as exc:
            logger.debug("search_cache: skip malformed cached row err=%s", exc)
            return None
    return out


async def cached_collector_run(
    *,
    source: str,
    key: str,
    ttl_sec: int = DEFAULT_TTL_SEC,
    fetcher: Callable[[], Awaitable[list[RawLead]]],
) -> list[RawLead]:
    """Return cached leads for ``(source, key)`` or run ``fetcher`` and store.

    The fetcher is only awaited on miss. Empty results are not
    cached — a transient outage shouldn't pin a "no results" state
    for the next 12h. Cache backend errors are logged and degrade to
    a live fetch.
    """
    namespace = f"collector_{source}"
    try:
        cached = await _cache.get_json(namespace, key)
    except Exception as exc:  # noqa: BLE001
        logger.debug("search_cache: get failed source=%s err=%s", source, exc)
        cached = None
    if cached is not None:
        rebuilt = _deserialize(cached)
        if rebuilt is not None:
            logger.info(
                "search_cache.hit source=%s key=%s count=%d",
                source,
                key,
                len(rebuilt),
            )
            return rebuilt

    leads = await fetcher()
    if leads:
        try:
            await _cache.set_json(namespace, key, _serialize(leads), ttl_sec)
        except Exception as exc:  # noqa: BLE001
            logger.debug("search_cache: set failed source=%s err=%s", source, exc)
    return leads


def make_geo_key(
    *,
    niche: str,
    region: str,
    bbox: tuple[float, float, float, float] | None,
    extras: dict[str, Any] | None = None,
) -> str:
    """Build a deterministic cache key from a search's identity.

    ``extras`` covers source-specific fields (osm_tags, yelp/fsq
    categories, language, ...) — pass them in pre-sorted form so a
    set/dict reordering doesn't fragment the cache.
    """
    parts = [niche.strip().lower(), region.strip().lower()]
    if bbox:
        parts.append(",".join(f"{v:.4f}" for v in bbox))
    else:
        parts.append("-")
    if extras:
        for k in sorted(extras):
            v = extras[k]
            if isinstance(v, (list, tuple, set)):
                v = ",".join(sorted(str(x) for x in v))
            parts.append(f"{k}={v}")
    return "|".join(parts)
