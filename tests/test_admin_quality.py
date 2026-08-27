"""Admin quality dashboard: gating + payload shape."""

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
from leadgen.db.models import Base, SearchQuery, User
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
async def test_admin_quality_404s_for_non_admin(patched_session_factory):
    user = User(id=1, email="u@example.com", is_admin=False)
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()
    r = _client_for(user).get("/api/v1/admin/quality")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_admin_quality_returns_payload(patched_session_factory):
    now = datetime.now(timezone.utc)
    admin = User(id=10, email="admin@example.com", is_admin=True)
    fast = SearchQuery(
        id=uuid.uuid4(),
        user_id=10,
        niche="dental",
        region="Berlin",
        scope="city",
        status="done",
        source="web",
        created_at=now - timedelta(minutes=30),
        finished_at=now - timedelta(minutes=29),
        leads_count=12,
    )
    slow = SearchQuery(
        id=uuid.uuid4(),
        user_id=10,
        niche="roofing",
        region="NYC",
        scope="city",
        status="done",
        source="web",
        created_at=now - timedelta(minutes=20),
        finished_at=now - timedelta(minutes=15),
        leads_count=30,
    )
    failed = SearchQuery(
        id=uuid.uuid4(),
        user_id=10,
        niche="x",
        region="y",
        scope="city",
        status="failed",
        source="web",
        created_at=now - timedelta(hours=1),
    )
    pending = SearchQuery(
        id=uuid.uuid4(),
        user_id=10,
        niche="x",
        region="y",
        scope="city",
        status="pending",
        source="web",
        created_at=now,
    )
    async with patched_session_factory() as s:
        s.add_all([admin, fast, slow, failed, pending])
        await s.commit()

    r = _client_for(admin).get("/api/v1/admin/quality")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["searches_total_24h"] == 4
    assert data["searches_failed_24h"] == 1
    assert 0 < data["searches_failure_rate_24h"] < 1
    assert data["queue_pending"] == 1
    assert data["queue_running"] == 0
    assert len(data["slowest_searches"]) == 2
    # The 5-minute "slow" search must come ahead of the 1-minute "fast".
    assert data["slowest_searches"][0]["niche"] == "roofing"
    assert data["slowest_searches"][0]["duration_seconds"] > data[
        "slowest_searches"
    ][1]["duration_seconds"]
    assert data["anthropic_estimated_spend_usd"] >= 0
