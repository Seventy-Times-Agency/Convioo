"""Foursquare Places v3 collector.

Foursquare's free tier (950 calls/day) covers global hotspots well
and is the right complement to Yelp (US/UK/CA-strong) and OSM
(EU/UA-strong). Niche → Foursquare category mapping is opt-in via
``data/niches.yaml`` under ``fsq_categories`` — without that key
the collector is skipped, same conservative pattern as Yelp.

Docs: https://docs.foursquare.com/developer/reference/place-search
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from leadgen.collectors.google_places import RawLead
from leadgen.config import get_settings
from leadgen.utils.retry import retry_async

logger = logging.getLogger(__name__)


FSQ_SEARCH_URL = "https://api.foursquare.com/v3/places/search"


class FoursquareError(RuntimeError):
    """Raised when Foursquare returns a non-success body."""


class _FsqTransientError(RuntimeError):
    """Internal: 5xx — retried by retry_async, not user-visible."""


class FoursquareCollector:
    """Pull leads from Foursquare Places v3.

    The v3 API uses an ``Authorization: <api_key>`` header — note
    the lack of ``Bearer`` prefix; that's a common gotcha when
    porting from Yelp.
    """

    source = "foursquare"

    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = 15.0,
        max_results: int = 50,
    ) -> None:
        if not api_key:
            raise FoursquareError("FSQ_API_KEY is empty")
        self.api_key = api_key
        self.timeout = timeout
        # Foursquare caps ``limit`` at 50 per call.
        self.max_results = max(1, min(50, max_results))
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> FoursquareCollector:
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            headers={
                # v3 deliberately uses the bare key, not "Bearer".
                "Authorization": self.api_key,
                "Accept": "application/json",
            },
        )
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={
                    "Authorization": self.api_key,
                    "Accept": "application/json",
                },
            )
        return self._client

    async def search(
        self,
        *,
        niche: str,
        region: str,
        fsq_categories: list[str] | tuple[str, ...],
        limit: int | None = None,
        bbox: tuple[float, float, float, float] | None = None,
    ) -> list[RawLead]:
        """Run ``places/search`` and normalise hits to RawLead."""
        if not fsq_categories:
            return []
        # Foursquare expects the rich detail fields enumerated up-front
        # — without ``fields`` we get a stub payload missing rating
        # and description. Keep the list tight to stay inside their
        # bandwidth caps on the free tier.
        params: dict[str, Any] = {
            "categories": ",".join(c.strip() for c in fsq_categories if c.strip()),
            "limit": str(min(limit or self.max_results, self.max_results)),
            "fields": (
                "fsq_id,name,location,categories,geocodes,"
                "tel,website,rating,stats"
            ),
        }
        if bbox is not None:
            south, west, north, east = bbox
            # ``ne`` and ``sw`` are "lat,long" pairs.
            params["ne"] = f"{north:.6f},{east:.6f}"
            params["sw"] = f"{south:.6f},{west:.6f}"
        else:
            params["near"] = region

        client = await self._http()
        settings = get_settings()

        async def _do_get() -> httpx.Response:
            r = await client.get(FSQ_SEARCH_URL, params=params)
            if r.status_code >= 500:
                raise _FsqTransientError(f"foursquare 5xx {r.status_code}")
            return r

        try:
            resp = await retry_async(
                _do_get,
                retries=settings.http_retries,
                base_delay=settings.http_retry_base_delay,
                retry_on=(httpx.HTTPError, _FsqTransientError),
                source="foursquare",
            )
        except (httpx.HTTPError, _FsqTransientError) as exc:
            logger.warning("foursquare.search: http error source=foursquare err=%s", exc)
            return []
        if resp.status_code == 401:
            raise FoursquareError("Foursquare rejected the API key (401)")
        if resp.status_code == 429:
            logger.warning("foursquare.search: rate limited source=foursquare status=429")
            return []
        if resp.status_code >= 400:
            logger.warning(
                "foursquare.search: source=foursquare status=%s body=%s",
                resp.status_code,
                resp.text[:300],
            )
            return []
        try:
            data = resp.json()
        except ValueError:
            return []

        leads: list[RawLead] = []
        for place in data.get("results") or []:
            lead = self._parse(place)
            if lead is not None:
                leads.append(lead)
        logger.info(
            "foursquare.search: niche=%r region=%r cats=%s -> %d leads",
            niche,
            region,
            params["categories"],
            len(leads),
        )
        return leads

    @staticmethod
    def _parse(place: dict[str, Any]) -> RawLead | None:
        fsq_id = place.get("fsq_id")
        name = place.get("name")
        if not fsq_id or not name:
            return None
        loc = place.get("location") or {}
        addr_lines = [
            loc.get("address"),
            loc.get("locality"),
            loc.get("region"),
            loc.get("postcode"),
            loc.get("country"),
        ]
        full_addr = ", ".join(s for s in addr_lines if s)
        cats = place.get("categories") or []
        primary = cats[0].get("name") if cats else None
        coords = (place.get("geocodes") or {}).get("main") or {}
        stats = place.get("stats") or {}
        return RawLead(
            source="foursquare",
            source_id=str(fsq_id),
            name=name,
            website=place.get("website"),
            phone=place.get("tel"),
            address=full_addr or None,
            category=primary,
            rating=float(place["rating"]) if place.get("rating") is not None else None,
            reviews_count=int(stats["total_ratings"])
            if stats.get("total_ratings") is not None
            else None,
            latitude=float(coords["latitude"])
            if coords.get("latitude") is not None
            else None,
            longitude=float(coords["longitude"])
            if coords.get("longitude") is not None
            else None,
            raw=place,
        )
