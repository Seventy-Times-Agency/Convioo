"""Оценка настройки до запуска: бесплатная разведка Google, история
команды по нише, противоречия, общий светофор."""

from __future__ import annotations

import uuid

import pytest

from leadgen.db.models import Lead, SearchQuery, TeamSeenLead

pytest_plugins = ["tests.test_team_roles_wave1"]


class _Scout:
    calls = 0

    def __init__(self, **_kw) -> None:
        pass

    async def scout_ids(self, niche, region, *, location_restriction_bbox=None):
        _Scout.calls += 1
        return [f"kyiv-{i}" for i in range(40)]


@pytest.fixture
def scout(monkeypatch):
    import leadgen.collectors.google_places as gp
    from leadgen.config import get_settings

    monkeypatch.setenv("DEMO_MODE", "0")
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    get_settings.cache_clear()
    monkeypatch.setattr(gp, "GooglePlacesCollector", _Scout)
    _Scout.calls = 0
    yield
    get_settings.cache_clear()


def _check(client, team_id, **kw):
    body = {
        "niche": "dentists",
        "cities": [{"region": "Kyiv"}],
        "limit": 50,
        "team_id": str(team_id),
        **kw,
    }
    r = client.post("/api/v1/searches/setup-check", json=body)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_scout_counts_fresh_and_flags_low_supply(crew, patched_session_factory, scout):
    async with patched_session_factory() as session:
        for i in range(30):
            session.add(
                TeamSeenLead(
                    team_id=crew["team_id"],
                    source="google_places",
                    source_id=f"kyiv-{i}",
                    first_user_id=crew["ids"]["owner"],
                )
            )
        await session.commit()

    out = _check(crew["clients"]["owner"], crew["team_id"])
    city = out["cities"][0]
    assert city["scouted"] is True
    assert city["fresh"] == 10 and city["already"] == 30
    assert city["level"] == "bad"
    assert {f["kind"] for f in city["fixes"]} == {"radius", "limit"}
    assert out["level"] == "bad"
    assert out["headline"]["key"] == "city_low"
    assert _Scout.calls == 11  # все нетронутые срезы, бесплатно


@pytest.mark.asyncio
async def test_history_filters_and_conflicts(crew, patched_session_factory, scout):
    async with patched_session_factory() as session:
        q = SearchQuery(
            id=uuid.uuid4(),
            user_id=crew["ids"]["owner"],
            team_id=crew["team_id"],
            niche="Dentists",
            region="Lviv",
            source="web",
            status="done",
        )
        session.add(q)
        for i, rating in enumerate([4.9, 4.6, 4.1, 3.8]):
            session.add(
                Lead(
                    query_id=q.id,
                    name=f"D{i}",
                    source="google_places",
                    source_id=f"h{i}",
                    rating=rating,
                    score_ai=80 if i == 0 else 50,
                    website="https://d.ua",
                )
            )
        await session.commit()

    out = _check(
        crew["clients"]["owner"],
        crew["team_id"],
        min_rating=4.5,
        website_filter="without",
        find_decision_makers=True,
    )
    by = {c["key"]: c for c in out["checks"]}
    assert by["filters_cut"]["params"]["cut"] == 100  # у всех есть сайт → «без сайта» отсечёт всех
    assert by["conflict_dm_no_site"]["level"] == "bad"
    assert by["quality"]["params"]["hot"] == 25
    assert out["level"] == "bad"


@pytest.mark.asyncio
async def test_good_setup_is_green(crew, patched_session_factory, scout):
    out = _check(crew["clients"]["owner"], crew["team_id"], limit=30)
    assert out["cities"][0]["expected"] == 30
    assert out["cities"][0]["level"] == "good"
    assert out["totals"]["tokens_max"] == 30
    assert out["level"] in ("good", "fair")  # без истории качество неизвестно
    assert crew["clients"]["sales"].post(
        "/api/v1/searches/setup-check",
        json={"niche": "dentists", "cities": [{"region": "Kyiv"}], "team_id": str(uuid.uuid4())},
    ).status_code == 403
