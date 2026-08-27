"""Outreach template CRUD (routes/templates.py)."""

from __future__ import annotations

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
from leadgen.db.models import Base, User
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
async def test_create_and_list_template(patched_session_factory):
    user = User(id=1, email="u@example.com")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    client = _client_for(user)
    resp = client.post(
        "/api/v1/templates",
        json={
            "name": "Cold intro",
            "subject": "Quick question about {niche}",
            "body": "Hi {name}, I help {niche} companies...",
            "tone": "professional",
        },
    )
    assert resp.status_code == 200, resp.text
    tmpl = resp.json()
    assert tmpl["name"] == "Cold intro"
    assert tmpl["tone"] == "professional"
    tmpl_id = tmpl["id"]

    resp = client.get("/api/v1/templates")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == tmpl_id


@pytest.mark.asyncio
async def test_list_templates_user_scoped(patched_session_factory):
    user1 = User(id=1, email="u1@example.com")
    user2 = User(id=2, email="u2@example.com")
    async with patched_session_factory() as s:
        s.add_all([user1, user2])
        await s.commit()

    _client_for(user1).post(
        "/api/v1/templates",
        json={"name": "User1 template", "body": "Hello"},
    )

    resp = _client_for(user2).get("/api/v1/templates")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


@pytest.mark.asyncio
async def test_update_template(patched_session_factory):
    user = User(id=1, email="u@example.com")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    client = _client_for(user)
    resp = client.post(
        "/api/v1/templates",
        json={"name": "Original", "body": "Original body", "tone": "casual"},
    )
    tmpl_id = resp.json()["id"]

    resp = client.patch(
        f"/api/v1/templates/{tmpl_id}",
        json={"name": "Updated", "body": "Updated body", "tone": "formal"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["name"] == "Updated"
    assert data["body"] == "Updated body"
    assert data["tone"] == "formal"


@pytest.mark.asyncio
async def test_update_template_wrong_user_returns_404(patched_session_factory):
    user1 = User(id=1, email="u1@example.com")
    user2 = User(id=2, email="u2@example.com")
    async with patched_session_factory() as s:
        s.add_all([user1, user2])
        await s.commit()

    resp = _client_for(user1).post(
        "/api/v1/templates",
        json={"name": "Private", "body": "Secret"},
    )
    tmpl_id = resp.json()["id"]

    resp = _client_for(user2).patch(
        f"/api/v1/templates/{tmpl_id}",
        json={"name": "Hijacked"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_template(patched_session_factory):
    user = User(id=1, email="u@example.com")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    client = _client_for(user)
    resp = client.post(
        "/api/v1/templates",
        json={"name": "Delete me", "body": "Bye"},
    )
    tmpl_id = resp.json()["id"]

    resp = client.delete(f"/api/v1/templates/{tmpl_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    resp = client.get("/api/v1/templates")
    assert resp.json()["items"] == []


@pytest.mark.asyncio
async def test_delete_template_wrong_user_returns_404(patched_session_factory):
    user1 = User(id=1, email="u1@example.com")
    user2 = User(id=2, email="u2@example.com")
    async with patched_session_factory() as s:
        s.add_all([user1, user2])
        await s.commit()

    resp = _client_for(user1).post(
        "/api/v1/templates",
        json={"name": "Private", "body": "Secret"},
    )
    tmpl_id = resp.json()["id"]

    resp = _client_for(user2).delete(f"/api/v1/templates/{tmpl_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_tone_defaults_to_professional(patched_session_factory):
    user = User(id=1, email="u@example.com")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    resp = _client_for(user).post(
        "/api/v1/templates",
        json={"name": "No tone", "body": "Hi there"},
    )
    assert resp.status_code == 200
    assert resp.json()["tone"] == "professional"
