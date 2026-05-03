"""Saved + scheduled searches: schedule math, CRUD, dispatch loop."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.adapters.web_api import auth as auth_mod
from leadgen.core.services.saved_searches import (
    VALID_SCHEDULES,
    build_search_query,
    dispatch_due,
    next_run_after,
)
from leadgen.db import session as db_session_mod
from leadgen.db.models import (
    Base,
    SavedSearch,
    SearchQuery,
    Team,
    TeamMembership,
    User,
)
from leadgen.utils import rate_limit as rate_limit_mod

# ── Schedule math ────────────────────────────────────────────────────────


def test_next_run_after_unknown_schedule_returns_none() -> None:
    assert next_run_after(None) is None
    assert next_run_after("") is None
    assert next_run_after("yearly") is None


def test_next_run_after_advances_by_known_interval() -> None:
    now = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)
    assert next_run_after("daily", now=now) == now + timedelta(days=1)
    assert next_run_after("weekly", now=now) == now + timedelta(days=7)
    assert next_run_after("biweekly", now=now) == now + timedelta(days=14)
    assert next_run_after("monthly", now=now) == now + timedelta(days=30)


def test_valid_schedules_set() -> None:
    assert {"daily", "weekly", "biweekly", "monthly"} == VALID_SCHEDULES


# ── DB fixtures ──────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def patched_session_factory(monkeypatch, db_engine):
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db_session_mod, "_engine", db_engine)
    monkeypatch.setattr(db_session_mod, "_session_factory", maker)
    return maker


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    for name in (
        "login_limiter",
        "register_limiter",
        "forgot_password_limiter",
        "forgot_email_limiter",
        "reset_password_limiter",
        "resend_verification_limiter",
    ):
        getattr(rate_limit_mod, name)._events.clear()
    yield


def _client_for(user: User) -> TestClient:
    from leadgen.adapters.web_api.app import create_app

    async def _fake() -> User:
        return user

    app = create_app()
    app.dependency_overrides[auth_mod.get_current_user] = _fake
    return TestClient(app)


# ── CRUD via HTTP ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_saved_search_with_schedule(patched_session_factory):
    user = User(id=1, email="u@example.com")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    client = _client_for(user)
    resp = client.post(
        "/api/v1/saved-searches",
        json={
            "name": "NYC roofing weekly",
            "niche": "roofing",
            "region": "New York",
            "scope": "city",
            "schedule": "weekly",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["schedule"] == "weekly"
    assert data["next_run_at"] is not None
    assert data["active"] is True


@pytest.mark.asyncio
async def test_create_saved_search_with_off_schedule(patched_session_factory):
    user = User(id=2, email="u@example.com")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    client = _client_for(user)
    resp = client.post(
        "/api/v1/saved-searches",
        json={
            "name": "Manual only",
            "niche": "dentist",
            "region": "Berlin",
            "scope": "city",
            "schedule": "off",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["schedule"] is None
    assert data["next_run_at"] is None


@pytest.mark.asyncio
async def test_invalid_schedule_returns_400(patched_session_factory):
    user = User(id=3, email="u@example.com")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    client = _client_for(user)
    resp = client.post(
        "/api/v1/saved-searches",
        json={
            "name": "x",
            "niche": "y",
            "region": "z",
            "schedule": "yearly",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_patch_changes_schedule_and_recomputes_next_run(
    patched_session_factory,
):
    user = User(id=4, email="u@example.com")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    client = _client_for(user)
    created = client.post(
        "/api/v1/saved-searches",
        json={
            "name": "x",
            "niche": "y",
            "region": "z",
            "schedule": "weekly",
        },
    ).json()
    saved_id = created["id"]

    patched = client.patch(
        f"/api/v1/saved-searches/{saved_id}",
        json={"schedule": "monthly"},
    ).json()
    assert patched["schedule"] == "monthly"

    # Switching to "off" should null out next_run_at.
    patched2 = client.patch(
        f"/api/v1/saved-searches/{saved_id}",
        json={"schedule": "off"},
    ).json()
    assert patched2["schedule"] is None
    assert patched2["next_run_at"] is None


@pytest.mark.asyncio
async def test_team_saved_search_visible_to_member(patched_session_factory):
    team_id = uuid.uuid4()
    owner = User(id=11, email="o@example.com")
    member = User(id=12, email="m@example.com")
    async with patched_session_factory() as s:
        s.add_all(
            [
                owner,
                member,
                Team(id=team_id, name="Crew"),
                TeamMembership(
                    id=uuid.uuid4(),
                    user_id=11,
                    team_id=team_id,
                    role="owner",
                ),
                TeamMembership(
                    id=uuid.uuid4(),
                    user_id=12,
                    team_id=team_id,
                    role="member",
                ),
            ]
        )
        await s.commit()

    owner_client = _client_for(owner)
    create_resp = owner_client.post(
        "/api/v1/saved-searches",
        json={
            "name": "Team weekly",
            "niche": "y",
            "region": "z",
            "schedule": "weekly",
            "team_id": str(team_id),
        },
    )
    assert create_resp.status_code == 200, create_resp.text

    member_client = _client_for(member)
    listed = member_client.get("/api/v1/saved-searches").json()
    assert any(it["name"] == "Team weekly" for it in listed["items"])


@pytest.mark.asyncio
async def test_delete_only_owner(patched_session_factory):
    a = User(id=21, email="a@example.com")
    b = User(id=22, email="b@example.com")
    saved = SavedSearch(
        id=uuid.uuid4(),
        user_id=21,
        team_id=None,
        name="A's saved",
        niche="x",
        region="y",
        scope="city",
        active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    async with patched_session_factory() as s:
        s.add_all([a, b, saved])
        await s.commit()

    other_client = _client_for(b)
    r = other_client.delete(f"/api/v1/saved-searches/{saved.id}")
    assert r.status_code == 404

    owner_client = _client_for(a)
    r2 = owner_client.delete(f"/api/v1/saved-searches/{saved.id}")
    assert r2.status_code == 200


# ── dispatch_due ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatch_due_runs_only_overdue_rows(patched_session_factory):
    user = User(id=31, email="u@example.com")
    now = datetime.now(timezone.utc)
    overdue = SavedSearch(
        id=uuid.uuid4(),
        user_id=31,
        name="overdue",
        niche="x",
        region="y",
        scope="city",
        schedule="weekly",
        next_run_at=now - timedelta(minutes=5),
        active=True,
        created_at=now,
        updated_at=now,
    )
    future = SavedSearch(
        id=uuid.uuid4(),
        user_id=31,
        name="future",
        niche="x",
        region="y",
        scope="city",
        schedule="weekly",
        next_run_at=now + timedelta(hours=12),
        active=True,
        created_at=now,
        updated_at=now,
    )
    inactive = SavedSearch(
        id=uuid.uuid4(),
        user_id=31,
        name="inactive",
        niche="x",
        region="y",
        scope="city",
        schedule="weekly",
        next_run_at=now - timedelta(hours=1),
        active=False,
        created_at=now,
        updated_at=now,
    )
    manual = SavedSearch(
        id=uuid.uuid4(),
        user_id=31,
        name="manual-only",
        niche="x",
        region="y",
        scope="city",
        schedule=None,
        next_run_at=None,
        active=True,
        created_at=now,
        updated_at=now,
    )
    async with patched_session_factory() as s:
        s.add_all([user, overdue, future, inactive, manual])
        await s.commit()

    fired: list[uuid.UUID] = []

    async def _runner(saved: SavedSearch, session):
        fired.append(saved.id)
        return None

    async with patched_session_factory() as session:
        count = await dispatch_due(session, run_search=_runner, now=now)
        assert count == 1
        assert fired == [overdue.id]
        # next_run_at should have advanced one weekly slot. SQLite
        # strips tzinfo so we re-attach UTC for the comparison.
        refreshed = await session.get(SavedSearch, overdue.id)
        assert refreshed.next_run_at is not None
        naive_next = (
            refreshed.next_run_at
            if refreshed.next_run_at.tzinfo is not None
            else refreshed.next_run_at.replace(tzinfo=timezone.utc)
        )
        assert naive_next > now


@pytest.mark.asyncio
async def test_build_search_query_copies_axes(patched_session_factory):
    saved = SavedSearch(
        id=uuid.uuid4(),
        user_id=99,
        name="x",
        niche="dentist",
        region="Berlin",
        scope="metro",
        radius_m=25_000,
        max_results=30,
        target_languages=["de", "en"],
        active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    q = build_search_query(saved)
    assert isinstance(q, SearchQuery)
    assert q.niche == "dentist"
    assert q.region == "Berlin"
    assert q.scope == "metro"
    assert q.radius_m == 25_000
    assert q.max_results == 30
    assert q.target_languages == ["de", "en"]
    assert q.status == "pending"
    assert q.source == "web"
