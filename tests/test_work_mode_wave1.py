"""Wave-1 call mode: the rep's queue buckets and the one-button
call outcome endpoint."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.db import session as db_session_mod
from leadgen.db.models import (
    Base,
    Funnel,
    FunnelStep,
    Lead,
    LeadActivity,
    SearchQuery,
    Team,
    TeamMembership,
)
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


def _client(patched_session_factory) -> TestClient:
    from leadgen.adapters.web_api import create_app

    return TestClient(create_app())


def _register(client: TestClient, email: str) -> int:
    rate_limit_mod.register_limiter._events.clear()
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Work",
            "last_name": "Rep",
            "email": email,
            "password": "correcthorse123",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


@pytest_asyncio.fixture
async def setup(patched_session_factory):
    maker = patched_session_factory
    rep_client = _client(maker)
    rep_id = _register(rep_client, "rep@example.test")
    team_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    async with maker() as session:
        session.add(Team(id=team_id, name="Dept"))
        session.add(
            TeamMembership(team_id=team_id, user_id=rep_id, role="sales")
        )
        funnel = Funnel(
            id=uuid.uuid4(),
            team_id=team_id,
            name="Аудит-первый",
            status="active",
            goal_name="Платный аудит",
            goal_action="payment_calendar",
            no_answer_attempts=3,
            no_answer_pause_days=14,
        )
        funnel.steps = [
            FunnelStep(order_index=0, kind="call", day_offset=0),
            FunnelStep(order_index=1, kind="email", day_offset=1, auto=False),
        ]
        session.add(funnel)
        sq = SearchQuery(
            id=uuid.uuid4(),
            user_id=rep_id,
            team_id=team_id,
            niche="salons",
            region="Miami",
            status="done",
            source="web",
        )
        session.add(sq)
        await session.flush()

        def mk(name, source_id, **kw):
            return Lead(
                id=uuid.uuid4(),
                query_id=sq.id,
                name=name,
                source="google_places",
                source_id=source_id,
                lead_status="new",
                owner_user_id=rep_id,
                **kw,
            )

        callback = mk(
            "Callback Deli",
            "cb-1",
            funnel_id=funnel.id,
            next_touch_at=now - timedelta(hours=1),
            score_ai=60,
        )
        hot = mk("Hot Salon", "hot-1", funnel_id=funnel.id, score_ai=91)
        rest = mk("Cold Cafe", "rest-1", funnel_id=funnel.id, score_ai=40)
        done = mk(
            "Won Already",
            "won-1",
            funnel_id=funnel.id,
            score_ai=95,
            goal_reached_at=now,
        )
        foreign = Lead(
            id=uuid.uuid4(),
            query_id=sq.id,
            name="Not Mine",
            source="google_places",
            source_id="x-1",
            lead_status="new",
            score_ai=99,
        )
        session.add_all([callback, hot, rest, done, foreign])
        await session.commit()
        return {
            "client": rep_client,
            "rep_id": rep_id,
            "team_id": team_id,
            "funnel_id": funnel.id,
            "callback": callback.id,
            "hot": hot.id,
            "rest": rest.id,
        }


@pytest.mark.asyncio
async def test_queue_buckets(setup):
    r = setup["client"].get(
        "/api/v1/work/queue", params={"team_id": str(setup["team_id"])}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert [x["name"] for x in body["callbacks"]] == ["Callback Deli"]
    assert [x["name"] for x in body["hot"]] == ["Hot Salon"]
    assert [x["name"] for x in body["rest"]] == ["Cold Cafe"]
    # goal-reached and unassigned leads never enter the queue
    assert body["total"] == 3


@pytest.mark.asyncio
async def test_call_outcome_flow(setup, patched_session_factory):
    client = setup["client"]
    lead_id = setup["hot"]

    # Bad outcome name → 400.
    r = client.post(
        f"/api/v1/leads/{lead_id}/call-outcome", json={"outcome": "meh"}
    )
    assert r.status_code == 400

    # Thinking → advances to the email follow-up.
    r = client.post(
        f"/api/v1/leads/{lead_id}/call-outcome",
        json={"outcome": "thinking", "note": "думает про бюджет"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["result"]["next_step"] == 1

    # Goal → stamped + funnel goal config returned.
    r = client.post(
        f"/api/v1/leads/{lead_id}/call-outcome", json={"outcome": "goal"}
    )
    assert r.status_code == 200
    res = r.json()["result"]
    assert res["goal_reached"] is True
    assert res["goal_name"] == "Платный аудит"

    async with patched_session_factory() as session:
        lead = await session.get(Lead, lead_id)
        assert lead.goal_reached_at is not None
        acts = (
            (
                await session.execute(
                    select(LeadActivity)
                    .where(LeadActivity.lead_id == lead_id)
                    .where(LeadActivity.kind == "call")
                )
            )
            .scalars()
            .all()
        )
        assert len(acts) == 2
        assert acts[0].payload["note"] == "думает про бюджет"


@pytest.mark.asyncio
async def test_no_answer_releases_via_api(setup, patched_session_factory):
    client = setup["client"]
    lead_id = setup["rest"]
    for _ in range(3):
        r = client.post(
            f"/api/v1/leads/{lead_id}/call-outcome",
            json={"outcome": "no_answer"},
        )
        assert r.status_code == 200
    assert r.json()["result"].get("released") is True
    async with patched_session_factory() as session:
        lead = await session.get(Lead, lead_id)
        assert lead.owner_user_id is None  # back to the free pool

    # Released lead no longer in the rep's queue.
    r = client.get(
        "/api/v1/work/queue", params={"team_id": str(setup["team_id"])}
    )
    names = [
        x["name"]
        for k in ("callbacks", "hot", "rest")
        for x in r.json()[k]
    ]
    assert "Cold Cafe" not in names
