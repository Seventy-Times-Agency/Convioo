"""End-to-end test for forgot-password / reset-password.

Stands up an in-memory SQLite engine, monkey-patches the global
session factory so the FastAPI handlers transparently use it, then
walks through register → forgot-password (which logs the
verification token instead of dispatching email) → reset-password →
login with the new password. Lockout is also exercised.
"""

from __future__ import annotations

import re

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.db import session as db_session_mod
from leadgen.db.models import Base, EmailVerificationToken, User
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
    """Redirect ``leadgen.db.session.session_factory`` at the SQLite engine."""
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db_session_mod, "_engine", db_engine)
    monkeypatch.setattr(db_session_mod, "_session_factory", maker)
    return maker


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Wipe in-memory rate-limit state so each test starts fresh."""
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
    from leadgen.adapters.web_api import create_app

    app = create_app()
    return TestClient(app)


def _register(client: TestClient, email: str = "user1@example.test") -> dict:
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Alex",
            "last_name": "Test",
            "email": email,
            "password": "correcthorse123",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_register_then_forgot_then_reset_then_login(
    client: TestClient, patched_session_factory
) -> None:
    user_payload = _register(client)
    assert user_payload["user_id"]
    user_id = user_payload["user_id"]

    # Forgot-password is anti-oracle: always 200 with sent=True.
    r = client.post(
        "/api/v1/auth/forgot-password", json={"email": "user1@example.test"}
    )
    assert r.status_code == 200
    assert r.json() == {"sent": True}

    # Pull the freshly issued reset token directly out of the DB —
    # the email-sender's log fallback would print it but capturing
    # logs in pytest is brittle.
    async with patched_session_factory() as session:
        token_row = (
            await session.execute(
                select(EmailVerificationToken)
                .where(EmailVerificationToken.user_id == user_id)
                .where(EmailVerificationToken.kind == "password_reset")
                .where(EmailVerificationToken.used_at.is_(None))
            )
        ).scalar_one()
        token_value = token_row.token

    # Reset and verify the new password is now active.
    r = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token_value, "new_password": "newhorse456789"},
    )
    assert r.status_code == 200, r.text

    # Old password no longer works.
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "user1@example.test", "password": "correcthorse123"},
    )
    assert r.status_code == 401

    # New password does.
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "user1@example.test", "password": "newhorse456789"},
    )
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_reset_token_is_single_use(
    client: TestClient, patched_session_factory
) -> None:
    user_id = _register(client)["user_id"]
    client.post(
        "/api/v1/auth/forgot-password", json={"email": "user1@example.test"}
    )
    async with patched_session_factory() as session:
        token_row = (
            await session.execute(
                select(EmailVerificationToken)
                .where(EmailVerificationToken.user_id == user_id)
                .where(EmailVerificationToken.kind == "password_reset")
                .where(EmailVerificationToken.used_at.is_(None))
            )
        ).scalar_one()
        token_value = token_row.token

    r1 = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token_value, "new_password": "abcdefgh1234"},
    )
    assert r1.status_code == 200
    r2 = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token_value, "new_password": "anotherone98765"},
    )
    assert r2.status_code == 410  # already used


@pytest.mark.asyncio
async def test_forgot_password_unknown_email_returns_sent(
    client: TestClient,
) -> None:
    # Anti-oracle: response is identical for known / unknown emails.
    r = client.post(
        "/api/v1/auth/forgot-password", json={"email": "user1@example.test"}
    )
    assert r.status_code == 200
    assert r.json() == {"sent": True}


@pytest.mark.asyncio
async def test_login_locks_after_threshold_bad_attempts(
    client: TestClient, patched_session_factory, monkeypatch
) -> None:
    _register(client, email="user1@example.test")
    # The IP-level rate limiter would shut us out at 5 attempts before
    # the account lockout (10 attempts) ever fires. Loosen it for this
    # test so we can exercise the actual lockout state machine.
    monkeypatch.setattr(rate_limit_mod.login_limiter, "max_actions", 50)
    # Eleven bad attempts: the tenth should trigger lockout, the
    # eleventh should still 401 even though the password matched
    # nothing — the locked_until check fires before the verify.
    for _ in range(11):
        r = client.post(
            "/api/v1/auth/login",
            json={"email": "user1@example.test", "password": "wrongwrong1"},
        )
        assert r.status_code == 401

    # Even with the correct password, login is refused while locked.
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "user1@example.test", "password": "correcthorse123"},
    )
    assert r.status_code == 401

    # Sanity-check the DB stamp.
    async with patched_session_factory() as session:
        user = (
            await session.execute(
                select(User).where(User.email == "user1@example.test")
            )
        ).scalar_one()
        assert user.failed_login_attempts >= 10
        assert user.locked_until is not None


@pytest.mark.asyncio
async def test_session_cookie_is_set_on_register(
    client: TestClient,
) -> None:
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Sam",
            "last_name": "Cookie",
            "email": "user1@example.test",
            "password": "correcthorse456",
        },
    )
    assert r.status_code == 200
    set_cookie = r.headers.get("set-cookie", "")
    assert "convioo_session=" in set_cookie
    # Mandatory security attributes.
    assert re.search(r"httponly", set_cookie, re.I)
    assert re.search(r"samesite=lax", set_cookie, re.I)
