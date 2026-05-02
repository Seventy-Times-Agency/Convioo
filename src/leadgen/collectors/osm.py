"""OpenStreetMap collector via Nominatim + Overpass.

Free public APIs, no key required, but they ask for a meaningful
``User-Agent`` and have soft rate limits — we cap concurrency and
keep timeouts tight so a slow Overpass node doesn't stall the
whole search.

Nominatim: https://nominatim.org/release-docs/latest/api/Search/
Overpass:  https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from leadgen.collectors.google_places import RawLead
from leadgen.config import get_settings

logger = logging.getLogger(__name__)


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"


class OsmError(RuntimeError):
    """Raised when Nominatim or Overpass return something unusable."""


class OsmCollector:
    """Pull leads from OpenStreetMap matching a niche-derived tag set.

    The pipeline first resolves the user-typed niche to a taxonomy
    entry to get its ``osm_tags`` (e.g. ``["amenity=dentist",
    "healthcare=dentist"]``), geocodes the region via Nominatim, then
    runs an Overpass query over the bounding box. Results are
    normalised into ``RawLead`` so the rest of the pipeline (dedup,
    enrichment, AI scoring) doesn't care that they came from OSM.
    """

    source = "osm"

    def __init__(
        self,
        timeout: float = 25.0,
        page_size: int = 50,
        user_agent: str = "Convioo/0.1 (+https://convioo.com)",
    ) -> None:
        self.timeout = timeout
        self.page_size = page_size
        self.user_agent = user_agent
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> OsmCollector:
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            headers={"User-Agent": self.user_agent},
        )
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            # Allow direct one-shot use without ``async with``.
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={"User-Agent": self.user_agent},
            )
        return self._client

    async def search(
        self,
        *,
        niche: str,
        region: str,
        osm_tags: list[str],
        limit: int | None = None,
    ) -> list[RawLead]:
        """Geocode ``region``, query Overpass for ``osm_tags`` inside it."""
        if not osm_tags:
            return []
        bbox = await self._geocode(region)
        if bbox is None:
            logger.info("osm.search: geocode miss for region=%r", region)
            return []
        query = self._build_overpass_query(osm_tags, bbox)
        try:
            data = await self._post_overpass(query)
        except OsmError as exc:
            logger.warning("osm.search: overpass failed: %s", exc)
            return []
        leads = self._parse(data)
        if limit is not None:
            leads = leads[:limit]
        logger.info(
            "osm.search niche=%r region=%r tags=%s → %d leads",
            niche,
            region,
            osm_tags,
            len(leads),
        )
        return leads

    # ── HTTP plumbing ──────────────────────────────────────────────

    async def _geocode(
        self, region: str
    ) -> tuple[float, float, float, float] | None:
        """Return ``(south, west, north, east)`` for the matched place."""
        client = await self._http()
        params = {
            "q": region,
            "format": "json",
            "limit": "1",
            "addressdetails": "0",
        }
        try:
            resp = await client.get(NOMINATIM_URL, params=params)
        except httpx.HTTPError as exc:
            raise OsmError(f"nominatim http error: {exc}") from exc
        if resp.status_code != 200:
            raise OsmError(
                f"nominatim returned {resp.status_code}: {resp.text[:200]}"
            )
        rows = resp.json()
        if not rows:
            return None
        row = rows[0]
        bbox_raw = row.get("boundingbox")
        if not bbox_raw or len(bbox_raw) != 4:
            return None
        try:
            south, north, west, east = (
                float(bbox_raw[0]),
                float(bbox_raw[1]),
                float(bbox_raw[2]),
                float(bbox_raw[3]),
            )
        except (TypeError, ValueError) as exc:
            raise OsmError(f"nominatim bbox parse failed: {exc}") from exc
        return (south, west, north, east)

    def _build_overpass_query(
        self,
        osm_tags: list[str],
        bbox: tuple[float, float, float, float],
    ) -> str:
        """Generate an Overpass QL query covering nodes + ways + relations."""
        south, west, north, east = bbox
        bbox_clause = f"({south},{west},{north},{east})"
        clauses: list[str] = []
        for tag in osm_tags:
            if "=" not in tag:
                continue
            key, value = tag.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key or not value:
                continue
            for kind in ("node", "way", "relation"):
                clauses.append(f'  {kind}["{key}"="{value}"]{bbox_clause};')
        body = "\n".join(clauses)
        # ``out tags center`` returns coordinates even for ways/relations,
        # which gives us a usable lat/lon without a second roundtrip.
        return (
            f"[out:json][timeout:{int(self.timeout)}];\n"
            "(\n"
            f"{body}\n"
            ");\n"
            f"out tags center {self.page_size};\n"
        )

    async def _post_overpass(self, query: str) -> dict[str, Any]:
        client = await self._http()
        try:
            resp = await client.post(OVERPASS_URL, data={"data": query})
        except httpx.HTTPError as exc:
            raise OsmError(f"overpass http error: {exc}") from exc
        if resp.status_code != 200:
            raise OsmError(
                f"overpass returned {resp.status_code}: {resp.text[:200]}"
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise OsmError(f"overpass returned non-JSON: {exc}") from exc

    # ── Parsing ────────────────────────────────────────────────────

    def _parse(self, data: dict[str, Any]) -> list[RawLead]:
        elements = data.get("elements") or []
        out: list[RawLead] = []
        seen_ids: set[str] = set()
        for el in elements:
            lead = self._element_to_lead(el)
            if lead is None:
                continue
            if lead.source_id in seen_ids:
                continue
            seen_ids.add(lead.source_id)
            out.append(lead)
        return out

    def _element_to_lead(self, el: dict[str, Any]) -> RawLead | None:
        tags = el.get("tags") or {}
        name = (tags.get("name") or "").strip()
        if not name:
            # Without a business name we can't surface the lead in the
            # CRM, and OSM has lots of unnamed POIs (parking lots etc.).
            return None
        kind = el.get("type") or "node"
        oid = el.get("id")
        if not oid:
            return None
        source_id = f"{kind}/{oid}"
        # Coordinates: nodes use lat/lon directly, ways/relations carry
        # them under ``center`` thanks to ``out center``.
        lat = el.get("lat")
        lon = el.get("lon")
        if lat is None or lon is None:
            center = el.get("center") or {}
            lat = center.get("lat")
            lon = center.get("lon")
        website = (
            tags.get("website")
            or tags.get("contact:website")
            or tags.get("url")
        )
        phone = tags.get("phone") or tags.get("contact:phone")
        address = _format_address(tags)
        category = (
            tags.get("amenity")
            or tags.get("shop")
            or tags.get("craft")
            or tags.get("office")
            or tags.get("healthcare")
            or tags.get("leisure")
        )
        return RawLead(
            source=self.source,
            source_id=source_id,
            name=name,
            website=website,
            phone=phone,
            address=address,
            category=category,
            rating=None,
            reviews_count=None,
            latitude=float(lat) if lat is not None else None,
            longitude=float(lon) if lon is not None else None,
            raw=el,
        )


def _format_address(tags: dict[str, Any]) -> str | None:
    parts: list[str] = []
    street = tags.get("addr:street")
    house = tags.get("addr:housenumber")
    if street and house:
        parts.append(f"{street} {house}")
    elif street:
        parts.append(street)
    city = tags.get("addr:city") or tags.get("addr:town") or tags.get("addr:village")
    if city:
        parts.append(city)
    postcode = tags.get("addr:postcode")
    if postcode:
        parts.append(postcode)
    country = tags.get("addr:country")
    if country:
        parts.append(country)
    return ", ".join(parts) if parts else None


_OSM_LOCK = asyncio.Lock()


async def discover_with_lock(
    *,
    niche: str,
    region: str,
    osm_tags: list[str],
    limit: int | None = None,
) -> list[RawLead]:
    """Single-flight OSM call.

    The Overpass public node throttles parallel requests; we serialize
    them across the worker process so a burst of searches doesn't get
    rate-limited.
    """
    settings = get_settings()
    if not getattr(settings, "osm_enabled", True):
        return []
    async with _OSM_LOCK, OsmCollector() as collector:
        return await collector.search(
            niche=niche,
            region=region,
            osm_tags=osm_tags,
            limit=limit,
        )
