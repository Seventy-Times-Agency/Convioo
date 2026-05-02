"""Pure-function tests for the geocode helpers (no Nominatim hit)."""

from __future__ import annotations

import math

from leadgen.utils.geocode import bbox_from_circle


def test_bbox_from_circle_zero_radius_collapses_to_point() -> None:
    south, west, north, east = bbox_from_circle(50.0, 10.0, 0)
    assert south == 50.0 and north == 50.0
    assert west == 10.0 and east == 10.0


def test_bbox_from_circle_latitude_offset_matches_111km_per_deg() -> None:
    # 111.32 km per degree latitude → 10 km radius ≈ 0.0898 degrees.
    s, _w, n, _e = bbox_from_circle(50.0, 10.0, 10_000)
    assert math.isclose((n - s) / 2, 10 / 111.32, abs_tol=0.001)


def test_bbox_from_circle_widens_longitude_near_equator() -> None:
    # At the equator longitude ≈ latitude in km/degree → bbox is ~square.
    s, w, n, e = bbox_from_circle(0.0, 0.0, 50_000)
    width = e - w
    height = n - s
    assert math.isclose(width, height, abs_tol=0.001)


def test_bbox_from_circle_narrows_longitude_at_high_latitude() -> None:
    # At 60°N a degree of longitude is half a degree of latitude in km,
    # so the bbox should be ~2× wider in longitude.
    s, w, n, e = bbox_from_circle(60.0, 10.0, 50_000)
    width = e - w
    height = n - s
    assert width > height * 1.8


def test_bbox_from_circle_handles_negative_radius_safely() -> None:
    # ``radius_m`` should be clamped at zero — caller passing a junk
    # value shouldn't produce a wraparound bbox.
    s, w, n, e = bbox_from_circle(50.0, 10.0, -100)
    assert s == n == 50.0
    assert w == e == 10.0
