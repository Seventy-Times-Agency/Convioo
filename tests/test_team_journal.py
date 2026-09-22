"""Журнал действий команды: запись, чтение, права.

Журнал — аргумент в споре «кто это сделал», поэтому проверяем три
вещи: строка переживает удаление актора (имя снято в момент записи),
лента отдаётся только владельцу и админу, и сбой журнала не роняет
само действие.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.core.services import team_journal
from leadgen.core.services.team_permissions import (
    PERM_VIEW_AUDIT_LOG,
    has_permission,
)
from leadgen.db.models import Base, Team, TeamActionLog, User
from leadgen.db.models.journal import (
    JK_BATCH_ASSIGNED,
    JK_COST_CAP_CHANGED,
)


@pytest_asyncio.fixture
async def session_factory():
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


async def _team_with_user(session) -> tuple[Team, User]:
    user = User(id=1, email="a@b.c", display_name="Роман")
    team = Team(id=uuid.uuid4(), name="t")
    session.add_all([user, team])
    await session.flush()
    return team, user


@pytest.mark.asyncio
async def test_record_snapshots_actor_name(session_factory):
    async with session_factory() as session:
        team, user = await _team_with_user(session)
        await team_journal.record(
            session,
            team.id,
            JK_BATCH_ASSIGNED,
            actor=user,
            actor_role="admin",
            payload={"count": 5},
        )
        await session.commit()

        row = (
            await session.execute(select(TeamActionLog))
        ).scalar_one()
        assert row.actor_name == "Роман"
        assert row.actor_role == "admin"
        assert row.payload == {"count": 5}

        # Актор ушёл — строка осталась читаемой.
        await session.delete(user)
        await session.commit()
        row = (
            await session.execute(select(TeamActionLog))
        ).scalar_one()
        assert row.actor_name == "Роман"


@pytest.mark.asyncio
async def test_system_rows_have_no_actor(session_factory):
    async with session_factory() as session:
        team, _user = await _team_with_user(session)
        await team_journal.record(
            session,
            team.id,
            "search_finished",
            payload={"leads": 12},
        )
        await session.commit()
        row = (
            await session.execute(
                select(TeamActionLog).where(
                    TeamActionLog.kind == "search_finished"
                )
            )
        ).scalar_one()
        assert row.actor_id is None
        assert row.actor_name is None


@pytest.mark.asyncio
async def test_record_failure_does_not_raise(session_factory):
    """Кривой payload не должен ронять действие — только warning."""
    async with session_factory() as session:
        team, user = await _team_with_user(session)
        # object_label с не-строкой споткнётся на срезе — record
        # обязан проглотить и не поднять.
        await team_journal.record(
            session,
            team.id,
            JK_COST_CAP_CHANGED,
            actor=user,
            object_label=12345,  # type: ignore[arg-type]
        )
        await session.commit()


def test_journal_visibility_is_admin_and_owner_only():
    assert has_permission("owner", PERM_VIEW_AUDIT_LOG)
    assert has_permission("admin", PERM_VIEW_AUDIT_LOG)
    assert not has_permission("manager", PERM_VIEW_AUDIT_LOG)
    assert not has_permission("sales", PERM_VIEW_AUDIT_LOG)


# ── API-уровень: эндпоинт журнала ──────────────────────────────────────


@pytest_asyncio.fixture
async def db_engine():
    from sqlalchemy.ext.asyncio import create_async_engine as _cae
    from sqlalchemy.pool import StaticPool

    engine = _cae(
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


def _register(client, email: str) -> int:
    from leadgen.utils import rate_limit as rate_limit_mod

    rate_limit_mod.register_limiter._events.clear()
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "J",
            "last_name": "L",
            "email": email,
            "password": "correcthorse123",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


@pytest.mark.asyncio
async def test_journal_endpoint_gating_and_filters(patched_session_factory):
    from fastapi.testclient import TestClient

    from leadgen.adapters.web_api import create_app
    from leadgen.db.models import TeamMembership

    admin_c = TestClient(create_app())
    sales_c = TestClient(create_app())
    admin_id = _register(admin_c, "jr-admin@example.test")
    sales_id = _register(sales_c, "jr-sales@example.test")

    team_id = uuid.uuid4()
    async with patched_session_factory() as session:
        session.add(Team(id=team_id, name="Dept"))
        session.add(
            TeamMembership(team_id=team_id, user_id=admin_id, role="admin")
        )
        session.add(
            TeamMembership(team_id=team_id, user_id=sales_id, role="sales")
        )
        session.add(
            TeamActionLog(
                team_id=team_id,
                actor_id=admin_id,
                actor_name="Роман",
                actor_role="admin",
                kind=JK_COST_CAP_CHANGED,
                payload={"from": None, "to": 150.0},
            )
        )
        session.add(
            TeamActionLog(
                team_id=team_id,
                kind="search_finished",
                payload={"leads": 12, "tokens": 12},
            )
        )
        await session.commit()

    # Селзу лента не видна.
    r = sales_c.get(f"/api/v1/teams/{team_id}/journal")
    assert r.status_code == 403

    # Админ видит обе строки, свежие сверху.
    r = admin_c.get(f"/api/v1/teams/{team_id}/journal")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["entries"]) == 2
    assert "cost_cap_changed" in body["kinds"]

    # Фильтр по типу.
    r = admin_c.get(
        f"/api/v1/teams/{team_id}/journal", params={"kind": "search_finished"}
    )
    assert [e["kind"] for e in r.json()["entries"]] == ["search_finished"]
    assert r.json()["entries"][0]["actor_id"] is None

    # Фильтр по актору.
    r = admin_c.get(
        f"/api/v1/teams/{team_id}/journal", params={"actor_id": admin_id}
    )
    assert [e["kind"] for e in r.json()["entries"]] == ["cost_cap_changed"]
