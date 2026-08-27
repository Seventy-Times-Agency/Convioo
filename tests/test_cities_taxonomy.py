"""Curated cities catalogue: loader integrity, matcher, /api/v1/cities."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from leadgen.adapters.web_api import create_app
from leadgen.data.cities import all_cities, find, match_city, suggest


def test_catalogue_loads_at_least_100_entries() -> None:
    assert len(all_cities()) >= 100


def test_every_entry_has_unique_id() -> None:
    ids = [c.id for c in all_cities()]
    assert len(ids) == len(set(ids))


def test_every_entry_has_country_lat_lon() -> None:
    for entry in all_cities():
        assert entry.country and len(entry.country) == 2
        assert -90.0 <= entry.lat <= 90.0
        assert -180.0 <= entry.lon <= 180.0


def test_top_of_list_is_population_sorted() -> None:
    populations = [c.population for c in all_cities()[:10]]
    assert populations == sorted(populations, reverse=True)


def test_find_resolves_known_id() -> None:
    assert find("kyiv-ua") is not None
    assert find("KYIV-UA") is not None  # case-insensitive
    assert find("not-a-real-city") is None


def test_match_city_handles_localized_name() -> None:
    # Russian / Ukrainian names should still resolve to the canonical entry.
    assert (match_city("Лондон") or _).id == "london-gb"
    assert (match_city("Київ") or _).id == "kyiv-ua"
    assert (match_city("Berlin") or _).id == "berlin-de"


def test_match_city_returns_none_for_garbage() -> None:
    assert match_city("xyzzy nonsense 42") is None
    assert match_city("") is None
    assert match_city(None) is None


def test_suggest_filters_by_country() -> None:
    de_only = suggest(None, country="DE", limit=20)
    assert all(c.country == "DE" for c in de_only)
    assert any(c.id == "berlin-de" for c in de_only)


def test_suggest_returns_empty_for_unknown_country() -> None:
    assert suggest("Paris", country="ZZ", limit=5) == []


def test_suggest_prefers_exact_match() -> None:
    out = suggest("Lyon", limit=10)
    assert out[0].id == "lyon-fr"


# ── HTTP endpoint ────────────────────────────────────────────────────────


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_cities_endpoint_returns_top(client: TestClient) -> None:
    r = client.get("/api/v1/cities", params={"limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["query"] == ""
    assert len(body["items"]) == 5
    # Top-of-list should be one of the high-population entries.
    assert body["items"][0]["population"] >= 1000000


def test_cities_endpoint_filters_by_query_in_russian(client: TestClient) -> None:
    r = client.get(
        "/api/v1/cities",
        params={"q": "Берлин", "lang": "ru", "limit": 5},
    )
    assert r.status_code == 200
    items = r.json()["items"]
    ids = [i["id"] for i in items]
    assert "berlin-de" in ids
    berlin = next(i for i in items if i["id"] == "berlin-de")
    assert berlin["name"] == "Берлин"


def test_cities_endpoint_caps_limit(client: TestClient) -> None:
    r = client.get("/api/v1/cities", params={"limit": 0})
    assert r.status_code == 422
    r = client.get("/api/v1/cities", params={"limit": 51})
    assert r.status_code == 422


def test_cities_endpoint_country_filter(client: TestClient) -> None:
    r = client.get(
        "/api/v1/cities", params={"country": "UA", "limit": 30}
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert all(i["country"] == "UA" for i in items)
    assert any(i["id"] == "kyiv-ua" for i in items)


# Helper for the (None or _).id pattern used above.
class _Sentinel:
    id = "(none)"


_ = _Sentinel()
