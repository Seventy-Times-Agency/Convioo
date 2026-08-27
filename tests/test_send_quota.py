"""Warmup ramp + daily cap reservation + read-only status snapshot."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from leadgen.core.services import send_quota
from leadgen.db.models import Base, User


@pytest_asyncio.fixture
async def session():
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
    async with maker() as s:
        yield s
    await engine.dispose()


async def _make_user(session, user_id: int = 1) -> User:
    user = User(
        id=user_id,
        email=f"u{user_id}@example.test",
        created_at=datetime.now(timezone.utc),
    )
    session.add(user)
    await session.commit()
    return user


def test_warmup_cap_ramp():
    assert send_quota.warmup_cap(0) == 20
    assert send_quota.warmup_cap(1) == 30
    assert send_quota.warmup_cap(5) == 70
    # Capped at MAX.
    assert send_quota.warmup_cap(1000) == 200
    # Defensive: negative days behave like day 0.
    assert send_quota.warmup_cap(-5) == 20


@pytest.mark.asyncio
async def test_reserve_increments_and_blocks_at_cap(session):
    await _make_user(session)
    # No mailbox connected → anchor on user.created_at (today) → cap 20.
    first = await send_quota.check_and_reserve_send(session, 1)
    assert first.allowed is True
    assert first.cap == 20
    assert first.sent == 1

    # Drain to the cap.
    for _ in range(19):
        r = await send_quota.check_and_reserve_send(session, 1)
        assert r.allowed is True
    assert r.sent == 20

    # The 21st send is blocked.
    blocked = await send_quota.check_and_reserve_send(session, 1)
    assert blocked.allowed is False
    assert blocked.cap == 20
    assert blocked.sent == 20


@pytest.mark.asyncio
async def test_get_send_status_shape(session):
    await _make_user(session)
    await send_quota.check_and_reserve_send(session, 1)
    status = await send_quota.get_send_status(session, 1)
    assert set(status.keys()) == {
        "connected",
        "provider",
        "warmup_day",
        "daily_cap",
        "sent_today",
        "remaining",
    }
    assert status["connected"] is False
    assert status["provider"] is None
    assert status["daily_cap"] == 20
    assert status["sent_today"] == 1
    assert status["remaining"] == 19
