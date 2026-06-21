"""Email sequence CRUD and enrollment routes (Wave 12 routes/sequences.py)."""

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
from sqlalchemy.pool import StaticPool

from leadgen.adapters.web_api import auth as auth_mod
from leadgen.db import session as db_session_mod
from leadgen.db.models import Base, EmailSequence, Lead, SearchQuery, User
from leadgen.utils import rate_limit as rate_limit_mod


@pytest_asyncio.fixture
async def db_engine():
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
        "sequence_create_limiter",
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


# ── Helpers ──────────────────────────────────────────────────────────────


_STEPS = [
    {"day": 0, "subject": "Hi {name}", "body": "First touch"},
    {"day": 3, "subject": "Follow-up", "body": "Still interested?"},
]


@pytest.mark.asyncio
async def test_create_and_list_sequence(patched_session_factory):
    user = User(id=1, email="u@example.com")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    client = _client_for(user)
    resp = client.post(
        "/api/v1/sequences",
        json={"name": "Cold outreach", "steps": _STEPS},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["name"] == "Cold outreach"
    assert data["steps_count"] == 2
    seq_id = data["id"]

    resp = client.get("/api/v1/sequences")
    assert resp.status_code == 200, resp.text
    seqs = resp.json()
    assert len(seqs) == 1
    assert seqs[0]["id"] == seq_id
    assert len(seqs[0]["steps"]) == 2


@pytest.mark.asyncio
async def test_list_sequences_scoped_to_user(patched_session_factory):
    user1 = User(id=1, email="u1@example.com")
    user2 = User(id=2, email="u2@example.com")
    async with patched_session_factory() as s:
        s.add_all([user1, user2])
        await s.commit()

    _client_for(user1).post(
        "/api/v1/sequences",
        json={"name": "User1 seq", "steps": _STEPS},
    )

    resp = _client_for(user2).get("/api/v1/sequences")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_delete_sequence(patched_session_factory):
    user = User(id=1, email="u@example.com")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    client = _client_for(user)
    resp = client.post(
        "/api/v1/sequences",
        json={"name": "Delete me", "steps": _STEPS},
    )
    seq_id = resp.json()["id"]

    resp = client.delete(f"/api/v1/sequences/{seq_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == seq_id

    resp = client.get("/api/v1/sequences")
    assert resp.json() == []


@pytest.mark.asyncio
async def test_delete_sequence_wrong_user_returns_404(patched_session_factory):
    user1 = User(id=1, email="u1@example.com")
    user2 = User(id=2, email="u2@example.com")
    async with patched_session_factory() as s:
        s.add_all([user1, user2])
        await s.commit()

    resp = _client_for(user1).post(
        "/api/v1/sequences",
        json={"name": "Private", "steps": _STEPS},
    )
    seq_id = resp.json()["id"]

    resp = _client_for(user2).delete(f"/api/v1/sequences/{seq_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_sequence_empty_steps_returns_400(patched_session_factory):
    user = User(id=1, email="u@example.com")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    resp = _client_for(user).post(
        "/api/v1/sequences",
        json={"name": "Empty", "steps": []},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_enroll_lead_and_list_enrollments(patched_session_factory):
    user = User(id=1, email="u@example.com")
    q = SearchQuery(
        id=uuid.uuid4(), user_id=1, niche="roofing", region="NY", scope="city"
    )
    lead = Lead(
        id=uuid.uuid4(),
        query_id=q.id,
        name="Roof Co",
        source="google",
        source_id="g1",
    )
    async with patched_session_factory() as s:
        s.add_all([user, q, lead])
        await s.commit()

    client = _client_for(user)
    resp = client.post(
        "/api/v1/sequences",
        json={"name": "Enroll test", "steps": _STEPS},
    )
    seq_id = resp.json()["id"]

    resp = client.post(
        f"/api/v1/sequences/{seq_id}/enroll",
        json={"lead_id": str(lead.id)},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "enrollment_id" in data
    assert data["steps_total"] == 2

    resp = client.get(f"/api/v1/sequences/{seq_id}/enrollments")
    assert resp.status_code == 200, resp.text
    enrollments = resp.json()
    assert len(enrollments) == 1
    assert enrollments[0]["lead_id"] == str(lead.id)
    assert enrollments[0]["status"] == "active"
    assert enrollments[0]["current_step"] == 0
