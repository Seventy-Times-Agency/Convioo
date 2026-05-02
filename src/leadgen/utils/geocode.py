"""Region geocoding via Nominatim (free, no key).

Used by the search pipeline to turn a free-text region ("Berlin",
"Bavaria", "Germany") into a centered point + bounding box that
both Google Places and Overpass can lean on. Nominatim is shared
infrastructure — we keep the User-Agent meaningful and cache
results in-process so a stampede of identical searches doesn't
hammer the upstream.
"""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from time import monotonic

import httpx

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "Convioo/0.1 (+https://convioo.com)"


@dataclass(slots=True, frozen=True)
class GeocodeResult:
    """Minimal Nominatim response shape we care about."""

    name: str
    lat: float
    lon: float
    bbox_south: float
    bbox_west: float
    bbox_north: float
    bbox_east: float
    osm_type: str | None = None  # node / way / relation

    def bbox_tuple(self) -> tuple[float, float, float, float]:
        """``(south, west, north, east)`` — matches the OSM collector shape."""
        return (self.bbox_south, self.bbox_west, self.bbox_north, self.bbox_east)


# Simple in-memory cache: identical region strings normalise to the
# same key, TTL keeps us from holding stale data forever (city
# boundaries get redrawn). One process, one cache — fine for the
# current single-container deploy.
_CACHE: dict[str, tuple[float, GeocodeResult]] = {}
_CACHE_TTL_SEC = 24 * 60 * 60


async def geocode_region(
    region: str, *, timeout: float = 10.0
) -> GeocodeResult | None:
    """Resolve a free-text region to ``(lat, lon, bbox)``.

    Returns ``None`` for unrecognised inputs so callers can fall back
    to text-only search instead of crashing.
    """
    key = (region or "").strip().lower()
    if not key:
        return None

    now = monotonic()
    cached = _CACHE.get(key)
    if cached is not None and (now - cached[0]) < _CACHE_TTL_SEC:
        return cached[1]

    params = {
        "q": region,
        "format": "json",
        "limit": "1",
        "addressdetails": "0",
    }
    try:
        async with httpx.AsyncClient(
            timeout=timeout, headers={"User-Agent": USER_AGENT}
        ) as client:
            resp = await client.get(NOMINATIM_URL, params=params)
    except httpx.HTTPError as exc:
        logger.warning("geocode_region: HTTP error %s for %r", exc, region)
        return None

    if resp.status_code != 200:
        logger.warning(
            "geocode_region: %s returned %s",
            NOMINATIM_URL,
            resp.status_code,
        )
        return None

    rows = resp.json()
    if not rows:
        return None
    row = rows[0]
    bbox_raw = row.get("boundingbox")
    if not bbox_raw or len(bbox_raw) != 4:
        return None
    try:
        result = GeocodeResult(
            name=row.get("display_name") or region,
            lat=float(row["lat"]),
            lon=float(row["lon"]),
            bbox_south=float(bbox_raw[0]),
            bbox_north=float(bbox_raw[1]),
            bbox_west=float(bbox_raw[2]),
            bbox_east=float(bbox_raw[3]),
            osm_type=row.get("osm_type"),
        )
    except (TypeError, ValueError, KeyError) as exc:
        logger.warning("geocode_region: parse error %s for %r", exc, region)
        return None

    _CACHE[key] = (now, result)
    return result


def bbox_from_circle(
    lat: float, lon: float, radius_m: int
) -> tuple[float, float, float, float]:
    """Approximate ``(south, west, north, east)`` for a circle.

    Equirectangular approximation — good enough for the radii we care
    about (≤100 km). Latitudinal degree ≈ 111.32 km everywhere;
    longitudinal degree narrows toward the poles by cos(lat).
    """
    radius_km = max(0.0, radius_m / 1000.0)
    if radius_km <= 0:
        return (lat, lon, lat, lon)
    lat_offset = radius_km / 111.32
    cos_lat = max(0.01, math.cos(math.radians(lat)))
    lon_offset = radius_km / (111.32 * cos_lat)
    return (
        lat - lat_offset,
        lon - lon_offset,
        lat + lat_offset,
        lon + lon_offset,
    )


def clear_cache() -> None:
    """Drop the in-memory cache. Used by tests; not meant for prod."""
    _CACHE.clear()


# Single-flight: when N concurrent searches resolve the same region
# we don't want N Nominatim hits. ``async_lru_cache`` would be nice
# but we only need it for one function — a manual lock keyed by query
# is fine.
_INFLIGHT: dict[str, asyncio.Future[GeocodeResult | None]] = {}


async def geocode_region_dedup(region: str) -> GeocodeResult | None:
    """``geocode_region`` with concurrent-call coalescing."""
    key = (region or "").strip().lower()
    if not key:
        return None
    cached = _CACHE.get(key)
    now = monotonic()
    if cached is not None and (now - cached[0]) < _CACHE_TTL_SEC:
        return cached[1]
    fut = _INFLIGHT.get(key)
    if fut is not None:
        return await fut
    loop = asyncio.get_event_loop()
    fresh: asyncio.Future[GeocodeResult | None] = loop.create_future()
    _INFLIGHT[key] = fresh
    try:
        result = await geocode_region(region)
        fresh.set_result(result)
        return result
    finally:
        _INFLIGHT.pop(key, None)
