"""Команды внутри компании: CRUD, видимость, обратная совместимость.

Главное правило: компания без команд работает ровно как раньше
(squad_id везде NULL), а тимлид с командой видит своих людей и
свободный пул — не чужие карточки.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.core.services.squads import visible_member_ids
from leadgen.db.models import (
    Base,
    Lead,
    SearchQuery,
    Team,
    TeamMembership,
    TeamSquad,
)


@pytest_asyncio.fixture
async def db_engine():
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def patched_session_factory(monkeypatch, db_engine):
    from leadgen.db import session as db_session_mod

    maker = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr(db_session_mod, "_engine", db_engine)
    monkeypatch.setattr(db_session_mod, "_session_factory", maker)
    return maker


def _register(client, email):
    from leadgen.utils import rate_limit as rate_limit_mod

    rate_limit_mod.register_limiter._events.clear()
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "S",
            "last_name": "Q",
            "email": email,
            "password": "correcthorse123",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


@pytest.mark.asyncio
async def test_visibility_rules(patched_session_factory):
    team_id = uuid.uuid4()
    async with patched_session_factory() as session:
        session.add(Team(id=team_id, name="Компания"))
        squad = TeamSquad(team_id=team_id, name="Команда А", lead_user_id=2)
        session.add(squad)
        await session.flush()
        session.add_all(
            [
                TeamMembership(team_id=team_id, user_id=1, role="owner"),
                TeamMembership(
                    team_id=team_id, user_id=2, role="manager",
                    squad_id=squad.id,
                ),
                TeamMembership(
                    team_id=team_id, user_id=3, role="sales",
                    squad_id=squad.id,
                ),
                TeamMembership(team_id=team_id, user_id=4, role="sales"),
                TeamMembership(team_id=team_id, user_id=5, role="manager"),
            ]
        )
        await session.commit()

        # Владелец видит всё.
        assert await visible_member_ids(session, team_id, 1) is None
        # Тимлид без команды — как раньше, всё.
        assert await visible_member_ids(session, team_id, 5) is None
        # Тимлид с командой — только своих.
        ids = await visible_member_ids(session, team_id, 2)
        assert sorted(ids) == [2, 3]
        # Селз — правило не для него (его режет own-leads фильтр).
        assert await visible_member_ids(session, team_id, 3) is None


@pytest.mark.asyncio
async def test_squad_crud_and_scoped_crm(patched_session_factory):
    from leadgen.adapters.web_api import create_app

    rop_c = TestClient(create_app())
    lead_c = TestClient(create_app())
    rop_id = _register(rop_c, "sq-rop@example.test")
    tl_id = _register(lead_c, "sq-tl@example.test")
    outsider_id = _register(
        TestClient(create_app()), "sq-out@example.test"
    )

    team_id = uuid.uuid4()
    async with patched_session_factory() as session:
        session.add(Team(id=team_id, name="Компания"))
        session.add_all(
            [
                TeamMembership(team_id=team_id, user_id=rop_id, role="admin"),
                TeamMembership(
                    team_id=team_id, user_id=tl_id, role="manager"
                ),
                TeamMembership(
                    team_id=team_id, user_id=outsider_id, role="sales"
                ),
            ]
        )
        await session.commit()

    # РОП создаёт команду с тимлидом — тот привязывается сразу.
    r = rop_c.post(
        f"/api/v1/teams/{team_id}/squads",
        json={"name": "Команда А", "lead_user_id": tl_id},
    )
    assert r.status_code == 200, r.text
    squad_id = r.json()["id"]
    assert r.json()["lead_user_id"] == tl_id

    # Тимлид управлять командами не может.
    r = lead_c.post(
        f"/api/v1/teams/{team_id}/squads", json={"name": "Команда Б"}
    )
    assert r.status_code == 403

    # Список виден любому участнику.
    r = lead_c.get(f"/api/v1/teams/{team_id}/squads")
    assert r.status_code == 200
    assert r.json()["squads"][0]["member_count"] == 1

    # Лиды: свой селз, чужой селз и свободный.
    async with patched_session_factory() as session:
        q = SearchQuery(
            id=uuid.uuid4(),
            user_id=rop_id,
            team_id=team_id,
            niche="n",
            region="r",
            status="done",
            source="web",
        )
        session.add(q)
        await session.flush()
        session.add_all(
            [
                Lead(query_id=q.id, name="Мой", source="google",
                     source_id="a", owner_user_id=tl_id),
                Lead(query_id=q.id, name="Чужой", source="google",
                     source_id="b", owner_user_id=outsider_id),
                Lead(query_id=q.id, name="Свободный", source="google",
                     source_id="c"),
            ]
        )
        await session.commit()

    # Тимлид с командой: свои + свободный пул, без чужих.
    r = lead_c.get(f"/api/v1/leads?team_id={team_id}")
    assert r.status_code == 200, r.text
    names = {row["name"] for row in r.json()["leads"]}
    assert names == {"Мой", "Свободный"}

    # РОП видит всё.
    r = rop_c.get(f"/api/v1/leads?team_id={team_id}")
    assert {row["name"] for row in r.json()["leads"]} == {
        "Мой", "Чужой", "Свободный",
    }

    # Аналитика: у РОПа сводка по командам присутствует.
    r = rop_c.get(f"/api/v1/teams/{team_id}/analytics/calls")
    assert r.status_code == 200, r.text
    assert [sq["name"] for sq in r.json()["by_squad"]] == ["Команда А"]

    # Роспуск: люди в общий пул.
    r = rop_c.delete(f"/api/v1/squads/{squad_id}")
    assert r.status_code == 200
    r = lead_c.get(f"/api/v1/leads?team_id={team_id}")
    assert {row["name"] for row in r.json()["leads"]} == {
        "Мой", "Чужой", "Свободный",
    }
