"""User API keys: issuance, list, revoke + Bearer auth on protected endpoints."""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.db import session as db_session_mod
from leadgen.db.models import Base
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
        "search_user_limiter",
        "search_team_limiter",
        "search_ip_limiter",
        "assistant_user_limiter",
        "assistant_team_limiter",
    ):
        getattr(rate_limit_mod, name)._events.clear()
    yield


@pytest.fixture
def client(patched_session_factory):
    from leadgen.adapters.web_api import create_app

    return TestClient(create_app())


def _register(client: TestClient, email: str = "keys@example.test") -> int:
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Key",
            "last_name": "User",
            "email": email,
            "password": "correcthorse123",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


def test_issue_list_revoke_key(client: TestClient):
    _register(client)

    # No keys initially.
    r = client.get("/api/v1/auth/api-keys")
    assert r.status_code == 200
    assert r.json() == {"items": []}

    # Mint a fresh key.
    r = client.post(
        "/api/v1/auth/api-keys", json={"label": "My script"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token"].startswith("convioo_pk_")
    assert len(body["token"]) > 30
    key_id = body["id"]
    plaintext = body["token"]
    preview = body["token_preview"]
    assert preview.startswith("convioo_pk_")
    assert preview.endswith(plaintext[-4:])

    # Listing shows the key but never the plaintext.
    r = client.get("/api/v1/auth/api-keys")
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["token_preview"] == preview
    assert items[0]["revoked"] is False
    assert "token" not in items[0]

    # Revoke.
    r = client.delete(f"/api/v1/auth/api-keys/{key_id}")
    assert r.status_code == 200
    r = client.get("/api/v1/auth/api-keys")
    assert r.json()["items"][0]["revoked"] is True


def test_bearer_token_authenticates_protected_endpoint(
    client: TestClient,
):
    user_id = _register(client)

    # Mint key, then drop the cookie so we exercise pure Bearer auth.
    r = client.post(
        "/api/v1/auth/api-keys", json={"label": "Zapier"}
    )
    token = r.json()["token"]
    client.cookies.clear()

    # Bearer auth on /auth/me works.
    r = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["user_id"] == user_id

    # Without the header it's 401 again.
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_revoked_key_no_longer_authenticates(client: TestClient):
    _register(client)
    r = client.post("/api/v1/auth/api-keys", json={"label": "x"})
    token = r.json()["token"]
    key_id = r.json()["id"]

    # Revoke through the cookie session (still alive).
    r = client.delete(f"/api/v1/auth/api-keys/{key_id}")
    assert r.status_code == 200

    client.cookies.clear()
    r = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401


def test_invalid_bearer_returns_401(client: TestClient):
    _register(client)
    client.cookies.clear()
    r = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer convioo_pk_garbage"},
    )
    assert r.status_code == 401


def test_other_users_key_cant_be_revoked(client: TestClient):
    _register(client, email="alice@example.test")
    r = client.post("/api/v1/auth/api-keys", json={"label": "alice"})
    alice_key = r.json()["id"]

    # Switch user via another register.
    _register(client, email="bob@example.test")
    r = client.delete(f"/api/v1/auth/api-keys/{alice_key}")
    assert r.status_code == 404
