"""Google Places API (New) collector.

Docs: https://developers.google.com/maps/documentation/places/web-service/text-search

Uses the POST /v1/places:searchText endpoint with a FieldMask to limit billing.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from leadgen.config import get_settings
from leadgen.core.services import usage_tracker
from leadgen.utils import cache as _cache
from leadgen.utils import retry_async
from leadgen.utils.secrets import sanitize

logger = logging.getLogger(__name__)


PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"

# Only request fields we actually use — this is what controls billing tier.
FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.shortFormattedAddress",
        "places.location",
        "places.types",
        "places.primaryType",
        "places.primaryTypeDisplayName",
        "places.businessStatus",
        "places.rating",
        "places.userRatingCount",
        "places.nationalPhoneNumber",
        "places.internationalPhoneNumber",
        "places.websiteUri",
        "nextPageToken",
    ]
)

# Place Details FieldMask: includes reviews (Enterprise SKU). Use sparingly,
# only for top-N leads selected for enrichment.
DETAILS_FIELD_MASK = ",".join(
    [
        "id",
        "displayName",
        "rating",
        "userRatingCount",
        "reviews",
        "regularOpeningHours",
        "businessStatus",
        "priceLevel",
        "editorialSummary",
    ]
)


@dataclass(slots=True)
class RawLead:
    """Normalised lead record produced by a collector."""

    source: str
    source_id: str
    name: str
    website: str | None = None
    phone: str | None = None
    address: str | None = None
    category: str | None = None
    rating: float | None = None
    reviews_count: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    tags: list[str] | None = None


class GooglePlacesError(RuntimeError):
    """Raised when the Google Places API returns a non-success response."""


class GooglePlacesCollector:
    source = "google_places"

    def __init__(
        self,
        api_key: str | None = None,
        language: str | None = "en",
        region_code: str | None = None,
        page_size: int = 20,
        max_pages: int = 3,
        timeout: float = 30.0,
    ) -> None:
        """Construct a Places collector.

        ``language`` defaults to ``"en"`` so results come back in English
        regardless of the user's Telegram locale — appropriate for our
        US/EU/CIS-ex-RU target market. ``region_code`` defaults to
        ``None`` (no regional bias): a previous hard-coded ``"RU"`` was
        skewing English queries like "roofing" toward Russian results
        (a single university showed up in one real search). The bias
        can still be set explicitly per-call if a caller has strong
        signal about which market to prefer.
        """
        self.api_key = api_key or get_settings().google_places_api_key
        if not self.api_key:
            raise GooglePlacesError("GOOGLE_PLACES_API_KEY is not configured")
        self.language = language
        self.region_code = region_code
        self.page_size = page_size
        self.max_pages = max_pages
        self.timeout = timeout

    async def search(
        self,
        niche: str,
        region: str,
        *,
        location_restriction_bbox: tuple[float, float, float, float] | None = None,
    ) -> list[RawLead]:
        """Run a Places text search.

        ``location_restriction_bbox`` is ``(south, west, north, east)``;
        when set we send it as ``locationRestriction.rectangle`` so the
        backend strictly limits results to the geo. Used by the radius
        + scope features — the pipeline computes the rectangle from
        either Nominatim's bbox (state/country) or a circle around the
        city center (city/metro). Without it we fall back to plain
        ``textQuery`` biasing (existing behaviour).
        """
        query = f"{niche.strip()} {region.strip()}".strip()
        if not query:
            return []

        # Cross-user cache for the Text Search SKU (the most expensive
        # per-call endpoint we hit). Keyed on the full identity of the
        # request — same niche + region + language + bbox returns the
        # same Google response for ~24h, so two users hunting "roofing
        # brooklyn" share one billable lookup. RawLead is reconstructed
        # from the raw place dicts on cache hit.
        bbox_key = (
            ",".join(f"{v:.5f}" for v in location_restriction_bbox)
            if location_restriction_bbox
            else "-"
        )
        cache_key = (
            f"{query}|lang={self.language or '-'}|region={self.region_code or '-'}"
            f"|bbox={bbox_key}|page={self.page_size}x{self.max_pages}"
        )
        cached = await _cache.get_json("places_text_search", cache_key)
        if isinstance(cached, list):
            rebuilt: list[RawLead] = []
            seen: set[str] = set()
            for raw_place in cached:
                if not isinstance(raw_place, dict):
                    continue
                lead = self._parse_place(raw_place)
                if lead is None or lead.source_id in seen:
                    continue
                seen.add(lead.source_id)
                rebuilt.append(lead)
            logger.info(
                "google_places.search cache_hit query=%r count=%d",
                query,
                len(rebuilt),
            )
            return rebuilt

        logger.info(
            "google_places.search start query=%r language=%r region_code=%r bbox=%s",
            query,
            self.language,
            self.region_code,
            location_restriction_bbox,
        )

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        }
        body: dict[str, Any] = {
            "textQuery": query,
            "pageSize": self.page_size,
        }
        # Only bias the result set when the caller actually knows which
        # market/language they want — unbiased search on a fully-formed
        # query ("roofing Los Angeles") produces better results than
        # hinting the wrong locale.
        if self.language:
            body["languageCode"] = self.language
        if self.region_code:
            body["regionCode"] = self.region_code
        if location_restriction_bbox is not None:
            south, west, north, east = location_restriction_bbox
            body["locationRestriction"] = {
                "rectangle": {
                    "low": {"latitude": south, "longitude": west},
                    "high": {"latitude": north, "longitude": east},
                }
            }

        leads: list[RawLead] = []
        seen_ids: set[str] = set()
        raw_places: list[dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for page in range(self.max_pages):
                async def do_search_request() -> httpx.Response:
                    return await client.post(PLACES_TEXT_SEARCH_URL, headers=headers, json=body)

                resp = await retry_async(
                    do_search_request,
                    retries=get_settings().http_retries,
                    base_delay=get_settings().http_retry_base_delay,
                    retry_on=(httpx.HTTPError,),
                )

                if resp.status_code != 200:
                    safe_body = sanitize(resp.text[:500])
                    logger.error(
                        "google_places.error status=%s body=%s",
                        resp.status_code,
                        safe_body,
                    )
                    raise GooglePlacesError(
                        f"Google Places API returned {resp.status_code}: "
                        f"{sanitize(resp.text[:200])}"
                    )

                # Bill the user for one Text Search SKU. Counted only
                # on cache miss because cache hits don't go to Google.
                await usage_tracker.record("google_text_search", 1)
                data = resp.json()
                for place in data.get("places", []) or []:
                    lead = self._parse_place(place)
                    if lead is None:
                        # Closed-permanently / closed-temporarily businesses
                        # or rows missing an id — not useful to the user.
                        continue
                    if lead.source_id in seen_ids:
                        continue
                    seen_ids.add(lead.source_id)
                    leads.append(lead)
                    raw_places.append(place)

                next_token = data.get("nextPageToken")
                if not next_token or page == self.max_pages - 1:
                    break

                # Google recommends a brief delay before the page token becomes valid.
                await asyncio.sleep(2.0)
                body["pageToken"] = next_token

        if raw_places:
            await _cache.set_json(
                "places_text_search",
                cache_key,
                raw_places,
                _cache.TEXT_SEARCH_TTL_SEC,
            )

        logger.info("google_places.search done query=%r count=%d", query, len(leads))
        return leads

    async def get_details(self, place_id: str) -> dict[str, Any]:
        """Fetch detailed info for a single place, including up to 5 reviews.

        Uses the Place Details endpoint with reviews field — this is the
        Enterprise pricing tier, so call only for top-N leads.
        """
        if not place_id:
            raise ValueError("place_id is required")

        # Place Details is the Enterprise SKU on Google's side — cache
        # aggressively. Key on (place_id, language) since language flips
        # the localised display name + editorialSummary.
        cache_key = f"{place_id}:{self.language or '-'}"
        cached = await _cache.get_json("place_details", cache_key)
        if isinstance(cached, dict):
            return cached

        url = PLACE_DETAILS_URL.format(place_id=place_id)
        headers = {
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": DETAILS_FIELD_MASK,
        }
        if self.language:
            headers["Accept-Language"] = self.language

        # Tighter timeout per place — we're enriching up to ~50 in parallel
        # and one stuck request shouldn't stall the whole batch.
        per_request_timeout = min(8.0, self.timeout)

        async with httpx.AsyncClient(timeout=per_request_timeout) as client:
            async def do_details_request() -> httpx.Response:
                return await asyncio.wait_for(
                    client.get(url, headers=headers),
                    timeout=per_request_timeout,
                )

            try:
                resp = await retry_async(
                    do_details_request,
                    retries=get_settings().http_retries,
                    base_delay=get_settings().http_retry_base_delay,
                    retry_on=(httpx.HTTPError, TimeoutError),
                )
            except TimeoutError as exc:
                raise GooglePlacesError(
                    f"Place Details timed out after {per_request_timeout}s"
                ) from exc

            if resp.status_code != 200:
                safe_body = sanitize(resp.text[:300])
                logger.warning(
                    "google_places.details_error status=%s body=%s",
                    resp.status_code,
                    safe_body,
                )
                raise GooglePlacesError(
                    f"Place Details returned {resp.status_code}: "
                    f"{sanitize(resp.text[:200])}"
                )
            payload = resp.json()
            # Bill one Place Details (Enterprise SKU — we request reviews).
            await usage_tracker.record("google_place_details", 1)
            await _cache.set_json(
                "place_details", cache_key, payload, _cache.PLACE_DETAILS_TTL_SEC
            )
            return payload

    def _parse_place(self, place: dict[str, Any]) -> RawLead | None:
        # Skip rows we can't use downstream: closed businesses and anything
        # without a stable source id (we need it for dedup + details).
        business_status = (place.get("businessStatus") or "").upper()
        if business_status in {"CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"}:
            return None
        source_id = place.get("id")
        if not source_id:
            return None

        display_name = place.get("displayName") or {}
        primary_type_display = place.get("primaryTypeDisplayName") or {}
        location = place.get("location") or {}

        return RawLead(
            source=self.source,
            source_id=source_id,
            name=display_name.get("text") or "",
            website=place.get("websiteUri"),
            phone=place.get("internationalPhoneNumber") or place.get("nationalPhoneNumber"),
            address=place.get("formattedAddress") or place.get("shortFormattedAddress"),
            category=primary_type_display.get("text") or place.get("primaryType"),
            rating=place.get("rating"),
            reviews_count=place.get("userRatingCount"),
            latitude=location.get("latitude"),
            longitude=location.get("longitude"),
            raw=place,
        )
