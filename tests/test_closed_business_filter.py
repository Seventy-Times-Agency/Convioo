"""Tests for closed-business filtering in GooglePlacesCollector._parse_place."""

from __future__ import annotations

import pytest

from leadgen.collectors.google_places import GooglePlacesCollector


@pytest.fixture
def collector() -> GooglePlacesCollector:
    return GooglePlacesCollector(api_key="dummy-key-for-parsing-only")


@pytest.mark.parametrize("status", ["CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"])
def test_closed_place_returns_none(
    collector: GooglePlacesCollector, status: str
) -> None:
    place = {
        "id": "abc123",
        "businessStatus": status,
        "displayName": {"text": "Shuttered Cafe"},
    }
    assert collector._parse_place(place) is None


def test_operational_place_returns_lead(collector: GooglePlacesCollector) -> None:
    place = {
        "id": "xyz789",
        "businessStatus": "OPERATIONAL",
        "displayName": {"text": "Live Cafe"},
    }
    lead = collector._parse_place(place)
    assert lead is not None
    assert lead.source_id == "xyz789"
    assert lead.name == "Live Cafe"


def test_missing_business_status_is_treated_as_operational(
    collector: GooglePlacesCollector,
) -> None:
    place = {"id": "no-status-123", "displayName": {"text": "Ambiguous"}}
    assert collector._parse_place(place) is not None


def test_missing_id_returns_none(collector: GooglePlacesCollector) -> None:
    place = {"displayName": {"text": "Orphan"}}
    assert collector._parse_place(place) is None
