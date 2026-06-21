"""Email open tracking pixel endpoint (GET /api/v1/track/{token})."""

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

from leadgen.core.services.tracking import generate_track_token
from leadgen.db import session as db_session_mod
from leadgen.db.models import Base, Lead, LeadActivity, SearchQuery, User
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


@pytest.fixture
def client(patched_session_factory):
    from leadgen.adapters.web_api.app import create_app
    return TestClient(create_app())


@pytest_asyncio.fixture
async def lead_and_user(patched_session_factory):
    user = User(id=1, email="u@example.com")
    q = SearchQuery(
        id=uuid.uuid4(), user_id=1, niche="dentist", region="NY", scope="city"
    )
    lead = Lead(
        id=uuid.uuid4(),
        query_id=q.id,
        name="Test Co",
        source="google",
        source_id="g1",
    )
    async with patched_session_factory() as s:
        s.add_all([user, q, lead])
        await s.commit()
    return user, lead


def test_valid_token_returns_gif_pixel(client, lead_and_user):
    user, lead = lead_and_user
    token = generate_track_token(str(lead.id), str(user.id))

    resp = client.get(
        f"/api/v1/track/{token}",
        params={"lead_id": str(lead.id), "user_id": str(user.id)},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/gif"
    # GIF89a magic bytes
    assert resp.content[:6] == b"GIF89a"


def test_invalid_token_still_returns_gif(client, lead_and_user):
    _, lead = lead_and_user
    resp = client.get(
        "/api/v1/track/totallyinvalidtoken",
        params={"lead_id": str(lead.id), "user_id": "1"},
    )
    # Pixel must always return 200 — email clients can't handle errors.
    assert resp.status_code == 200
    assert "image/gif" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_valid_token_creates_activity(client, lead_and_user, patched_session_factory):
    user, lead = lead_and_user
    token = generate_track_token(str(lead.id), str(user.id))

    client.get(
        f"/api/v1/track/{token}",
        params={"lead_id": str(lead.id), "user_id": str(user.id)},
    )

    async with patched_session_factory() as s:
        from sqlalchemy import select
        rows = (
            await s.execute(
                select(LeadActivity).where(LeadActivity.lead_id == lead.id)
            )
        ).scalars().all()
    assert any(r.kind == "email_opened" for r in rows)


def test_missing_query_params_returns_422(client):
    resp = client.get("/api/v1/track/sometoken")
    assert resp.status_code == 422
