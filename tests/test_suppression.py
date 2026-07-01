"""Recipient-level email suppression: service helpers, the management
API, and enforcement in the lead send path."""

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

from leadgen.config import get_settings
from leadgen.core.services.oauth_store import save_tokens
from leadgen.core.services.suppression import (
    add_suppression,
    is_suppressed,
    list_suppressions,
    normalize_email,
    remove_suppression,
)
from leadgen.db import session as db_session_mod
from leadgen.db.models import Base, Lead, SearchQuery, User
from leadgen.integrations.gmail import TokenSet


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


@pytest.fixture
def gmail_env(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "google_oauth_client_id", "client-x", raising=False)
    monkeypatch.setattr(
        s, "google_oauth_client_secret", "secret-x", raising=False
    )
    monkeypatch.setattr(
        s,
        "google_oauth_redirect_uri",
        "https://convioo.com/api/v1/oauth/gmail/callback",
        raising=False,
    )
    return s


# ── normalize_email ──────────────────────────────────────────────────────


def test_normalize_email_lowercases_and_trims():
    assert normalize_email("  Foo@Bar.COM ") == "foo@bar.com"
    assert normalize_email(None) == ""
    assert normalize_email("") == ""


# ── service helpers ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_is_suppressed_remove_roundtrip(patched_session_factory):
    async with patched_session_factory() as session:
        session.add(User(id=1, email="me@example.com"))
        await session.commit()

        assert (
            await is_suppressed(session, user_id=1, email="x@target.com")
            is False
        )

        await add_suppression(
            session, user_id=1, email="X@Target.com", reason="unsub"
        )
        await session.commit()

        # Case-insensitive match against the normalized stored value.
        assert (
            await is_suppressed(session, user_id=1, email="x@target.com")
            is True
        )
        # Scoped per user: another user is unaffected.
        assert (
            await is_suppressed(session, user_id=2, email="x@target.com")
            is False
        )

        removed = await remove_suppression(
            session, user_id=1, email="x@target.com"
        )
        await session.commit()
        assert removed is True
        assert (
            await is_suppressed(session, user_id=1, email="x@target.com")
            is False
        )


@pytest.mark.asyncio
async def test_add_suppression_is_idempotent(patched_session_factory):
    async with patched_session_factory() as session:
        session.add(User(id=1, email="me@example.com"))
        await session.commit()

        first = await add_suppression(session, user_id=1, email="a@b.com")
        await session.commit()
        second = await add_suppression(session, user_id=1, email="a@b.com")
        await session.commit()

        assert first is not None and second is not None
        assert first.id == second.id
        rows = await list_suppressions(session, user_id=1)
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_add_suppression_empty_email_is_noop(patched_session_factory):
    async with patched_session_factory() as session:
        session.add(User(id=1, email="me@example.com"))
        await session.commit()
        assert await add_suppression(session, user_id=1, email="  ") is None
        assert await list_suppressions(session, user_id=1) == []


# ── management API ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_suppression_api_crud(patched_session_factory):
    from leadgen.adapters.web_api import auth as auth_mod
    from leadgen.adapters.web_api.app import create_app

    user = User(id=7, email="me@example.com")
    async with patched_session_factory() as session:
        session.add(user)
        await session.commit()

    app = create_app()
    app.dependency_overrides[auth_mod.get_current_user] = lambda: user
    client = TestClient(app)

    # create
    resp = client.post(
        "/api/v1/suppressions",
        json={"email": "Stop@Me.com", "reason": "unsubscribed"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == "stop@me.com"

    # list
    resp = client.get("/api/v1/suppressions")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["email"] == "stop@me.com"
    assert items[0]["source"] == "manual"

    # delete
    resp = client.delete("/api/v1/suppressions/stop@me.com")
    assert resp.status_code == 204

    resp = client.get("/api/v1/suppressions")
    assert resp.json()["items"] == []

    # deleting a non-suppressed address is a 404
    resp = client.delete("/api/v1/suppressions/never@there.com")
    assert resp.status_code == 404


# ── enforcement in the send path ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_email_blocked_for_suppressed_recipient(
    patched_session_factory, gmail_env, monkeypatch
):
    from leadgen.adapters.web_api import auth as auth_mod
    from leadgen.adapters.web_api.app import create_app

    user = User(id=99, email="u@example.com")
    query = SearchQuery(
        id=uuid.uuid4(),
        user_id=99,
        niche="dentist",
        region="NYC",
        scope="city",
    )
    lead_id = uuid.uuid4()
    lead = Lead(
        id=lead_id,
        query_id=query.id,
        name="Acme Dental",
        source="google",
        source_id="ChIJfake",
        website_meta={"emails": ["target@acme.com"]},
    )

    async with patched_session_factory() as session:
        session.add_all([user, query, lead])
        await session.commit()
        await save_tokens(
            session,
            user_id=99,
            provider="gmail",
            tokens=TokenSet(
                access_token="acc",
                refresh_token="ref",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
                scope=None,
            ),
            account_email="u@example.com",
        )
        # Suppress the lead's recipient address.
        await add_suppression(
            session, user_id=99, email="target@acme.com", reason="unsub"
        )
        await session.commit()

    sent = {"called": False}

    async def _fake_send(*, access_token, raw_message, **kw):
        sent["called"] = True
        return {"id": "msg", "threadId": "thr"}

    monkeypatch.setattr(
        "leadgen.integrations.gmail.send_message", _fake_send
    )

    app = create_app()
    app.dependency_overrides[auth_mod.get_current_user] = lambda: user
    client = TestClient(app)

    resp = client.post(
        f"/api/v1/leads/{lead_id}/send-email",
        json={"subject": "Hi", "body": "Hello"},
    )
    assert resp.status_code == 403, resp.text
    assert "suppress" in resp.json()["detail"].lower()
    # The provider must never be hit for a suppressed recipient.
    assert sent["called"] is False
