"""Wave-1 cost control: team spend aggregation, the monthly ceiling
(80% warn / 100% stop), the owner-only cap endpoint and the
pre-launch estimate."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.core.services import usage_tracker
from leadgen.core.services.cost_control import (
    COST_PER_ENRICHED_LEAD_USD,
    estimate_search_cost,
    get_team_cost_status,
)
from leadgen.db import session as db_session_mod
from leadgen.db.models import Base, Team, TeamMembership
from leadgen.utils import cache as cache_mod
from leadgen.utils import rate_limit as rate_limit_mod


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
    maker = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr(db_session_mod, "_engine", db_engine)
    monkeypatch.setattr(db_session_mod, "_session_factory", maker)
    return maker


@pytest.fixture(autouse=True)
def _clean_usage_cache():
    cache_mod._INMEM.clear()
    yield
    cache_mod._INMEM.clear()


def _client(patched_session_factory) -> TestClient:
    from leadgen.adapters.web_api import create_app

    return TestClient(create_app())


def _register(client: TestClient, email: str) -> int:
    rate_limit_mod.register_limiter._events.clear()
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Cost",
            "last_name": "Ctl",
            "email": email,
            "password": "correcthorse123",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


async def _record_spend(user_id: int, place_details: int) -> None:
    token = usage_tracker.set_active_user(user_id)
    try:
        await usage_tracker.record("google_place_details", place_details)
    finally:
        usage_tracker.reset_active_user(token)


def test_estimate_math():
    assert COST_PER_ENRICHED_LEAD_USD > 0.03
    assert estimate_search_cost(200) == round(
        200 * COST_PER_ENRICHED_LEAD_USD, 2
    )


@pytest.mark.asyncio
async def test_team_status_aggregates_and_thresholds(
    patched_session_factory,
):
    team_id = uuid.uuid4()
    async with patched_session_factory() as session:
        session.add(
            Team(
                id=team_id,
                name="Dept",
                monthly_cost_cap_usd=Decimal("1.00"),
            )
        )
        session.add(
            TeamMembership(team_id=team_id, user_id=101, role="owner")
        )
        session.add(
            TeamMembership(team_id=team_id, user_id=102, role="manager")
        )
        await session.commit()

    # 15 place-details = 15 * $0.028 = $0.42 → below 80%.
    await _record_spend(101, 15)
    async with patched_session_factory() as session:
        status = await get_team_cost_status(session, team_id)
    assert status.month_cost_usd == pytest.approx(0.42)
    assert not status.warning and not status.blocked

    # Second member pushes it past 80% ($0.42 + $0.42 = $0.84).
    await _record_spend(102, 15)
    async with patched_session_factory() as session:
        status = await get_team_cost_status(session, team_id)
    assert status.warning and not status.blocked

    # Past 100% → blocked.
    await _record_spend(102, 10)
    async with patched_session_factory() as session:
        status = await get_team_cost_status(session, team_id)
    assert status.blocked


@pytest.mark.asyncio
async def test_cap_endpoint_and_search_stop(patched_session_factory):
    owner_c = _client(patched_session_factory)
    mgr_c = _client(patched_session_factory)
    owner_id = _register(owner_c, "cost-owner@example.test")
    mgr_id = _register(mgr_c, "cost-mgr@example.test")
    team_id = uuid.uuid4()
    async with patched_session_factory() as session:
        session.add(Team(id=team_id, name="Dept"))
        session.add(
            TeamMembership(team_id=team_id, user_id=owner_id, role="owner")
        )
        session.add(
            TeamMembership(
                team_id=team_id, user_id=mgr_id, role="manager"
            )
        )
        # Verify emails so create_search reaches the cost gate.
        from datetime import datetime, timezone

        from leadgen.db.models import User

        for uid in (owner_id, mgr_id):
            u = await session.get(User, uid)
            u.email_verified_at = datetime.now(timezone.utc)
        await session.commit()

    # Manager can read usage but not set the cap.
    r = mgr_c.get(f"/api/v1/teams/{team_id}/usage")
    assert r.status_code == 200, r.text
    assert r.json()["cap_usd"] is None
    r = mgr_c.patch(
        f"/api/v1/teams/{team_id}/cost-cap",
        json={"monthly_cost_cap_usd": 100},
    )
    assert r.status_code == 403

    # Owner sets a tiny cap.
    r = owner_c.patch(
        f"/api/v1/teams/{team_id}/cost-cap",
        json={"monthly_cost_cap_usd": 0.5},
    )
    assert r.status_code == 200, r.text
    assert r.json()["cap_usd"] == 0.5

    # Spend past the cap → team search stops with a clear message.
    await _record_spend(mgr_id, 20)  # $0.56
    r = mgr_c.post(
        "/api/v1/searches",
        json={
            "niche": "bakery",
            "region": "Miami",
            "team_id": str(team_id),
        },
    )
    assert r.status_code == 402, r.text
    assert "потолок" in r.json()["detail"].lower()

    # Estimate endpoint answers for any authed user.
    r = mgr_c.get("/api/v1/searches/estimate", params={"leads": 200})
    assert r.status_code == 200
    assert r.json()["leads"] == 200
    assert r.json()["cost_usd"] == estimate_search_cost(200)
