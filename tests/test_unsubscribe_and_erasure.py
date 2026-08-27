"""One-click unsubscribe (token, headers/footer, public endpoint) and
GDPR lead erasure by email."""

from __future__ import annotations

import base64
import uuid

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.core.services.suppression import is_suppressed
from leadgen.core.services.unsubscribe import (
    make_unsubscribe_token,
    parse_unsubscribe_token,
)
from leadgen.db import session as db_session_mod
from leadgen.db.models import Base, Lead, SearchQuery, User
from leadgen.integrations.gmail import build_raw_message


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


# ── token ────────────────────────────────────────────────────────────────


def test_unsubscribe_token_roundtrip():
    tok = make_unsubscribe_token(42, "Foo@Bar.com")
    parsed = parse_unsubscribe_token(tok)
    assert parsed == (42, "foo@bar.com")


def test_unsubscribe_token_tamper_rejected():
    tok = make_unsubscribe_token(42, "foo@bar.com")
    payload, _sig = tok.split(".", 1)
    forged = payload + ".deadbeef"
    assert parse_unsubscribe_token(forged) is None
    assert parse_unsubscribe_token("garbage") is None


# ── build_raw_message headers + footer ─────────────────────────────────────


def _decode(raw: str) -> str:
    return base64.urlsafe_b64decode(raw + "==").decode("utf-8")


def test_build_raw_message_adds_unsubscribe_when_url_given():
    raw = build_raw_message(
        from_addr="me@example.com",
        to_addr="lead@acme.com",
        subject="Hi",
        body="Hello",
        html_body="<p>Hello</p>",
        list_unsubscribe_url="https://app.example/api/v1/unsubscribe/tok",
    )
    decoded = _decode(raw)
    assert "List-Unsubscribe:" in decoded
    assert "One-Click" in decoded
    assert "unsubscribe/tok" in decoded.lower()


def test_build_raw_message_no_unsubscribe_by_default():
    raw = build_raw_message(
        from_addr="me@example.com",
        to_addr="lead@acme.com",
        subject="Hi",
        body="Hello",
    )
    assert "List-Unsubscribe" not in _decode(raw)


# ── public unsubscribe endpoint ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unsubscribe_endpoint_suppresses(patched_session_factory):
    from leadgen.adapters.web_api.app import create_app

    async with patched_session_factory() as session:
        session.add(User(id=7, email="me@example.com"))
        await session.commit()

    client = TestClient(create_app())
    token = make_unsubscribe_token(7, "stop@lead.com")

    # GET renders a confirmation page and suppresses.
    resp = client.get(f"/api/v1/unsubscribe/{token}")
    assert resp.status_code == 200
    assert "unsubscribed" in resp.text.lower()

    async with patched_session_factory() as session:
        assert (
            await is_suppressed(session, user_id=7, email="stop@lead.com")
            is True
        )

    # One-click POST is idempotent and returns 200.
    resp = client.post(f"/api/v1/unsubscribe/{token}")
    assert resp.status_code == 200
    assert resp.json()["unsubscribed"] is True

    # A tampered token is rejected.
    resp = client.get("/api/v1/unsubscribe/garbage.sig")
    assert resp.status_code == 400


# ── GDPR lead erasure by email ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_erase_lead_by_email(patched_session_factory):
    from leadgen.adapters.web_api import auth as auth_mod
    from leadgen.adapters.web_api.app import create_app

    user = User(id=200, email="me@example.com")
    query = SearchQuery(
        id=uuid.uuid4(),
        user_id=200,
        niche="dentist",
        region="NYC",
        scope="city",
    )
    match = Lead(
        id=uuid.uuid4(),
        query_id=query.id,
        name="Target Co",
        source="google",
        source_id="ChIJ1",
        contact_email="Target@Acme.com",
    )
    other = Lead(
        id=uuid.uuid4(),
        query_id=query.id,
        name="Other Co",
        source="google",
        source_id="ChIJ2",
        contact_email="someone@else.com",
    )
    async with patched_session_factory() as session:
        session.add_all([user, query, match, other])
        await session.commit()

    app = create_app()
    app.dependency_overrides[auth_mod.get_current_user] = lambda: user
    client = TestClient(app)

    resp = client.post(
        "/api/v1/leads/erase-by-email", json={"email": "target@acme.com"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["erased"] == 1

    async with patched_session_factory() as session:
        # The matching lead is gone, the other remains.
        assert await session.get(Lead, match.id) is None
        assert await session.get(Lead, other.id) is not None
        # And the erased address is now suppressed.
        assert (
            await is_suppressed(session, user_id=200, email="target@acme.com")
            is True
        )
