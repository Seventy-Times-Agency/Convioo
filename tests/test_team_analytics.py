"""Team analytics endpoint: owner gating + aggregations."""

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
    TeamMembership,
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
async def test_team_analytics_owner_only(patched_session_factory):
    owner = User(id=1, email="o@x.com")
    member = User(id=2, email="m@x.com")
    team_id = uuid.uuid4()
    team = Team(id=team_id, name="Crew")
    own_m = TeamMembership(team_id=team_id, user_id=1, role="owner")
    mem_m = TeamMembership(team_id=team_id, user_id=2, role="member")
    async with patched_session_factory() as s:
        s.add_all([owner, member, team, own_m, mem_m])
        await s.commit()

    # Member gets 403.
    r = _client_for(member).get(f"/api/v1/teams/{team_id}/analytics")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_team_analytics_aggregates(patched_session_factory):
    now = datetime.now(timezone.utc)
    owner = User(id=1, email="o@x.com", display_name="Owner")
    member = User(id=2, email="m@x.com", display_name="Mem")
    team_id = uuid.uuid4()
    team = Team(id=team_id, name="Crew")
    own_m = TeamMembership(team_id=team_id, user_id=1, role="owner")
    mem_m = TeamMembership(team_id=team_id, user_id=2, role="member")

    s1 = SearchQuery(
        id=uuid.uuid4(),
        user_id=1,
        team_id=team_id,
        niche="dental",
        region="Berlin",
        scope="city",
        status="done",
        source="web",
        created_at=now - timedelta(days=2),
    )
    s2 = SearchQuery(
        id=uuid.uuid4(),
        user_id=2,
        team_id=team_id,
        niche="dental",
        region="Munich",
        scope="city",
        status="done",
        source="web",
        created_at=now - timedelta(days=1),
    )
    leads = [
        Lead(
            id=uuid.uuid4(),
            query_id=s1.id,
            name="Co1",
            source="google",
            source_id="g1",
            score_ai=80,
            lead_status="new",
            enriched=True,
            created_at=now - timedelta(days=2),
        ),
        Lead(
            id=uuid.uuid4(),
            query_id=s1.id,
            name="Co2",
            source="osm",
            source_id="o1",
            score_ai=40,
            lead_status="contacted",
            enriched=True,
            created_at=now - timedelta(days=2),
        ),
        Lead(
            id=uuid.uuid4(),
            query_id=s2.id,
            name="Co3",
            source="google",
            source_id="g2",
            score_ai=90,
            lead_status="new",
            enriched=True,
            created_at=now - timedelta(days=1),
        ),
    ]

    async with patched_session_factory() as s:
        s.add_all([owner, member, team, own_m, mem_m, s1, s2, *leads])
        await s.commit()

    r = _client_for(owner).get(f"/api/v1/teams/{team_id}/analytics")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["searches_total"] == 2
    assert data["leads_total"] == 3
    assert data["avg_lead_score"] == 70.0
    assert data["top_source"]["source"] == "google"
    assert data["top_source"]["leads_count"] == 2
    assert data["top_niche"]["niche"] == "dental"
    assert data["top_niche"]["searches_total"] == 2
    member_ids = {m["user_id"] for m in data["members"]}
    assert member_ids == {1, 2}
    assert any(p["leads_total"] > 0 for p in data["timeseries"])
