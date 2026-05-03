"""Onboarding tour completion: PATCH /api/v1/users/me/onboarding-complete."""

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
async def test_complete_endpoint_stamps_timestamp(patched_session_factory):
    user = User(id=1, email="u@example.com", first_name="U")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    r = _client_for(user).patch("/api/v1/users/me/onboarding-complete")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["onboarding_tour_completed"] is True

    async with patched_session_factory() as s:
        row = await s.get(User, 1)
        assert row.onboarding_completed_at is not None


@pytest.mark.asyncio
async def test_complete_endpoint_idempotent(patched_session_factory):
    user = User(id=2, email="u2@example.com", first_name="U")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    client = _client_for(user)
    r1 = client.patch("/api/v1/users/me/onboarding-complete")
    assert r1.status_code == 200

    async with patched_session_factory() as s:
        first_stamp = (await s.get(User, 2)).onboarding_completed_at
        assert first_stamp is not None

    r2 = client.patch("/api/v1/users/me/onboarding-complete")
    assert r2.status_code == 200
    assert r2.json()["onboarding_tour_completed"] is True

    async with patched_session_factory() as s:
        # Second call must NOT bump the timestamp — idempotent.
        assert (await s.get(User, 2)).onboarding_completed_at == first_stamp


@pytest.mark.asyncio
async def test_auth_me_returns_flag(patched_session_factory):
    user = User(id=3, email="u3@example.com", first_name="U")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    client = _client_for(user)
    me = client.get("/api/v1/auth/me").json()
    assert me["onboarding_tour_completed"] is False

    client.patch("/api/v1/users/me/onboarding-complete")
    # The PATCH response itself reflects the new state.
    async with patched_session_factory() as s:
        refreshed = await s.get(User, 3)
    fresh_client = _client_for(refreshed)
    me = fresh_client.get("/api/v1/auth/me").json()
    assert me["onboarding_tour_completed"] is True
