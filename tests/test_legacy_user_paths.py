"""Legacy /api/v1/users/{user_id}/* path redirects.

Cookie sessions own identity now, so the path-based id is redundant
and historically created an IDOR risk. The new canonical path is
``/api/v1/users/me/*``; the old paths return 308 to it (after a
``user_id == session_user.id`` check) so older clients still work.
"""

from __future__ import annotations

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
from leadgen.db.models import Base, User


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
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


def _client_for(user: User) -> TestClient:
    from leadgen.adapters.web_api.app import create_app

    async def _fake() -> User:
        return user

    app = create_app()
    app.dependency_overrides[auth_mod.get_current_user] = _fake
    return TestClient(app)


@pytest.mark.asyncio
async def test_legacy_get_user_redirects_to_me(patched_session_factory):
    user = User(id=1, email="u@example.com", first_name="U")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    client = _client_for(user)
    r = client.get("/api/v1/users/1", follow_redirects=False)
    assert r.status_code == 308
    assert r.headers["location"].startswith("/api/v1/users/me")


@pytest.mark.asyncio
async def test_legacy_audit_log_redirect(patched_session_factory):
    user = User(id=2, email="u2@example.com", first_name="U")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    r = _client_for(user).get(
        "/api/v1/users/2/audit-log", follow_redirects=False
    )
    assert r.status_code == 308
    assert "/api/v1/users/me/audit-log" in r.headers["location"]


@pytest.mark.asyncio
async def test_legacy_path_id_mismatch_is_403(patched_session_factory):
    """Closes the historical IDOR: the cookie's user_id wins."""
    real = User(id=10, email="real@example.com", first_name="R")
    async with patched_session_factory() as s:
        s.add(real)
        await s.commit()

    # The cookie says user 10, but the path attempts to access user 99.
    r = _client_for(real).get("/api/v1/users/99", follow_redirects=False)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_me_endpoint_returns_session_user(patched_session_factory):
    user = User(id=20, email="u20@example.com", first_name="X")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    r = _client_for(user).get("/api/v1/users/me")
    assert r.status_code == 200
    assert r.json()["user_id"] == 20


@pytest.mark.asyncio
async def test_legacy_redirect_preserves_query(patched_session_factory):
    user = User(id=30, email="u30@example.com", first_name="X")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    r = _client_for(user).get(
        "/api/v1/users/30/tasks?open_only=false&limit=5",
        follow_redirects=False,
    )
    assert r.status_code == 308
    assert "open_only=false" in r.headers["location"]
    assert "limit=5" in r.headers["location"]
