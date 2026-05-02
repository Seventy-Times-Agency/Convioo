"""Niche taxonomy: loader integrity + matcher behaviour + HTTP endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from leadgen.adapters.web_api import create_app
from leadgen.data.niches import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    all_niches,
    find,
    suggest,
)

# ── Loader integrity ─────────────────────────────────────────────────────


def test_taxonomy_loads_at_least_50_entries() -> None:
    entries = all_niches()
    assert len(entries) >= 50


def test_every_entry_has_unique_id() -> None:
    ids = [e.id for e in all_niches()]
    assert len(ids) == len(set(ids))


def test_every_entry_has_english_label() -> None:
    # The matcher falls back to ``en`` when the requested language is
    # missing, so an entry without an English label would be unrenderable.
    for entry in all_niches():
        assert "en" in entry.labels, f"{entry.id} is missing an English label"


def test_every_entry_uses_supported_language_codes_only() -> None:
    for entry in all_niches():
        for code in entry.labels:
            assert code in SUPPORTED_LANGUAGES, (
                f"{entry.id} uses unsupported language {code!r}"
            )


def test_find_resolves_known_id() -> None:
    assert find("dentists") is not None
    assert find("DENTISTS") is not None  # case-insensitive
    assert find("totally-fake-niche") is None


# ── Matcher ──────────────────────────────────────────────────────────────


def test_empty_query_returns_curated_top() -> None:
    out = suggest("", limit=5)
    assert len(out) == 5
    # Order matches the YAML so the curated top-of-list is preserved.
    assert out[0].id == all_niches()[0].id


def test_substring_match_works() -> None:
    out = [n.id for n in suggest("roof", limit=5)]
    assert "roofing" in out


def test_alias_match_in_other_language() -> None:
    # User typing the Russian word for dentists must land on the
    # canonical entry even though the English label says "Dentists".
    out = [n.id for n in suggest("дантист", limit=5)]
    assert "dentists" in out


def test_match_prioritises_exact_over_substring() -> None:
    # "bars" (id=bars) should rank above any niche where "bars" is just
    # a substring (e.g. nothing right now, but the rule still holds).
    out = suggest("bars", limit=10)
    assert out[0].id == "bars"


def test_label_returns_requested_language_with_english_fallback() -> None:
    entry = find("dentists")
    assert entry is not None
    assert entry.label("ru") == "Стоматологии"
    # Unknown language → English fallback.
    assert entry.label("xx") == entry.label(DEFAULT_LANGUAGE)


# ── HTTP endpoint ────────────────────────────────────────────────────────


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_endpoint_returns_top_when_query_missing(client: TestClient) -> None:
    r = client.get("/api/v1/niches", params={"limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["query"] == ""
    assert body["language"] == "en"
    assert len(body["items"]) == 5


def test_endpoint_filters_by_query_in_russian(client: TestClient) -> None:
    r = client.get(
        "/api/v1/niches",
        params={"q": "стомат", "lang": "ru", "limit": 5},
    )
    assert r.status_code == 200
    items = r.json()["items"]
    ids = [i["id"] for i in items]
    assert "dentists" in ids
    # Russian label is what the SPA renders in the dropdown.
    dentists = next(i for i in items if i["id"] == "dentists")
    assert dentists["label"] == "Стоматологии"


def test_endpoint_falls_back_to_english_for_unknown_language(
    client: TestClient,
) -> None:
    r = client.get("/api/v1/niches", params={"q": "roof", "lang": "xx"})
    assert r.status_code == 200
    body = r.json()
    assert body["language"] == "en"
    assert any(i["id"] == "roofing" for i in body["items"])


def test_endpoint_caps_limit(client: TestClient) -> None:
    # ``ge=1, le=50`` on the schema — out-of-range should 422.
    r = client.get("/api/v1/niches", params={"limit": 0})
    assert r.status_code == 422
    r = client.get("/api/v1/niches", params={"limit": 51})
    assert r.status_code == 422
