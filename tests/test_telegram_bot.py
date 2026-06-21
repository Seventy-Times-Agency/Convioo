"""Tests for the Telegram v2 bot adapter.

Covers:
  - generate_link_token / token store / expiry
  - POST /api/v1/telegram/webhook (503 when unconfigured, 200 otherwise)
  - POST /api/v1/telegram/link-token (auth-gated; returns token + ttl)
  - process_update dispatch: /start, /help, /search, unknown commands
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from leadgen.db import session as db_session_mod
from leadgen.db.models import Base
from leadgen.db.models.telegram import TelegramConnection
from leadgen.utils import rate_limit as rate_limit_mod

# ── Fixtures ──────────────────────────────────────────────────────────────


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


@pytest.fixture(autouse=True)
def _clear_token_store():
    from leadgen.adapters.telegram_v2.bot import _PENDING_TOKENS

    _PENDING_TOKENS.clear()
    yield
    _PENDING_TOKENS.clear()


@pytest.fixture
def client(patched_session_factory):
    from leadgen.adapters.web_api import create_app

    return TestClient(create_app())


def _register(client: TestClient, email: str = "tg-user@example.test") -> int:
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Tg",
            "last_name": "User",
            "email": email,
            "password": "correcthorse123",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


# ── Token generation ───────────────────────────────────────────────────────


def test_generate_link_token_returns_8_char_hex():
    from leadgen.adapters.telegram_v2.bot import generate_link_token

    token = generate_link_token(42)
    assert len(token) == 8
    assert token == token.upper()
    int(token, 16)  # must be valid hex


def test_generate_link_token_stored_in_pending_dict():
    from leadgen.adapters.telegram_v2.bot import _PENDING_TOKENS, generate_link_token

    token = generate_link_token(99)
    assert token in _PENDING_TOKENS
    user_id, _ = _PENDING_TOKENS[token]
    assert user_id == 99


def test_generate_link_token_purges_expired_entries():
    from leadgen.adapters.telegram_v2.bot import _PENDING_TOKENS, generate_link_token

    # Plant an already-expired entry
    _PENDING_TOKENS["OLDTOKEN"] = (
        1,
        datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    generate_link_token(2)  # triggers _purge_expired
    assert "OLDTOKEN" not in _PENDING_TOKENS


# ── Webhook endpoint ───────────────────────────────────────────────────────


def test_webhook_503_when_bot_not_configured(client: TestClient):
    r = client.post(
        "/api/v1/telegram/webhook",
        json={"update_id": 1, "message": {"chat": {"id": 123}, "text": "/help"}},
    )
    assert r.status_code == 503
    assert "not configured" in r.json()["detail"].lower()


def test_webhook_200_when_configured(client: TestClient, monkeypatch):
    from leadgen.config import get_settings

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot123:TOKEN")
    get_settings.cache_clear()

    spawned: list[Any] = []

    def fake_spawn(coro, *, name=None):
        spawned.append(name)
        coro.close()  # prevent "coroutine was never awaited" warning
        import asyncio

        return asyncio.get_event_loop().create_future()

    monkeypatch.setattr("leadgen.adapters.web_api.routes.telegram.spawn", fake_spawn)

    r = client.post(
        "/api/v1/telegram/webhook",
        json={"update_id": 1, "message": {"chat": {"id": 123}, "text": "/help"}},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert spawned  # process_update was spawned

    get_settings.cache_clear()


# ── Link token endpoint ────────────────────────────────────────────────────


def test_link_token_requires_auth(client: TestClient):
    # No cookie / no session → should fail
    r = client.post(
        "/api/v1/telegram/link-token",
        cookies={},  # clear any session cookie
    )
    assert r.status_code in (401, 403)


def test_link_token_returns_token_and_ttl(client: TestClient):
    _register(client)
    r = client.post("/api/v1/telegram/link-token")
    assert r.status_code == 200
    body = r.json()
    assert "token" in body
    assert body["expires_in_seconds"] == 900
    assert len(body["token"]) == 8


# ── process_update dispatch ───────────────────────────────────────────────


def _update(text: str, chat_id: int = 100) -> dict[str, Any]:
    return {
        "update_id": 1,
        "message": {"chat": {"id": chat_id}, "text": text},
    }


@pytest.mark.asyncio
async def test_process_update_start_without_token_sends_welcome(monkeypatch):
    sent: list[tuple[int, str]] = []

    async def fake_send(chat_id, text, **kwargs):
        sent.append((chat_id, text))

    import leadgen.adapters.telegram_v2.api as tg_api

    monkeypatch.setattr(tg_api, "send_message", fake_send)

    from leadgen.adapters.telegram_v2.bot import process_update

    await process_update(_update("/start"))

    assert sent
    assert "welcome" in sent[0][1].lower() or "convioo" in sent[0][1].lower()


@pytest.mark.asyncio
async def test_process_update_start_invalid_token(monkeypatch):
    sent: list[tuple[int, str]] = []

    async def fake_send(chat_id, text, **kwargs):
        sent.append((chat_id, text))

    import leadgen.adapters.telegram_v2.api as tg_api

    monkeypatch.setattr(tg_api, "send_message", fake_send)

    from leadgen.adapters.telegram_v2.bot import process_update

    await process_update(_update("/start BADTOKEN"))

    assert sent
    assert "invalid" in sent[0][1].lower() or "expired" in sent[0][1].lower()


@pytest.mark.asyncio
async def test_process_update_start_valid_token_links_account(
    monkeypatch, patched_session_factory
):
    """A valid /start <token> creates a TelegramConnection row."""
    sent: list[tuple[int, str]] = []

    async def fake_send(chat_id, text, **kwargs):
        sent.append((chat_id, text))

    import leadgen.adapters.telegram_v2.api as tg_api

    monkeypatch.setattr(tg_api, "send_message", fake_send)

    from leadgen.adapters.telegram_v2.bot import _PENDING_TOKENS, process_update

    user_id = 7
    _PENDING_TOKENS["AABBCCDD"] = (
        user_id,
        datetime.now(timezone.utc) + timedelta(minutes=10),
    )

    await process_update(_update("/start AABBCCDD", chat_id=555))

    assert sent
    assert "linked" in sent[0][1].lower()

    from sqlalchemy import select

    async with patched_session_factory() as session:
        conn = (
            await session.execute(
                select(TelegramConnection).where(TelegramConnection.chat_id == 555)
            )
        ).scalar_one_or_none()
    assert conn is not None
    assert conn.user_id == user_id


@pytest.mark.asyncio
async def test_process_update_help_sends_help_text(monkeypatch):
    sent: list[tuple[int, str]] = []

    async def fake_send(chat_id, text, **kwargs):
        sent.append((chat_id, text))

    import leadgen.adapters.telegram_v2.api as tg_api

    monkeypatch.setattr(tg_api, "send_message", fake_send)

    from leadgen.adapters.telegram_v2.bot import process_update

    await process_update(_update("/help"))

    assert sent
    assert "/search" in sent[0][1]


@pytest.mark.asyncio
async def test_process_update_search_without_linked_account(
    monkeypatch, patched_session_factory
):
    """Without a TelegramConnection, bot asks the user to link first."""
    sent: list[tuple[int, str]] = []

    async def fake_send(chat_id, text, **kwargs):
        sent.append((chat_id, text))

    import leadgen.adapters.telegram_v2.api as tg_api

    monkeypatch.setattr(tg_api, "send_message", fake_send)

    from leadgen.adapters.telegram_v2.bot import process_update

    await process_update(_update("/search plumbers in London", chat_id=777))

    assert sent
    msg = sent[0][1].lower()
    assert "link" in msg or "/start" in msg


@pytest.mark.asyncio
async def test_process_update_search_bad_format(
    monkeypatch, patched_session_factory
):
    """'/search without the "in" separator' → usage hint."""
    sent: list[tuple[int, str]] = []

    async def fake_send(chat_id, text, **kwargs):
        sent.append((chat_id, text))

    import leadgen.adapters.telegram_v2.api as tg_api

    monkeypatch.setattr(tg_api, "send_message", fake_send)

    # Seed a TelegramConnection so auth passes
    async with patched_session_factory() as session:
        session.add(TelegramConnection(user_id=1, chat_id=888))
        await session.commit()

    from leadgen.adapters.telegram_v2.bot import process_update

    await process_update(_update("/search plumbers", chat_id=888))

    assert sent
    assert "usage" in sent[0][1].lower() or "/search" in sent[0][1].lower()


@pytest.mark.asyncio
async def test_process_update_search_valid_spawns_task(
    monkeypatch, patched_session_factory
):
    """/search niche in region with linked account spawns the search task."""
    sent: list[tuple[int, str]] = []

    async def fake_send(chat_id, text, **kwargs):
        sent.append((chat_id, text))

    import leadgen.adapters.telegram_v2.api as tg_api

    monkeypatch.setattr(tg_api, "send_message", fake_send)

    spawned: list[str | None] = []

    def fake_spawn(coro, *, name=None):
        spawned.append(name)
        coro.close()
        import asyncio

        return asyncio.get_event_loop().create_future()

    import leadgen.adapters.telegram_v2.bot as bot_mod

    monkeypatch.setattr(bot_mod, "spawn", fake_spawn)

    # Seed a TelegramConnection (user_id=5, chat_id=999)
    async with patched_session_factory() as session:
        session.add(TelegramConnection(user_id=5, chat_id=999))
        await session.commit()

    from leadgen.adapters.telegram_v2.bot import process_update

    await process_update(_update("/search roofers in Berlin", chat_id=999))

    # "Starting search..." message sent
    assert sent
    assert "roofers" in sent[0][1].lower() or "berlin" in sent[0][1].lower()
    # Background task was spawned
    assert spawned


@pytest.mark.asyncio
async def test_process_update_unknown_command_with_linked_account(
    monkeypatch, patched_session_factory
):
    sent: list[tuple[int, str]] = []

    async def fake_send(chat_id, text, **kwargs):
        sent.append((chat_id, text))

    import leadgen.adapters.telegram_v2.api as tg_api

    monkeypatch.setattr(tg_api, "send_message", fake_send)

    async with patched_session_factory() as session:
        session.add(TelegramConnection(user_id=3, chat_id=111))
        await session.commit()

    from leadgen.adapters.telegram_v2.bot import process_update

    await process_update(_update("hello there", chat_id=111))

    assert sent
    assert "/search" in sent[0][1] or "/help" in sent[0][1]
