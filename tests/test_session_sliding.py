"""Session sliding-expiry behaviour for the cookie auth path.

The session window is rolling: ``load_session`` slides ``expires_at``
forward to ``now + window`` once more than ~1 day has elapsed since the
last slide, so a session dies after the LAST activity rather than after
login. Tests cover: a near-expiry session is pushed forward, an expired
(unused-past-window) session is rejected, and the throttle does not slide
a brand-new session on a request made seconds after creation.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.adapters.web_api.auth import (
    _utcnow,
    hash_token,
    load_session,
)
from leadgen.config import get_settings
from leadgen.db.models import Base, User, UserSession


@pytest_asyncio.fixture
async def db_session():
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with maker() as session:
        session.add(User(id=1, queries_limit=5))
        await session.commit()
        yield session
    await engine.dispose()


def _window() -> timedelta:
    return timedelta(days=max(1, get_settings().auth_session_days))


async def _make_session(db_session, *, token: str, expires_at):
    row = UserSession(
        user_id=1,
        token_hash=hash_token(token),
        device_fingerprint="fp",
        expires_at=expires_at,
    )
    db_session.add(row)
    await db_session.flush()
    return row


@pytest.mark.asyncio
async def test_near_expiry_session_is_slid_forward(db_session):
    # Session that expires in ~1 hour — well inside the slide zone.
    window = _window()
    now = _utcnow()
    await _make_session(
        db_session, token="tok-near", expires_at=now + timedelta(hours=1)
    )

    row, extended = await load_session(db_session, "tok-near")
    assert row is not None
    assert extended is True
    # Pushed forward to roughly now + full window.
    assert row.expires_at >= now + window - timedelta(seconds=5)


@pytest.mark.asyncio
async def test_session_past_window_is_rejected(db_session):
    now = _utcnow()
    await _make_session(
        db_session, token="tok-dead", expires_at=now - timedelta(minutes=1)
    )

    row, extended = await load_session(db_session, "tok-dead")
    assert row is None
    assert extended is False


@pytest.mark.asyncio
async def test_fresh_session_not_slid_by_throttle(db_session):
    # A session created seconds ago still has nearly the full window left,
    # so the ~1-day throttle must NOT slide it (no needless DB write).
    window = _window()
    now = _utcnow()
    expires = now + window  # brand-new
    await _make_session(db_session, token="tok-fresh", expires_at=expires)

    row, extended = await load_session(db_session, "tok-fresh")
    assert row is not None
    assert extended is False
    # expires_at untouched (SQLite drops tzinfo on round-trip; compare naive).
    assert row.expires_at.replace(tzinfo=None) == expires.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_slide_threshold_respects_short_window(db_session, monkeypatch):
    # With a 1-day window the throttle is the full window, so a session
    # whose remaining life is under (window - 1 day) == 0 only slides once
    # it has actually elapsed past creation. Sanity-check the boundary by
    # forcing a tiny session-day setting.
    monkeypatch.setattr(
        get_settings(), "auth_session_days", 2, raising=False
    )
    now = _utcnow()
    # 2-day window, throttle 1 day: a session with 12h left should slide.
    await _make_session(
        db_session, token="tok-short", expires_at=now + timedelta(hours=12)
    )
    row, extended = await load_session(db_session, "tok-short")
    assert extended is True
    assert row.expires_at >= now + timedelta(days=2) - timedelta(seconds=5)
