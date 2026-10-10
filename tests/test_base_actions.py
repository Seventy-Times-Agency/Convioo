"""База: вкладки, фильтр по сессии, вернуть в базу, архив, удаление,
«нет контакта»; право продажника выбирать воронку."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from leadgen.db.models import Funnel, Lead, SearchQuery, TeamMembership

pytest_plugins = ["tests.test_team_roles_wave1"]


async def _leads(maker, crew, n: int, **kw) -> tuple[uuid.UUID, list[uuid.UUID]]:
    async with maker() as session:
        q = SearchQuery(
            id=uuid.uuid4(), user_id=crew["ids"]["owner"], team_id=crew["team_id"],
            niche="dentists", region="Kyiv", source="web", status="done",
        )
        session.add(q)
        ids = []
        for i in range(n):
            lead = Lead(query_id=q.id, name=f"L{i}", source="google_places", source_id=f"s-{uuid.uuid4()}", **kw)
            session.add(lead)
            await session.flush()
            ids.append(lead.id)
        await session.commit()
        return q.id, ids


@pytest.mark.asyncio
async def test_unassign_archive_delete_and_tabs(crew, patched_session_factory):
    team = crew["team_id"]
    sid, ids = await _leads(patched_session_factory, crew, 3, lead_status="new", owner_user_id=crew["ids"]["sales"])
    _, lost = await _leads(patched_session_factory, crew, 2, lead_status="lost")
    mgr, admin = crew["clients"]["manager"], crew["clients"]["admin"]
    url = f"/api/v1/teams/{team}/base/bulk"

    assert crew["clients"]["sales"].post(url, json={"lead_ids": [str(ids[0])], "action": "unassign"}).status_code == 403
    r = mgr.post(url, json={"lead_ids": [str(x) for x in ids[:2]], "action": "unassign"})
    assert r.json()["changed"] == 2
    async with patched_session_factory() as session:
        owners = (await session.execute(select(Lead.owner_user_id).where(Lead.id.in_(ids[:2])))).scalars().all()
    assert owners == [None, None]

    # Удалять может только владелец/РОП.
    assert mgr.post(url, json={"lead_ids": [str(ids[2])], "action": "delete"}).status_code == 403
    assert admin.post(url, json={"lead_ids": [str(ids[2])], "action": "delete"}).json()["changed"] == 1
    assert mgr.post(url, json={"lead_ids": [str(ids[1])], "action": "archive"}).json()["changed"] == 1

    facets = mgr.get("/api/v1/leads/facets", params={"team_id": str(team)}).json()
    assert facets["tabs"]["no_contact"] == 2 and facets["tabs"]["archive"] == 1
    assert any(s["id"] == str(sid) for s in facets["sessions"])

    # Фильтр по сессии и вкладка «Нет контакта».
    r = mgr.get("/api/v1/leads", params={"team_id": str(team), "bucket": "base", "session": str(sid)})
    assert {x["id"] for x in r.json()["leads"]} == {str(ids[0])}
    r = mgr.get("/api/v1/leads", params={"team_id": str(team), "bucket": "no_contact"})
    assert {x["id"] for x in r.json()["leads"]} == {str(x) for x in lost}

    # Вернуть из «Нет контакта» в работу.
    assert mgr.post(url, json={"lead_ids": [str(lost[0])], "action": "restore_contact"}).json()["changed"] == 1
    async with patched_session_factory() as session:
        assert (await session.get(Lead, lost[0])).lead_status == "new"


@pytest.mark.asyncio
async def test_sales_funnel_choice_permission(crew, patched_session_factory):
    team = crew["team_id"]
    async with patched_session_factory() as session:
        f = Funnel(id=uuid.uuid4(), team_id=team, name="Аудит", goal_name="Встреча")
        session.add(f)
        await session.commit()
        fid = f.id
    _, mine = await _leads(patched_session_factory, crew, 1, lead_status="new", owner_user_id=crew["ids"]["sales"])
    _, other = await _leads(patched_session_factory, crew, 1, lead_status="new", owner_user_id=crew["ids"]["sales2"])
    sales = crew["clients"]["sales"]
    assign = f"/api/v1/funnels/{fid}/assign"

    assert sales.post(assign, json={"lead_ids": [str(mine[0])]}).status_code == 403
    teams = {t["id"]: t for t in sales.get("/api/v1/teams").json()}
    assert teams[str(team)]["can_choose_funnel"] is False

    # Тимлид выдаёт право; руководителям его не выдают (есть по роли).
    url = f"/api/v1/teams/{team}/members/{crew['ids']['sales']}/funnel-choice"
    assert crew["clients"]["sales2"].patch(url, json={"enabled": True}).status_code == 403
    assert crew["clients"]["manager"].patch(url, json={"enabled": True}).json()["can_choose_funnel"] is True
    assert crew["clients"]["owner"].patch(
        f"/api/v1/teams/{team}/members/{crew['ids']['manager']}/funnel-choice", json={"enabled": True}
    ).status_code == 403

    teams = {t["id"]: t for t in sales.get("/api/v1/teams").json()}
    assert teams[str(team)]["can_choose_funnel"] is True
    r = sales.post(assign, json={"lead_ids": [str(mine[0]), str(other[0])]})
    assert r.status_code == 200, r.text
    async with patched_session_factory() as session:
        assert (await session.get(Lead, mine[0])).funnel_id == fid
        assert (await session.get(Lead, other[0])).funnel_id is None  # чужой лид не тронут
        ms = (
            await session.execute(
                select(TeamMembership).where(TeamMembership.user_id == crew["ids"]["sales"])
            )
        ).scalar_one()
        assert ms.can_choose_funnel is True
    # Передать лида другому — нельзя.
    r = sales.post(assign, json={"lead_ids": [str(mine[0])], "owner_user_id": crew["ids"]["sales2"]})
    assert r.status_code == 403
