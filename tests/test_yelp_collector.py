"""Yelp Fusion collector: HTTP mocked, parser + niche mapping verified."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from leadgen.collectors.yelp import YelpCollector, YelpError
from leadgen.data.niches import _load


def test_yelp_categories_loaded_from_yaml() -> None:
    """A handful of well-known niches must carry yelp_categories."""
    by_id = {entry.id: entry for entry in _load()}
    assert by_id["roofing"].yelp_categories == ("roofing",)
    assert by_id["plumbing"].yelp_categories == ("plumbing",)
    assert by_id["dentists"].yelp_categories == ("dentists",)
    assert "cafes" in by_id["cafes"].yelp_categories
    # Niches without an explicit mapping should default to empty.
    assert by_id["chiropractors"].yelp_categories == ()


def test_yelp_collector_rejects_empty_key() -> None:
    with pytest.raises(YelpError):
        YelpCollector("")


@pytest.mark.asyncio
async def test_search_returns_empty_when_no_categories() -> None:
    """The pipeline never sends an empty category list, but the
    contract is still: no categories → no API call → no leads."""
    out = await YelpCollector("sk_test").search(
        niche="x", region="y", yelp_categories=()
    )
    assert out == []


@pytest.mark.asyncio
async def test_search_parses_business_payload(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class _Resp:
        status_code = 200
        text = ""

        def json(self) -> dict[str, Any]:
            return {
                "businesses": [
                    {
                        "id": "yelp_abc",
                        "name": "Acme Roofing",
                        "url": "https://yelp.com/biz/acme",
                        "phone": "+15551112222",
                        "rating": 4.5,
                        "review_count": 120,
                        "categories": [
                            {"alias": "roofing", "title": "Roofing"}
                        ],
                        "coordinates": {
                            "latitude": 40.71,
                            "longitude": -74.01,
                        },
                        "location": {
                            "address1": "1 Broadway",
                            "display_address": [
                                "1 Broadway",
                                "New York, NY 10004",
                            ],
                        },
                    },
                    # Junk row missing ``id`` — should be skipped, not crash.
                    {"name": "No-id Co"},
                ]
            }

    class _Client:
        def __init__(self, *a, **kw):
            captured["headers"] = kw.get("headers")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, params=None, **kw):
            captured["url"] = url
            captured["params"] = params
            return _Resp()

        async def aclose(self):
            return None

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    async with YelpCollector("sk_test") as client:
        out = await client.search(
            niche="roofing",
            region="New York",
            yelp_categories=("roofing",),
        )

    assert len(out) == 1
    lead = out[0]
    assert lead.source == "yelp"
    assert lead.source_id == "yelp_abc"
    assert lead.name == "Acme Roofing"
    assert lead.phone == "+15551112222"
    assert lead.rating == 4.5
    assert lead.reviews_count == 120
    assert lead.latitude == 40.71
    assert lead.longitude == -74.01
    assert lead.category == "Roofing"
    assert "1 Broadway" in (lead.address or "")
    assert captured["headers"]["Authorization"] == "Bearer sk_test"
    assert captured["params"]["categories"] == "roofing"
    assert captured["params"]["location"] == "New York"


@pytest.mark.asyncio
async def test_search_uses_bbox_centroid_when_provided(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class _Resp:
        status_code = 200
        text = ""

        def json(self) -> dict[str, Any]:
            return {"businesses": []}

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, params=None, **kw):
            captured["params"] = params
            return _Resp()

        async def aclose(self):
            return None

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    async with YelpCollector("sk_test") as client:
        await client.search(
            niche="roofing",
            region="New York",
            yelp_categories=("roofing",),
            bbox=(40.0, -74.5, 41.0, -73.5),
        )

    # Centre of (40,-74.5)..(41,-73.5) → (40.5, -74.0)
    assert captured["params"]["latitude"] == "40.500000"
    assert captured["params"]["longitude"] == "-74.000000"
    # ``location`` should NOT be set when we have a bbox — Yelp would
    # otherwise prefer the textual location and ignore lat/long.
    assert "location" not in captured["params"]
    # Half-height 0.5° lat ≈ 55_500m, well under the 40km Yelp cap → 40_000.
    assert captured["params"]["radius"] == "40000"


@pytest.mark.asyncio
async def test_401_raises(monkeypatch) -> None:
    class _Resp:
        status_code = 401
        text = '{"error": "VALIDATION_ERROR"}'

        def json(self) -> dict[str, Any]:
            return {}

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, *a, **kw):
            return _Resp()

        async def aclose(self):
            return None

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    with pytest.raises(YelpError):
        async with YelpCollector("sk_test") as client:
            await client.search(
                niche="x",
                region="y",
                yelp_categories=("roofing",),
            )


@pytest.mark.asyncio
async def test_429_returns_empty_silently(monkeypatch) -> None:
    """A daily-budget burnout should degrade the search, not fail it."""

    class _Resp:
        status_code = 429
        text = ""

        def json(self) -> dict[str, Any]:
            return {}

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, *a, **kw):
            return _Resp()

        async def aclose(self):
            return None

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    async with YelpCollector("sk_test") as client:
        out = await client.search(
            niche="x",
            region="y",
            yelp_categories=("roofing",),
        )
    assert out == []
