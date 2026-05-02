"""OsmCollector unit tests + niche → osm_tags integration.

We don't actually hit Nominatim or Overpass in tests — those would
be flaky and rude. Instead we exercise:
  - the niche → osm_tags resolution helper (taxonomy join);
  - the Overpass query string builder (deterministic);
  - the response parser (handles nodes, ways with center,
    missing names, missing coords).
"""

from __future__ import annotations

from leadgen.collectors.osm import OsmCollector
from leadgen.data.niches import find, match_niche

# ── niche resolution ─────────────────────────────────────────────────────


def test_match_niche_returns_canonical_entry_with_osm_tags() -> None:
    entry = match_niche("дантист")
    assert entry is not None
    assert entry.id == "dentists"
    assert "amenity=dentist" in entry.osm_tags
    assert "healthcare=dentist" in entry.osm_tags


def test_match_niche_returns_none_for_unknown_text() -> None:
    assert match_niche("xyzzy nonsense 42") is None


def test_curated_niches_have_at_least_some_osm_coverage() -> None:
    """Catch regressions where the YAML loses osm_tags wholesale."""
    entry = find("dentists")
    assert entry is not None and entry.osm_tags
    entry = find("restaurants")
    assert entry is not None and entry.osm_tags
    entry = find("law_firms")
    assert entry is not None and entry.osm_tags


# ── Overpass query builder ───────────────────────────────────────────────


def test_overpass_query_includes_every_tag_and_geometry_type() -> None:
    collector = OsmCollector()
    bbox = (52.0, 13.0, 52.5, 13.5)
    query = collector._build_overpass_query(
        ["amenity=dentist", "healthcare=dentist"], bbox
    )
    # Every tag × every geometry kind => 6 clauses.
    for tag in ("amenity", "healthcare"):
        for kind in ("node", "way", "relation"):
            assert f'{kind}["{tag}"="dentist"]' in query
    # Bounding box correctly inlined.
    assert "(52.0,13.0,52.5,13.5)" in query
    # ``out tags center`` so we get coords for ways too.
    assert "out tags center" in query


def test_overpass_query_skips_malformed_tags() -> None:
    collector = OsmCollector()
    bbox = (0.0, 0.0, 1.0, 1.0)
    query = collector._build_overpass_query(
        ["good=tag", "no_equals_sign", "= ", "key=", "=value"], bbox
    )
    # Only the good tag survives.
    assert query.count("[\"good\"=\"tag\"]") == 3  # node + way + relation
    # Malformed lines should not appear.
    assert "no_equals_sign" not in query


# ── parser ───────────────────────────────────────────────────────────────


def _node(name: str, **extra) -> dict:
    return {
        "type": "node",
        "id": 12345,
        "lat": 52.5,
        "lon": 13.4,
        "tags": {"name": name, **extra},
    }


def test_parser_handles_node_with_full_tags() -> None:
    collector = OsmCollector()
    raw = {
        "elements": [
            _node(
                "Acme Dental",
                amenity="dentist",
                website="https://acme-dental.example",
                phone="+49 30 1234567",
                **{
                    "addr:street": "Hauptstraße",
                    "addr:housenumber": "12",
                    "addr:city": "Berlin",
                    "addr:postcode": "10115",
                },
            ),
        ]
    }
    leads = collector._parse(raw)
    assert len(leads) == 1
    lead = leads[0]
    assert lead.name == "Acme Dental"
    assert lead.source == "osm"
    assert lead.source_id == "node/12345"
    assert lead.website == "https://acme-dental.example"
    assert lead.phone == "+49 30 1234567"
    assert "Hauptstraße 12" in lead.address
    assert "Berlin" in lead.address
    assert lead.category == "dentist"
    assert lead.latitude == 52.5
    assert lead.longitude == 13.4


def test_parser_uses_center_for_ways() -> None:
    collector = OsmCollector()
    raw = {
        "elements": [
            {
                "type": "way",
                "id": 99,
                "center": {"lat": 50.1, "lon": 8.7},
                "tags": {"name": "Big Clinic", "healthcare": "dentist"},
            }
        ]
    }
    leads = collector._parse(raw)
    assert len(leads) == 1
    assert leads[0].source_id == "way/99"
    assert leads[0].latitude == 50.1
    assert leads[0].longitude == 8.7
    assert leads[0].category == "dentist"


def test_parser_skips_unnamed_and_missing_coords() -> None:
    collector = OsmCollector()
    raw = {
        "elements": [
            {"type": "node", "id": 1, "lat": 1, "lon": 1, "tags": {"amenity": "dentist"}},
            {"type": "node", "id": 2, "lat": 1, "lon": 1, "tags": {"name": "  "}},
            # Way without ``center`` but with a name still gets through —
            # the lead just won't have coords (acceptable).
            {"type": "way", "id": 3, "tags": {"name": "Coordless"}},
        ]
    }
    leads = collector._parse(raw)
    assert [lead.source_id for lead in leads] == ["way/3"]
    assert leads[0].latitude is None and leads[0].longitude is None


def test_parser_dedups_same_source_id() -> None:
    collector = OsmCollector()
    raw = {
        "elements": [
            _node("Twin", amenity="cafe"),
            _node("Twin", amenity="cafe"),
        ]
    }
    leads = collector._parse(raw)
    assert len(leads) == 1
