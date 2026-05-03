"""Admin overview: gating + counters."""

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
from leadgen.db import session as db_session_mod
from leadgen.db.models import (
    Base,
    Lead,
    SearchQuery,
    Team,
    User,
)
from leadgen.utils import rate_limit as rate_limit_mod


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


@pytest.mark.asyncio
async def test_admin_overview_404s_for_non_admin(patched_session_factory):
    user = User(id=1, email="u@example.com", is_admin=False)
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    r = _client_for(user).get("/api/v1/admin/overview")
    # 404 (not 403) so the route's existence stays hidden.
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_admin_overview_returns_counts(patched_session_factory):
    now = datetime.now(timezone.utc)

    admin = User(id=10, email="admin@example.com", is_admin=True, queries_used=42)
    paid_user = User(
        id=20,
        email="paid@example.com",
        plan="pro",
        plan_until=now + timedelta(days=10),
        queries_used=8,
    )
    trial_user = User(
        id=21,
        email="trial@example.com",
        plan="free",
        trial_ends_at=now + timedelta(days=3),
        queries_used=2,
    )
    expired_trial = User(
        id=22,
        email="exp@example.com",
        plan="free",
        trial_ends_at=now - timedelta(days=1),
    )

    team = Team(id=uuid.uuid4(), name="Crew")

    recent = SearchQuery(
        id=uuid.uuid4(),
        user_id=10,
        niche="x",
        region="y",
        scope="city",
        status="done",
        source="web",
        created_at=now - timedelta(days=2),
    )
    running = SearchQuery(
        id=uuid.uuid4(),
        user_id=10,
        niche="x",
        region="y",
        scope="city",
        status="running",
        source="web",
        created_at=now - timedelta(minutes=10),
    )
    failed_recent = SearchQuery(
        id=uuid.uuid4(),
        user_id=10,
        niche="x",
        region="y",
        scope="city",
        status="failed",
        source="web",
        created_at=now - timedelta(hours=3),
    )
    old_done = SearchQuery(
        id=uuid.uuid4(),
        user_id=10,
        niche="x",
        region="y",
        scope="city",
        status="done",
        source="web",
        created_at=now - timedelta(days=20),
    )

    lead_recent = Lead(
        id=uuid.uuid4(),
        query_id=recent.id,
        name="Co",
        source="google",
        source_id="g1",
        created_at=now - timedelta(days=1),
    )
    lead_old = Lead(
        id=uuid.uuid4(),
        query_id=old_done.id,
        name="Old Co",
        source="google",
        source_id="g2",
        created_at=now - timedelta(days=14),
    )

    async with patched_session_factory() as s:
        s.add_all(
            [
                admin,
                paid_user,
                trial_user,
                expired_trial,
                team,
                recent,
                running,
                failed_recent,
                old_done,
                lead_recent,
                lead_old,
            ]
        )
        await s.commit()

    client = _client_for(admin)
    r = client.get("/api/v1/admin/overview")
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["users_total"] == 4
    assert data["users_paid"] == 1
    assert data["users_trialing"] == 1
    assert data["teams_total"] == 1
    # 7d window catches recent + running + failed_recent (3); not old_done.
    assert data["searches_last_7d"] == 3
    assert data["searches_running"] == 1
    assert data["leads_last_7d"] == 1
    assert data["failed_searches_last_24h"] == 1

    # Top users sorted by queries_used desc — admin (42) should lead.
    top = data["top_users_by_searches"]
    assert top[0]["user_id"] == 10
    assert top[0]["queries_used"] == 42
    assert top[0]["is_admin"] is True
