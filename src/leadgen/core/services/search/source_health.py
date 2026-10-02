"""Per-source health probes for the collector fleet.

The admin dashboard hits this to figure out which external API is
currently flaky / out-of-budget without having to read Railway logs.
Each probe sends one cheap request, classifies the response, and
returns a small ``SourceHealth`` record. Probes never throw — they
return ``status="error"`` with the underlying message so a single
broken collector doesn't take down the whole health view.

Status values:

* ``ok``        — 2xx response in a reasonable time.
* ``degraded``  — 5xx, timeouts, or unexpected schema (collector still
                 responds, but something is off upstream).
* ``rate_limited`` — 429.
* ``unconfigured`` — the source has no API key / is feature-flagged off.
* ``error``     — network failure or collector raised.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from leadgen.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SourceHealth:
    """Per-source probe result. JSON-serialisable for the admin API."""

    source: str
    status: str
    latency_ms: int | None = None
    detail: str | None = None
    http_status: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "detail": self.detail,
            "http_status": self.http_status,
        }


PROBE_TIMEOUT_SEC = 6.0


def _classify(status: int) -> str:
    if status == 429:
        return "rate_limited"
    if 200 <= status < 300:
        return "ok"
    if status >= 500:
        return "degraded"
    return "error"


async def _probe_google() -> SourceHealth:
    settings = get_settings()
    if not settings.google_places_api_key:
        return SourceHealth("google_places", "unconfigured", detail="GOOGLE_PLACES_API_KEY not set")
    body = {"textQuery": "coffee", "pageSize": 1, "languageCode": "en"}
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_places_api_key,
        "X-Goog-FieldMask": "places.id",
    }
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_SEC) as client:
            resp = await client.post(
                "https://places.googleapis.com/v1/places:searchText",
                headers=headers,
                json=body,
            )
    except httpx.HTTPError as exc:
        return SourceHealth("google_places", "error", detail=str(exc))
    latency_ms = int((time.monotonic() - started) * 1000)
    return SourceHealth(
        "google_places",
        _classify(resp.status_code),
        latency_ms=latency_ms,
        http_status=resp.status_code,
        detail=None if resp.status_code == 200 else resp.text[:160],
    )


async def _probe_yelp() -> SourceHealth:
    settings = get_settings()
    if not settings.yelp_api_key or not settings.yelp_enabled:
        return SourceHealth("yelp", "unconfigured", detail="YELP_API_KEY not set")
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(
            timeout=PROBE_TIMEOUT_SEC,
            headers={"Authorization": f"Bearer {settings.yelp_api_key}"},
        ) as client:
            resp = await client.get(
                "https://api.yelp.com/v3/businesses/search",
                params={"location": "New York", "limit": "1"},
            )
    except httpx.HTTPError as exc:
        return SourceHealth("yelp", "error", detail=str(exc))
    latency_ms = int((time.monotonic() - started) * 1000)
    return SourceHealth(
        "yelp",
        _classify(resp.status_code),
        latency_ms=latency_ms,
        http_status=resp.status_code,
        detail=None if resp.status_code == 200 else resp.text[:160],
    )


async def _probe_foursquare() -> SourceHealth:
    settings = get_settings()
    if not settings.fsq_api_key or not settings.fsq_enabled:
        return SourceHealth("foursquare", "unconfigured", detail="FSQ_API_KEY not set")
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(
            timeout=PROBE_TIMEOUT_SEC,
            headers={"Authorization": settings.fsq_api_key, "Accept": "application/json"},
        ) as client:
            resp = await client.get(
                "https://api.foursquare.com/v3/places/search",
                params={"near": "New York", "limit": "1"},
            )
    except httpx.HTTPError as exc:
        return SourceHealth("foursquare", "error", detail=str(exc))
    latency_ms = int((time.monotonic() - started) * 1000)
    return SourceHealth(
        "foursquare",
        _classify(resp.status_code),
        latency_ms=latency_ms,
        http_status=resp.status_code,
        detail=None if resp.status_code == 200 else resp.text[:160],
    )


async def _probe_overpass() -> SourceHealth:
    settings = get_settings()
    if not getattr(settings, "osm_enabled", True):
        return SourceHealth("osm", "unconfigured", detail="OSM_ENABLED=false")
    # Trivial Overpass query — one node tagged amenity=cafe in a tiny
    # bbox. Cheap server-side, returns near-instantly when the public
    # node is healthy.
    query = (
        "[out:json][timeout:5];"
        'node["amenity"="cafe"](40.7,-74.01,40.71,-74.0);'
        "out 1;"
    )
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(
            timeout=PROBE_TIMEOUT_SEC,
            headers={"User-Agent": "Convioo/0.1 (+https://convioo.com)"},
        ) as client:
            resp = await client.post(
                "https://overpass-api.de/api/interpreter",
                data={"data": query},
            )
    except httpx.HTTPError as exc:
        return SourceHealth("osm", "error", detail=str(exc))
    latency_ms = int((time.monotonic() - started) * 1000)
    return SourceHealth(
        "osm",
        _classify(resp.status_code),
        latency_ms=latency_ms,
        http_status=resp.status_code,
        detail=None if resp.status_code == 200 else resp.text[:160],
    )


PROBES = {
    "google_places": _probe_google,
    "yelp": _probe_yelp,
    "foursquare": _probe_foursquare,
    "osm": _probe_overpass,
}


# Cache the last successful snapshot for ~60s. Without this, every hit on
# the admin dashboard fires four outbound probes — Google + Yelp + FSQ +
# Overpass — which burns paid quota and inflates the very latency we're
# trying to surface. A single in-process snapshot is fine: the endpoint
# is admin-only, low-traffic, and cross-replica drift here is harmless.
_SNAPSHOT_TTL_SEC = 60.0
_snapshot_lock = asyncio.Lock()
_snapshot_cache: tuple[float, list[SourceHealth]] | None = None


async def _run_all_probes() -> list[SourceHealth]:
    results = await asyncio.gather(
        *(probe() for probe in PROBES.values()),
        return_exceptions=True,
    )
    out: list[SourceHealth] = []
    for name, result in zip(PROBES.keys(), results, strict=True):
        if isinstance(result, BaseException):
            logger.warning(
                "source_health: probe source=%s crashed err=%s",
                name,
                result,
            )
            out.append(SourceHealth(name, "error", detail=str(result)))
        else:
            out.append(result)
    return out


async def check_all(force: bool = False) -> list[SourceHealth]:
    """Return the latest source-health snapshot.

    Results are cached in-process for ``_SNAPSHOT_TTL_SEC`` to avoid
    hammering external APIs every time the admin dashboard refreshes.
    Pass ``force=True`` to bypass the cache (e.g. a "Refresh now" button).

    Order of the returned list matches ``PROBES`` insertion order so the
    admin UI can render a stable table.
    """
    global _snapshot_cache
    now = time.monotonic()
    if not force and _snapshot_cache is not None:
        cached_at, cached = _snapshot_cache
        if now - cached_at < _SNAPSHOT_TTL_SEC:
            return list(cached)
    async with _snapshot_lock:
        # Re-check after acquiring the lock — another coroutine may have
        # populated the cache while we were waiting.
        if not force and _snapshot_cache is not None:
            cached_at, cached = _snapshot_cache
            if time.monotonic() - cached_at < _SNAPSHOT_TTL_SEC:
                return list(cached)
        fresh = await _run_all_probes()
        _snapshot_cache = (time.monotonic(), fresh)
        return list(fresh)


def reset_cache() -> None:
    """Clear the in-process snapshot. Used by tests."""
    global _snapshot_cache
    _snapshot_cache = None
