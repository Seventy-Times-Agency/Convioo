"""Yelp Fusion collector.

Yelp's Fusion v3 API has very strong US/CA/UK coverage and a free
tier (5k req/day). We hit ``businesses/search`` over the same
``RawLead`` shape Google + OSM emit, so the rest of the pipeline
(dedup, enrichment, AI scoring) stays identical.

Niche → Yelp category mapping lives in ``data/niches.yaml`` under
``yelp_categories``. Niches without that key skip Yelp entirely so
we don't blow our daily budget on a free-text fallback.

Docs: https://docs.developer.yelp.com/reference/v3_business_search
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from leadgen.collectors.google_places import RawLead
from leadgen.config import get_settings
from leadgen.utils.retry import retry_async

logger = logging.getLogger(__name__)


YELP_SEARCH_URL = "https://api.yelp.com/v3/businesses/search"


class YelpError(RuntimeError):
    """Raised when Yelp returns a non-success body."""


class _YelpTransientError(RuntimeError):
    """Internal: 5xx / 429 — retried by retry_async, not user-visible."""


class YelpCollector:
    """Pull leads from Yelp Fusion.

    Bring an API key (``YELP_API_KEY`` on Railway) and pass it once
    at construction. The collector caps page size at 50 (Yelp's hard
    limit) so a single search for a hot niche doesn't paginate
    forever — we already get plenty of fresh material from Google.
    """

    source = "yelp"

    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = 15.0,
        max_results: int = 50,
    ) -> None:
        if not api_key:
            raise YelpError("YELP_API_KEY is empty")
        self.api_key = api_key
        self.timeout = timeout
        # Yelp caps ``limit`` at 50 per call. Keeping the public knob
        # bounded saves callers from accidentally making 5x the calls
        # they expect.
        self.max_results = max(1, min(50, max_results))
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> YelpCollector:
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            headers={"Authorization": f"Bearer {self.api_key}"},
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
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        return self._client

    async def search(
        self,
        *,
        niche: str,
        region: str,
        yelp_categories: list[str] | tuple[str, ...],
        limit: int | None = None,
        bbox: tuple[float, float, float, float] | None = None,
    ) -> list[RawLead]:
        """Run ``businesses/search`` and normalise hits to RawLead.

        Yelp accepts either a textual ``location`` (e.g. "Brooklyn, NY")
        or a lat/long. When the pipeline already geocoded the region
        (and handed us a ``bbox``) we use the bbox centroid as the
        anchor — saves one round-trip and lines up with what Google
        and OSM see.
        """
        if not yelp_categories:
            return []
        cat_csv = ",".join(c.strip() for c in yelp_categories if c.strip())
        params: dict[str, Any] = {
            "categories": cat_csv,
            "limit": str(min(limit or self.max_results, self.max_results)),
            "sort_by": "best_match",
        }
        if bbox is not None:
            # Use the bbox centre as the anchor — Yelp doesn't accept a
            # raw bounding box, but a centre + radius approximates it.
            south, west, north, east = bbox
            params["latitude"] = f"{(south + north) / 2.0:.6f}"
            params["longitude"] = f"{(west + east) / 2.0:.6f}"
            # ~1° lat ≈ 111km; clamp at Yelp's 40km hard limit.
            radius_m = min(40_000, int(((north - south) / 2.0) * 111_000))
            if radius_m > 1_000:
                params["radius"] = str(radius_m)
        else:
            params["location"] = region

        client = await self._http()
        settings = get_settings()

        async def _do_get() -> httpx.Response:
            r = await client.get(YELP_SEARCH_URL, params=params)
            # 5xx is transient — retry. 429 is rate-limit; we surface it
            # to the caller so the search degrades silently rather than
            # eating the whole retry budget on a daily-budget burnout.
            if r.status_code >= 500:
                raise _YelpTransientError(f"yelp 5xx {r.status_code}")
            return r

        try:
            resp = await retry_async(
                _do_get,
                retries=settings.http_retries,
                base_delay=settings.http_retry_base_delay,
                retry_on=(httpx.HTTPError, _YelpTransientError),
                source="yelp",
            )
        except (httpx.HTTPError, _YelpTransientError) as exc:
            logger.warning("yelp.search: http error source=yelp err=%s", exc)
            return []
        if resp.status_code == 401:
            raise YelpError("Yelp rejected the API key (401)")
        if resp.status_code == 429:
            logger.warning("yelp.search: rate limited source=yelp status=429")
            return []
        if resp.status_code >= 400:
            logger.warning(
                "yelp.search: source=yelp status=%s body=%s",
                resp.status_code,
                resp.text[:300],
            )
            return []
        try:
            data = resp.json()
        except ValueError:
            return []

        leads: list[RawLead] = []
        for biz in data.get("businesses") or []:
            lead = self._parse(biz)
            if lead is not None:
                leads.append(lead)
        logger.info(
            "yelp.search: niche=%r region=%r categories=%s -> %d leads",
            niche,
            region,
            cat_csv,
            len(leads),
        )
        return leads

    @staticmethod
    def _parse(biz: dict[str, Any]) -> RawLead | None:
        name = biz.get("name")
        biz_id = biz.get("id")
        if not name or not biz_id:
            return None
        loc = biz.get("location") or {}
        addr = loc.get("display_address") or []
        full_addr = ", ".join(a for a in addr if a) or loc.get("address1")
        coords = biz.get("coordinates") or {}
        cats = biz.get("categories") or []
        primary = (cats[0].get("title") if cats else None) or None
        return RawLead(
            source="yelp",
            source_id=str(biz_id),
            name=name,
            website=biz.get("url"),  # Yelp's listing URL — not the biz site
            phone=biz.get("phone") or None,
            address=full_addr,
            category=primary,
            rating=float(biz["rating"]) if biz.get("rating") is not None else None,
            reviews_count=int(biz["review_count"])
            if biz.get("review_count") is not None
            else None,
            latitude=float(coords["latitude"])
            if coords.get("latitude") is not None
            else None,
            longitude=float(coords["longitude"])
            if coords.get("longitude") is not None
            else None,
            raw=biz,
        )
