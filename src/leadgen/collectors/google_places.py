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

from leadgen.config import settings

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


class GooglePlacesError(RuntimeError):
    """Raised when the Google Places API returns a non-success response."""


class GooglePlacesCollector:
    source = "google_places"

    def __init__(
        self,
        api_key: str | None = None,
        language: str = "ru",
        region_code: str = "RU",
        page_size: int = 20,
        max_pages: int = 3,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key or settings.google_places_api_key
        self.language = language
        self.region_code = region_code
        self.page_size = page_size
        self.max_pages = max_pages
        self.timeout = timeout

    async def search(self, niche: str, region: str) -> list[RawLead]:
        query = f"{niche.strip()} {region.strip()}".strip()
        if not query:
            return []

        logger.info("google_places.search start query=%r", query)

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        }
        body: dict[str, Any] = {
            "textQuery": query,
            "languageCode": self.language,
            "regionCode": self.region_code,
            "pageSize": self.page_size,
        }

        leads: list[RawLead] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for page in range(self.max_pages):
                resp = await client.post(PLACES_TEXT_SEARCH_URL, headers=headers, json=body)

                if resp.status_code != 200:
                    logger.error(
                        "google_places.error status=%s body=%s",
                        resp.status_code,
                        resp.text[:500],
                    )
                    raise GooglePlacesError(
                        f"Google Places API returned {resp.status_code}: {resp.text[:200]}"
                    )

                data = resp.json()
                for place in data.get("places", []) or []:
                    lead = self._parse_place(place)
                    if not lead.source_id or lead.source_id in seen_ids:
                        continue
                    seen_ids.add(lead.source_id)
                    leads.append(lead)

                next_token = data.get("nextPageToken")
                if not next_token or page == self.max_pages - 1:
                    break

                # Google recommends a brief delay before the page token becomes valid.
                await asyncio.sleep(2.0)
                body["pageToken"] = next_token

        logger.info("google_places.search done query=%r count=%d", query, len(leads))
        return leads

    async def get_details(self, place_id: str) -> dict[str, Any]:
        """Fetch detailed info for a single place, including up to 5 reviews.

        Uses the Place Details endpoint with reviews field — this is the
        Enterprise pricing tier, so call only for top-N leads.
        """
        if not place_id:
            raise ValueError("place_id is required")

        url = PLACE_DETAILS_URL.format(place_id=place_id)
        headers = {
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": DETAILS_FIELD_MASK,
            "Accept-Language": self.language,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning(
                    "google_places.details_error status=%s body=%s",
                    resp.status_code,
                    resp.text[:300],
                )
                raise GooglePlacesError(
                    f"Place Details returned {resp.status_code}: {resp.text[:200]}"
                )
            return resp.json()

    def _parse_place(self, place: dict[str, Any]) -> RawLead:
        display_name = place.get("displayName") or {}
        primary_type_display = place.get("primaryTypeDisplayName") or {}
        location = place.get("location") or {}

        return RawLead(
            source=self.source,
            source_id=place.get("id") or "",
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
