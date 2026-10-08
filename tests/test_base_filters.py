"""Фильтры «Базы»: счётчики панели, отбор по продажнику/свободным,
нише, контактам, сортировка; селзу «База» закрыта."""

from __future__ import annotations

import pytest

from leadgen.db.models import Lead

pytest_plugins = ["tests.test_team_roles_wave1"]


@pytest.mark.asyncio
async def test_facets_and_filters(crew, patched_session_factory):
    async with patched_session_factory() as session:
        lead = await session.get(Lead, crew["other_lead"])
        lead.phone = "+380441234567"
        lead.score_ai = 82
        await session.commit()

    c = crew["clients"]["owner"]
    team = str(crew["team_id"])
    r = c.get("/api/v1/leads/facets", params={"team_id": team})
    assert r.status_code == 200, r.text
    f = r.json()
    assert f["total"] == 2 and f["free"] == 1
    assert [o["count"] for o in f["owners"]] == [1]
    assert f["niches"] == [{"value": "roofing", "count": 2}]
    assert f["contacts"]["phone"] == 1 and f["temps"]["hot"] == 1

    # Свободные — только нераспределённый лид.
    r = c.get("/api/v1/leads", params={"team_id": team, "bucket": "base", "owner": "free"})
    assert [x["id"] for x in r.json()["leads"]] == [str(crew["other_lead"])]
    # Продажник + свободные вместе — оба.
    r = c.get(
        "/api/v1/leads",
        params=[("team_id", team), ("bucket", "base"), ("owner", "free"), ("owner", str(crew["ids"]["sales"]))],
    )
    assert r.json()["total"] == 2
    # Контакты и ниша.
    r = c.get("/api/v1/leads", params={"team_id": team, "bucket": "base", "has_phone": True, "niche": "roofing"})
    assert r.json()["total"] == 1
    # Счётчик своей группы не обнуляется выбором в ней же.
    r = c.get("/api/v1/leads/facets", params={"team_id": team, "owner": "free"})
    assert r.json()["free"] == 1 and r.json()["owners"][0]["count"] == 1 and r.json()["total"] == 1
    # Сортировка по названию.
    r = c.get("/api/v1/leads", params={"team_id": team, "bucket": "base", "sort": "name", "order": "asc"})
    names = [x["name"] for x in r.json()["leads"]]
    assert names == sorted(names, key=str.lower)
    # Поиск по тексту на сервере.
    r = c.get("/api/v1/leads", params={"team_id": team, "bucket": "base", "q": "unassigned"})
    assert r.json()["total"] == 1

    # Селзу «База» закрыта.
    assert crew["clients"]["sales"].get("/api/v1/leads/facets", params={"team_id": team}).status_code == 403
