"""Gmail OAuth + send-as-user: code exchange, refresh, message build,
   token store + ensure_fresh_token, and the public-facing endpoints
   (Google + Gmail API mocked)."""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.config import get_settings
from leadgen.core.services.oauth_store import (
    OAuthStoreError,
    ensure_fresh_token,
    save_tokens,
)
from leadgen.core.services.secrets_vault import decrypt
from leadgen.db import session as db_session_mod
from leadgen.db.models import Base, Lead, OAuthCredential, SearchQuery, User
from leadgen.integrations.gmail import (
    GmailError,
    TokenSet,
    build_authorize_url,
    build_raw_message,
    exchange_code_for_tokens,
    refresh_access_token,
)
from leadgen.utils import rate_limit as rate_limit_mod

# ── build_authorize_url ──────────────────────────────────────────────────


def test_build_authorize_url_includes_required_params() -> None:
    url = build_authorize_url(
        client_id="client-abc",
        redirect_uri="https://convioo.com/api/v1/oauth/gmail/callback",
        state="42:nonce",
    )
    assert "client_id=client-abc" in url
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    # The scope param is space-separated and url-encoded as +/%20
    assert "gmail.send" in url
    assert "state=42%3Anonce" in url


# ── build_raw_message ────────────────────────────────────────────────────


def test_build_raw_message_round_trips_via_base64() -> None:
    raw = build_raw_message(
        from_addr="u@example.com",
        to_addr="u@example.com",
        subject="Hello",
        body="World",
    )
    # Should be urlsafe-b64 with no '=' padding
    assert "=" not in raw
    decoded = base64.urlsafe_b64decode(raw + "==").decode("utf-8")
    assert "From: u@example.com" in decoded
    assert "To: u@example.com" in decoded
    assert "Subject: Hello" in decoded
    assert "World" in decoded


# ── exchange_code_for_tokens / refresh ───────────────────────────────────


@pytest.mark.asyncio
async def test_exchange_code_for_tokens(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class _Resp:
        status_code = 200
        text = ""

        def json(self) -> dict[str, Any]:
            return {
                "access_token": "ya29.fake",
                "refresh_token": "1//refresh",
                "expires_in": 3600,
                "scope": "https://www.googleapis.com/auth/gmail.send",
                "token_type": "Bearer",
            }

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, data=None, **kw):
            captured["url"] = url
            captured["data"] = data
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    out = await exchange_code_for_tokens(
        "AUTH_CODE",
        client_id="cid",
        client_secret="csec",
        redirect_uri="https://x/cb",
    )
    assert isinstance(out, TokenSet)
    assert out.access_token == "ya29.fake"
    assert out.refresh_token == "1//refresh"
    assert captured["data"]["code"] == "AUTH_CODE"
    assert captured["data"]["grant_type"] == "authorization_code"


@pytest.mark.asyncio
async def test_exchange_raises_on_non_200(monkeypatch) -> None:
    class _Resp:
        status_code = 400
        text = '{"error":"invalid_grant"}'

        def json(self) -> dict[str, Any]:
            return {}

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, *a, **kw):
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    with pytest.raises(GmailError):
        await exchange_code_for_tokens(
            "x",
            client_id="cid",
            client_secret="csec",
            redirect_uri="r",
        )


@pytest.mark.asyncio
async def test_refresh_access_token_returns_fresh_bearer(monkeypatch) -> None:
    class _Resp:
        status_code = 200
        text = ""

        def json(self) -> dict[str, Any]:
            return {"access_token": "new", "expires_in": 3500}

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, *a, **kw):
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    out = await refresh_access_token(
        "1//refresh", client_id="cid", client_secret="csec"
    )
    assert out.access_token == "new"
    assert out.refresh_token is None
    assert (out.expires_at - datetime.now(timezone.utc)).total_seconds() > 3000


# ── DB fixtures ──────────────────────────────────────────────────────────


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


# ── save_tokens / ensure_fresh_token ─────────────────────────────────────


@pytest.mark.asyncio
async def test_save_tokens_inserts_then_updates(patched_session_factory):
    tokens = TokenSet(
        access_token="acc1",
        refresh_token="ref1",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scope="x",
    )
    async with patched_session_factory() as session:
        u = User(id=1, email="u@example.com")
        session.add(u)
        await session.commit()
        row = await save_tokens(
            session,
            user_id=1,
            provider="gmail",
            tokens=tokens,
            account_email="u@example.com",
        )
        assert decrypt(row.access_token_ciphertext) == "acc1"
        assert decrypt(row.refresh_token_ciphertext) == "ref1"

    # Update with a new access token but no new refresh token
    tokens2 = TokenSet(
        access_token="acc2",
        refresh_token=None,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        scope=None,
    )
    async with patched_session_factory() as session:
        row = await save_tokens(
            session,
            user_id=1,
            provider="gmail",
            tokens=tokens2,
            account_email=None,
        )
        assert decrypt(row.access_token_ciphertext) == "acc2"
        # Old refresh token preserved
        assert decrypt(row.refresh_token_ciphertext) == "ref1"


@pytest.mark.asyncio
async def test_ensure_fresh_token_skips_refresh_when_alive(
    patched_session_factory,
):
    tokens = TokenSet(
        access_token="alive",
        refresh_token="ref",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        scope=None,
    )
    async with patched_session_factory() as session:
        u = User(id=2, email="u@example.com")
        session.add(u)
        await session.commit()
        await save_tokens(
            session,
            user_id=2,
            provider="gmail",
            tokens=tokens,
            account_email=None,
        )
        fresh = await ensure_fresh_token(
            session, user_id=2, provider="gmail"
        )
        assert fresh.access_token == "alive"


@pytest.mark.asyncio
async def test_ensure_fresh_token_refreshes_when_expired(
    patched_session_factory, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "google_oauth_client_id", "cid", raising=False)
    monkeypatch.setattr(settings, "google_oauth_client_secret", "csec", raising=False)

    expired = TokenSet(
        access_token="old",
        refresh_token="ref",
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=10),
        scope=None,
    )

    async def _fake_refresh(refresh_token, **kw):
        assert refresh_token == "ref"
        return TokenSet(
            access_token="rotated",
            refresh_token=None,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scope="x",
        )

    monkeypatch.setattr(
        "leadgen.core.services.oauth_store.refresh_access_token",
        _fake_refresh,
    )

    async with patched_session_factory() as session:
        u = User(id=3, email="u@example.com")
        session.add(u)
        await session.commit()
        await save_tokens(
            session,
            user_id=3,
            provider="gmail",
            tokens=expired,
            account_email=None,
        )
        fresh = await ensure_fresh_token(
            session, user_id=3, provider="gmail"
        )
        assert fresh.access_token == "rotated"


@pytest.mark.asyncio
async def test_ensure_fresh_token_raises_without_refresh_token(
    patched_session_factory,
):
    expired = TokenSet(
        access_token="old",
        refresh_token=None,
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=10),
        scope=None,
    )
    async with patched_session_factory() as session:
        u = User(id=4, email="u@example.com")
        session.add(u)
        await session.commit()
        await save_tokens(
            session,
            user_id=4,
            provider="gmail",
            tokens=expired,
            account_email=None,
        )
        with pytest.raises(OAuthStoreError):
            await ensure_fresh_token(
                session, user_id=4, provider="gmail"
            )


@pytest.mark.asyncio
async def test_ensure_fresh_token_raises_when_not_connected(
    patched_session_factory,
):
    async with patched_session_factory() as session:
        u = User(id=5, email="u@example.com")
        session.add(u)
        await session.commit()
        with pytest.raises(OAuthStoreError):
            await ensure_fresh_token(
                session, user_id=5, provider="gmail"
            )


# ── Endpoints (with Google + Gmail mocked) ───────────────────────────────


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


def test_gmail_endpoints_503_without_oauth_keys(patched_session_factory):
    from leadgen.adapters.web_api.app import create_app

    client = TestClient(create_app())
    resp = client.get(
        "/api/v1/oauth/gmail/callback?code=abcdefghij&state=1:nonce"
    )
    assert resp.status_code == 503


def test_gmail_callback_validates_state(
    patched_session_factory, gmail_env
):
    from leadgen.adapters.web_api.app import create_app

    client = TestClient(create_app())
    resp = client.get("/api/v1/oauth/gmail/callback?code=abcdefghij&state=garbage")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_gmail_callback_persists_tokens(
    patched_session_factory, gmail_env, monkeypatch
):
    from leadgen.adapters.web_api.app import create_app

    async with patched_session_factory() as session:
        u = User(id=42, email="u@example.com")
        session.add(u)
        await session.commit()

    async def _fake_exchange(code, **kw):
        assert code == "AUTHCODE_VALUE"
        return TokenSet(
            access_token="acc",
            refresh_token="ref",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scope="https://www.googleapis.com/auth/gmail.send",
        )

    async def _fake_email(token, **kw):
        return "u@example.com"

    monkeypatch.setattr(
        "leadgen.integrations.gmail.exchange_code_for_tokens", _fake_exchange
    )
    monkeypatch.setattr(
        "leadgen.integrations.gmail.fetch_account_email", _fake_email
    )

    client = TestClient(create_app())
    # follow_redirects=False so we can assert the 302 location
    resp = client.get(
        "/api/v1/oauth/gmail/callback?code=AUTHCODE_VALUE&state=42:nonce",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/app/settings" in resp.headers["location"]

    async with patched_session_factory() as session:
        cred = (
            (
                await session.execute(
                    OAuthCredential.__table__.select().where(
                        OAuthCredential.user_id == 42
                    )
                )
            )
            .mappings()
            .first()
        )
        assert cred is not None
        assert cred["account_email"] == "u@example.com"
        assert decrypt(cred["access_token_ciphertext"]) == "acc"


@pytest.mark.asyncio
async def test_send_email_endpoint_uses_lead_email_and_logs_activity(
    patched_session_factory, gmail_env, monkeypatch
):
    """End-to-end with the auth dependency stubbed out."""
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
        website_meta={"emails": ["u@example.com"]},
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

    async def _fake_send(*, access_token, raw_message, **kw):
        assert access_token == "acc"
        return {"id": "msg_001", "threadId": "thr_001"}

    monkeypatch.setattr(
        "leadgen.integrations.gmail.send_message", _fake_send
    )

    async def _fake_user_dep() -> User:
        return user

    app = create_app()
    app.dependency_overrides[auth_mod.get_current_user] = _fake_user_dep

    client = TestClient(app)
    resp = client.post(
        f"/api/v1/leads/{lead_id}/send-email",
        json={"subject": "Hi", "body": "Hello there"},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["message_id"] == "msg_001"
    assert payload["thread_id"] == "thr_001"


@pytest.mark.asyncio
async def test_send_email_returns_400_when_lead_has_no_email(
    patched_session_factory, gmail_env, monkeypatch
):
    from leadgen.adapters.web_api import auth as auth_mod
    from leadgen.adapters.web_api.app import create_app

    user = User(id=100, email="u@example.com")
    query = SearchQuery(
        id=uuid.uuid4(),
        user_id=100,
        niche="dentist",
        region="NYC",
        scope="city",
    )
    lead = Lead(
        id=uuid.uuid4(),
        query_id=query.id,
        name="No Email Co",
        source="google",
        source_id="ChIJxx",
        website_meta={},
    )
    async with patched_session_factory() as session:
        session.add_all([user, query, lead])
        await session.commit()
        await save_tokens(
            session,
            user_id=100,
            provider="gmail",
            tokens=TokenSet(
                access_token="acc",
                refresh_token="ref",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
                scope=None,
            ),
            account_email="u@example.com",
        )

    async def _fake_user_dep() -> User:
        return user

    app = create_app()
    app.dependency_overrides[auth_mod.get_current_user] = _fake_user_dep

    client = TestClient(app)
    resp = client.post(
        f"/api/v1/leads/{lead.id}/send-email",
        json={"subject": "x", "body": "y"},
    )
    assert resp.status_code == 400
