"""Saved CRM segments: CRUD + ownership + team scoping."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

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
    LeadSegment,
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
async def test_create_and_list_private_segment(patched_session_factory):
    user = User(id=1, email="user@example.com")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    client = _client_for(user)
    resp = client.post(
        "/api/v1/segments",
        json={
            "name": "Hot leads from this week",
            "filter_json": {"smartFilter": "hot_week"},
        },
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["name"] == "Hot leads from this week"
    assert payload["team_id"] is None
    assert payload["filter_json"] == {"smartFilter": "hot_week"}

    listed = client.get("/api/v1/segments").json()
    assert len(listed["items"]) == 1
    assert listed["items"][0]["id"] == payload["id"]


@pytest.mark.asyncio
async def test_team_segment_visible_to_other_member(patched_session_factory):
    team_id = uuid.uuid4()
    owner = User(id=11, email="owner@example.com")
    other = User(id=12, email="other@example.com")
    async with patched_session_factory() as s:
        s.add_all(
            [
                owner,
                other,
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
    resp = owner_client.post(
        "/api/v1/segments",
        json={
            "name": "Team pipeline",
            "filter_json": {"status": "contacted"},
            "team_id": str(team_id),
        },
    )
    assert resp.status_code == 200, resp.text

    other_client = _client_for(other)
    listed = other_client.get("/api/v1/segments").json()
    assert len(listed["items"]) == 1
    assert listed["items"][0]["name"] == "Team pipeline"


@pytest.mark.asyncio
async def test_team_segment_rejected_for_non_member(patched_session_factory):
    team_id = uuid.uuid4()
    user = User(id=21, email="user@example.com")
    async with patched_session_factory() as s:
        s.add_all([user, Team(id=team_id, name="Strangers")])
        await s.commit()

    client = _client_for(user)
    resp = client.post(
        "/api/v1/segments",
        json={"name": "x", "filter_json": {}, "team_id": str(team_id)},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_only_owner(patched_session_factory):
    a = User(id=31, email="a@example.com")
    b = User(id=32, email="b@example.com")
    seg_id = uuid.uuid4()
    async with patched_session_factory() as s:
        s.add_all(
            [
                a,
                b,
                LeadSegment(
                    id=seg_id,
                    user_id=31,
                    team_id=None,
                    name="A's bookmark",
                    filter_json={},
                    sort_order=0,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                ),
            ]
        )
        await s.commit()

    # Owner can update
    owner_client = _client_for(a)
    r1 = owner_client.patch(
        f"/api/v1/segments/{seg_id}",
        json={"name": "Renamed"},
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["name"] == "Renamed"

    # Non-owner gets 404 (we hide existence)
    other_client = _client_for(b)
    r2 = other_client.patch(
        f"/api/v1/segments/{seg_id}",
        json={"name": "Hostile takeover"},
    )
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_delete_segment(patched_session_factory):
    user = User(id=41, email="user@example.com")
    seg_id = uuid.uuid4()
    async with patched_session_factory() as s:
        s.add_all(
            [
                user,
                LeadSegment(
                    id=seg_id,
                    user_id=41,
                    team_id=None,
                    name="bye",
                    filter_json={},
                    sort_order=0,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                ),
            ]
        )
        await s.commit()

    client = _client_for(user)
    r = client.delete(f"/api/v1/segments/{seg_id}")
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    listed = client.get("/api/v1/segments").json()
    assert listed["items"] == []


@pytest.mark.asyncio
async def test_filter_json_round_trips_unknown_keys(patched_session_factory):
    """Schema-less ``filter_json`` is the whole point — confirm new
    keys we haven't planned for survive a save / load cycle."""
    user = User(id=51, email="u@example.com")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    client = _client_for(user)
    payload = {
        "future_score_min": 80,
        "future_freshness_days": 30,
        "tag_ids": ["aaa", "bbb"],
        "nested": {"a": 1, "b": [True, False]},
    }
    r = client.post(
        "/api/v1/segments",
        json={"name": "future-proof", "filter_json": payload},
    )
    assert r.status_code == 200
    listed = client.get("/api/v1/segments").json()
    assert listed["items"][0]["filter_json"] == payload
