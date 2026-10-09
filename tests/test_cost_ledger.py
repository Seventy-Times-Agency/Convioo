"""Журнал трат: каждая трата с командой, поиском и этапом; экономика
запуска — полная стоимость, на результат и сгоревшее с причинами."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from leadgen.adapters.web_api.routes import _helpers as helpers_mod
from leadgen.core.services.search import usage_tracker
from leadgen.db.models import CostEvent, SearchQuery
from leadgen.pipeline.search import FUNNELS

pytest_plugins = ["tests.test_team_roles_wave1"]


async def _search(maker, crew, **kw) -> uuid.UUID:
    async with maker() as session:
        q = SearchQuery(
            id=uuid.uuid4(),
            user_id=crew["ids"]["owner"],
            team_id=crew["team_id"],
            niche="dentists",
            region="Kyiv",
            source="web",
            max_results=50,
            **kw,
        )
        session.add(q)
        await session.commit()
        return q.id


async def _spend(search_id, team_id, items):
    tokens = usage_tracker.bind_search(search_id, team_id)
    try:
        for stage, service, units in items:
            await usage_tracker.record(service, units, stage=stage)
    finally:
        usage_tracker.unbind_search(tokens)


@pytest.mark.asyncio
async def test_record_writes_ledger_with_context_and_override(
    crew, patched_session_factory, monkeypatch
):
    from leadgen.config import get_settings

    monkeypatch.setenv("COST_OVERRIDES_JSON", '{"hunter_credit": 0.5}')
    get_settings.cache_clear()
    try:
        sid = await _search(patched_session_factory, crew, status="running")
        await _spend(sid, crew["team_id"], [("discovery", "google_text_search", 3), ("decision_maker", "hunter_credit", 2)])
        async with patched_session_factory() as session:
            rows = (await session.execute(select(CostEvent).where(CostEvent.search_id == sid))).scalars().all()
        by = {r.service: r for r in rows}
        assert by["google_text_search"].cost_usd == pytest.approx(0.105)
        assert by["hunter_credit"].cost_usd == pytest.approx(1.0)
        assert by["hunter_credit"].stage == "decision_maker"
        assert all(r.team_id == crew["team_id"] for r in rows)
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_economics_split_useful_and_wasted(crew, patched_session_factory):
    sid = await _search(patched_session_factory, crew, status="done", leads_count=20)
    # Поиск по карте $0.40, досье 25 лидов по $0.04 = $1.00.
    await _spend(
        sid,
        crew["team_id"],
        [("discovery", "google_text_search", 0.4 / 0.035), ("enrichment", "google_place_details", 40)],
    )
    FUNNELS[sid] = {"found": 50, "duplicates": 20, "prefiltered": 5, "excluded": 5, "delivered": 20}
    await helpers_mod.finish_search_run(sid)
    async with patched_session_factory() as session:
        eco = (await session.get(SearchQuery, sid)).economics
    assert eco["cost_usd"] == pytest.approx(1.4, abs=1e-3)
    # Дубли: 20/50 от $0.40; фильтры: 5/50; исключённые: 5/25 от $1.00.
    assert eco["wasted_by_reason"]["duplicates"] == pytest.approx(0.16, abs=1e-3)
    assert eco["wasted_by_reason"]["prefiltered"] == pytest.approx(0.04, abs=1e-3)
    assert eco["wasted_by_reason"]["excluded"] == pytest.approx(0.2, abs=1e-3)
    assert eco["useful_usd"] == pytest.approx(1.0, abs=1e-3)
    assert eco["cost_per_delivered_usd"] == pytest.approx(0.07, abs=1e-3)


@pytest.mark.asyncio
async def test_failed_run_burns_everything_and_team_report(crew, patched_session_factory):
    sid = await _search(patched_session_factory, crew, status="running")
    await _spend(sid, crew["team_id"], [("discovery", "google_text_search", 2)])
    await helpers_mod.finish_search_run(sid)  # не закрыт статус → failed
    async with patched_session_factory() as session:
        eco = (await session.get(SearchQuery, sid)).economics
    assert eco["wasted_by_reason"] == {"failed": pytest.approx(0.07)}

    team = crew["team_id"]
    assert crew["clients"]["admin"].get(f"/api/v1/teams/{team}/economics").status_code == 403
    r = crew["clients"]["owner"].get(f"/api/v1/teams/{team}/economics")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["wasted_by_reason"]["failed"] == pytest.approx(0.07)
    assert body["total_usd"] == pytest.approx(0.07)
    assert any(s["id"] == str(sid) for s in body["searches"])


@pytest.mark.asyncio
async def test_admin_cost_prices_override_applies_to_new_spend(crew, patched_session_factory):
    from leadgen.db.models import User

    owner = crew["clients"]["owner"]
    # Не админ платформы — маршрута «нет».
    assert owner.get("/api/v1/admin/cost-prices").status_code == 404
    async with patched_session_factory() as session:
        (await session.get(User, crew["ids"]["owner"])).is_admin = True
        await session.commit()

    rows = {r["service"]: r for r in owner.get("/api/v1/admin/cost-prices").json()}
    assert rows["hunter_credit"]["effective_usd"] == pytest.approx(0.07)
    assert rows["hunter_credit"]["override_usd"] is None

    r = owner.put("/api/v1/admin/cost-prices/hunter_credit", json={"price_usd": 0.2})
    assert r.status_code == 200, r.text
    # Новый сервис, которого нет в коде.
    r = owner.put("/api/v1/admin/cost-prices/serpapi_call", json={"price_usd": 0.01})
    rows = {x["service"]: x for x in r.json()}
    assert rows["hunter_credit"]["effective_usd"] == pytest.approx(0.2)
    assert rows["serpapi_call"]["default_usd"] is None
    assert owner.put("/api/v1/admin/cost-prices/Bad Name!", json={"price_usd": 1}).status_code in (404, 422)

    sid = await _search(patched_session_factory, crew, status="running")
    await _spend(sid, crew["team_id"], [("decision_maker", "hunter_credit", 1), ("other", "serpapi_call", 3)])
    async with patched_session_factory() as session:
        rows = (await session.execute(select(CostEvent).where(CostEvent.search_id == sid))).scalars().all()
    by = {e.service: e.cost_usd for e in rows}
    assert by["hunter_credit"] == pytest.approx(0.2)
    assert by["serpapi_call"] == pytest.approx(0.03)

    # Снять правку — снова цена из кода.
    r = owner.put("/api/v1/admin/cost-prices/hunter_credit", json={"price_usd": None})
    rows = {x["service"]: x for x in r.json()}
    assert rows["hunter_credit"]["effective_usd"] == pytest.approx(0.07)
    usage_tracker.invalidate_prices()
    usage_tracker._db_prices.clear()
