"""Foursquare Places v3 collector: parser + bbox handling + auth."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from leadgen.collectors.foursquare import (
    FoursquareCollector,
    FoursquareError,
)
from leadgen.data.niches import _load


def test_fsq_categories_loaded_from_yaml() -> None:
    by_id = {entry.id: entry for entry in _load()}
    assert by_id["dentists"].fsq_categories == ("15014",)
    assert by_id["restaurants"].fsq_categories == ("13065",)
    assert by_id["cafes"].fsq_categories == ("13032",)
    # Unmapped niches should default to empty.
    assert by_id["roofing"].fsq_categories == ()


def test_collector_rejects_empty_key() -> None:
    with pytest.raises(FoursquareError):
        FoursquareCollector("")


@pytest.mark.asyncio
async def test_search_returns_empty_without_categories() -> None:
    out = await FoursquareCollector("k").search(
        niche="x", region="y", fsq_categories=()
    )
    assert out == []


@pytest.mark.asyncio
async def test_search_parses_payload(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class _Resp:
        status_code = 200
        text = ""

        def json(self) -> dict[str, Any]:
            return {
                "results": [
                    {
                        "fsq_id": "fsq_abc",
                        "name": "The Daily Grind",
                        "tel": "+12125551111",
                        "website": "https://daily.example",
                        "rating": 8.4,
                        "stats": {"total_ratings": 213},
                        "categories": [
                            {"id": "13032", "name": "Café"}
                        ],
                        "geocodes": {
                            "main": {"latitude": 40.71, "longitude": -74.0}
                        },
                        "location": {
                            "address": "10 Coffee St",
                            "locality": "New York",
                            "region": "NY",
                            "postcode": "10004",
                            "country": "US",
                        },
                    },
                    # Junk row → skipped, not crash
                    {"name": "no id"},
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
    async with FoursquareCollector("FSQ_KEY") as client:
        out = await client.search(
            niche="cafes",
            region="New York",
            fsq_categories=("13032",),
        )

    assert len(out) == 1
    lead = out[0]
    assert lead.source == "foursquare"
    assert lead.source_id == "fsq_abc"
    assert lead.name == "The Daily Grind"
    assert lead.phone == "+12125551111"
    assert lead.rating == 8.4
    assert lead.reviews_count == 213
    assert lead.latitude == 40.71
    assert lead.category == "Café"
    assert "10 Coffee St" in (lead.address or "")
    # FSQ v3 uses bare key (no "Bearer" prefix).
    assert captured["headers"]["Authorization"] == "FSQ_KEY"
    # No bbox supplied → ``near`` must carry the textual region.
    assert captured["params"]["near"] == "New York"
    assert captured["params"]["categories"] == "13032"


@pytest.mark.asyncio
async def test_search_uses_bbox_corners(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class _Resp:
        status_code = 200
        text = ""

        def json(self) -> dict[str, Any]:
            return {"results": []}

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
    async with FoursquareCollector("k") as client:
        await client.search(
            niche="x",
            region="y",
            fsq_categories=("13032",),
            bbox=(40.0, -74.5, 41.0, -73.5),
        )

    assert captured["params"]["sw"] == "40.000000,-74.500000"
    assert captured["params"]["ne"] == "41.000000,-73.500000"
    assert "near" not in captured["params"]


@pytest.mark.asyncio
async def test_401_raises(monkeypatch) -> None:
    class _Resp:
        status_code = 401
        text = "{}"

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
    with pytest.raises(FoursquareError):
        async with FoursquareCollector("k") as client:
            await client.search(
                niche="x",
                region="y",
                fsq_categories=("13032",),
            )


@pytest.mark.asyncio
async def test_429_returns_empty(monkeypatch) -> None:
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
    async with FoursquareCollector("k") as client:
        out = await client.search(
            niche="x",
            region="y",
            fsq_categories=("13032",),
        )
    assert out == []
