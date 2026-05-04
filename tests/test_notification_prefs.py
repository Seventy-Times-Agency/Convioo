"""Tests for the notification-preferences service.

Pins the default-off behaviour, the partial-update PATCH semantics,
and the worker lookup helpers (``list_users_with_digest_enabled`` /
``list_users_with_reply_tracking``) — those are what the cron tasks
read on every tick, so a regression there would make digests + reply
tracking silently no-op for opted-in users.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.core.services.notification_prefs import (
    get_prefs,
    list_users_with_digest_enabled,
    list_users_with_reply_tracking,
    update_prefs,
)
from leadgen.db.models import User


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: User.__table__.create(sync_conn))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_defaults_are_both_off(session: AsyncSession) -> None:
    session.add(User(id=1))
    await session.commit()

    prefs = await get_prefs(session, 1)
    assert prefs.daily_digest_enabled is False
    assert prefs.email_reply_tracking_enabled is False
    assert prefs.email_reply_last_checked_at is None


@pytest.mark.asyncio
async def test_update_only_touches_provided_fields(session: AsyncSession) -> None:
    session.add(User(id=1))
    await session.commit()

    after_digest = await update_prefs(
        session, 1, daily_digest_enabled=True
    )
    assert after_digest.daily_digest_enabled is True
    # The other toggle wasn't passed — it must stay off, not flip.
    assert after_digest.email_reply_tracking_enabled is False

    after_reply = await update_prefs(
        session, 1, email_reply_tracking_enabled=True
    )
    assert after_reply.daily_digest_enabled is True  # preserved
    assert after_reply.email_reply_tracking_enabled is True


@pytest.mark.asyncio
async def test_worker_lookup_filters_to_opted_in(session: AsyncSession) -> None:
    session.add_all(
        [
            User(id=1, daily_digest_enabled=True),
            User(id=2, daily_digest_enabled=False),
            User(
                id=3,
                daily_digest_enabled=True,
                email_reply_tracking_enabled=True,
            ),
            User(id=4, email_reply_tracking_enabled=True),
        ]
    )
    await session.commit()

    digest_users = await list_users_with_digest_enabled(session)
    reply_users = await list_users_with_reply_tracking(session)

    assert {u.id for u in digest_users} == {1, 3}
    assert {u.id for u in reply_users} == {3, 4}


@pytest.mark.asyncio
async def test_get_prefs_raises_for_missing_user(session: AsyncSession) -> None:
    with pytest.raises(ValueError):
        await get_prefs(session, 999)
