"""Live connector smoke tests (Wave 1, задача 8 — Connector QA).

These hit the REAL external APIs, so they only run when explicitly
armed: ``RUN_LIVE_SMOKE=1`` in the environment AND the given
connector's key present. In CI and normal `pytest` runs every test
here skips — they are the pre-deploy checklist for Part A / key
rotation, not part of the unit suite:

    RUN_LIVE_SMOKE=1 pytest tests/test_connectors_smoke_live.py -v

Each test asserts the connector answers with a sane shape (list of
RawLead with names) — a revoked key raises/answers 401 and the
collector's own logging marks the source in Railway logs.
"""

from __future__ import annotations

import os

import pytest

from leadgen.config import get_settings

LIVE = os.environ.get("RUN_LIVE_SMOKE") == "1"

pytestmark = pytest.mark.skipif(
    not LIVE, reason="live smoke tests run only with RUN_LIVE_SMOKE=1"
)


def _skip_without(value: str, name: str) -> None:
    if not value:
        pytest.skip(f"{name} is not configured")


@pytest.mark.asyncio
async def test_google_places_live():
    settings = get_settings()
    _skip_without(settings.google_places_api_key, "GOOGLE_PLACES_API_KEY")
    from leadgen.collectors import GooglePlacesCollector

    leads = await GooglePlacesCollector().search("coffee shop", "Miami, FL")
    assert leads, "Google Places returned no leads"
    assert leads[0].name


@pytest.mark.asyncio
async def test_google_place_details_live():
    settings = get_settings()
    _skip_without(settings.google_places_api_key, "GOOGLE_PLACES_API_KEY")
    from leadgen.collectors import GooglePlacesCollector

    collector = GooglePlacesCollector()
    leads = await collector.search("coffee shop", "Miami, FL")
    assert leads
    details = await collector.get_details(leads[0].source_id)
    assert details is not None


@pytest.mark.asyncio
async def test_yelp_live():
    settings = get_settings()
    _skip_without(settings.yelp_api_key, "YELP_API_KEY")
    from leadgen.collectors.yelp import YelpCollector

    leads = await YelpCollector().search(
        niche="coffee",
        region="Miami, FL",
        yelp_categories=["coffee"],
        limit=5,
    )
    assert isinstance(leads, list)
    assert leads and leads[0].name


@pytest.mark.asyncio
async def test_foursquare_live():
    settings = get_settings()
    _skip_without(settings.fsq_api_key, "FSQ_API_KEY")
    from leadgen.collectors.foursquare import FoursquareCollector

    leads = await FoursquareCollector().search(
        niche="coffee",
        region="Miami, FL",
        fsq_categories=[],
        limit=5,
    )
    assert isinstance(leads, list)


@pytest.mark.asyncio
async def test_osm_live():
    from leadgen.collectors.osm import OsmCollector

    leads = await OsmCollector().search(
        niche="cafe", region="Miami, FL", osm_tags=["amenity=cafe"]
    )
    assert isinstance(leads, list)


@pytest.mark.asyncio
async def test_adzuna_live():
    settings = get_settings()
    _skip_without(settings.adzuna_app_id, "ADZUNA_APP_ID")
    _skip_without(settings.adzuna_api_key, "ADZUNA_API_KEY")
    from leadgen.collectors.adzuna import search_hiring_companies

    companies = await search_hiring_companies("marketing", "Miami")
    assert isinstance(companies, list)


@pytest.mark.asyncio
async def test_source_health_probes_live():
    """One pass over the health-probe fleet — the same view the admin
    dashboard renders. Every configured source must not be 'error'."""
    from leadgen.core.services.source_health import check_all

    results = await check_all(force=True)
    assert results
    broken = [
        r for r in results if getattr(r, "status", "error") == "error"
    ]
    assert not broken, f"broken sources: {broken}"


@pytest.mark.asyncio
async def test_website_collector_live():
    from leadgen.collectors.website import WebsiteCollector

    info = await WebsiteCollector().fetch("https://example.com")
    assert info.ok
