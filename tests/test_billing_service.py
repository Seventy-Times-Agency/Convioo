"""Tests for the atomic quota service shared by bot + web."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.core.services import BillingService, QuotaCheck
from leadgen.db.models import User


@pytest_asyncio.fixture
async def session(monkeypatch: pytest.MonkeyPatch) -> AsyncSession:
    """Ephemeral SQLite-backed session for unit-scale service tests.

    We spin up an in-memory DB, create just the tables we need, hand
    back a session, tear down at the end. Cheap, fast, no Postgres
    dependency for unit tests.

    The fixture also forces ``BILLING_ENFORCED=true`` so the tests
    exercise the real quota machinery rather than the development
    short-circuit.
    """
    monkeypatch.setenv("BILLING_ENFORCED", "true")
    # Re-cache settings so the new value takes effect for this test.
    from leadgen.config import get_settings

    get_settings.cache_clear()

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: User.__table__.create(sync_conn))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_try_consume_allows_when_under_limit(session: AsyncSession) -> None:
    session.add(User(id=1, queries_used=0, queries_limit=3))
    await session.commit()

    result = await BillingService(session).try_consume(1)

    assert result.allowed
    assert result.queries_used == 1
    assert result.remaining == 2


@pytest.mark.asyncio
async def test_try_consume_rejects_at_limit(session: AsyncSession) -> None:
    session.add(User(id=1, queries_used=3, queries_limit=3))
    await session.commit()

    result = await BillingService(session).try_consume(1)

    assert not result.allowed
    assert result.queries_used == 3
    assert result.remaining == 0


@pytest.mark.asyncio
async def test_try_consume_is_sequential_safe(session: AsyncSession) -> None:
    session.add(User(id=1, queries_used=0, queries_limit=2))
    await session.commit()

    billing = BillingService(session)
    r1 = await billing.try_consume(1)
    r2 = await billing.try_consume(1)
    r3 = await billing.try_consume(1)

    assert r1.allowed and r1.queries_used == 1
    assert r2.allowed and r2.queries_used == 2
    # Third one must be rejected — the DB-level WHERE clause guards us.
    assert not r3.allowed


@pytest.mark.asyncio
async def test_refund_returns_one_credit(session: AsyncSession) -> None:
    session.add(User(id=1, queries_used=2, queries_limit=5))
    await session.commit()

    await BillingService(session).refund(1)
    snap = await BillingService(session).snapshot(1)

    assert snap.queries_used == 1


@pytest.mark.asyncio
async def test_refund_never_goes_below_zero(session: AsyncSession) -> None:
    session.add(User(id=1, queries_used=0, queries_limit=5))
    await session.commit()

    # Double refund on a zero-counter must stay at 0, not go negative.
    await BillingService(session).refund(1)
    await BillingService(session).refund(1)
    snap = await BillingService(session).snapshot(1)

    assert snap.queries_used == 0


@pytest.mark.asyncio
async def test_snapshot_reports_verdict(session: AsyncSession) -> None:
    session.add(User(id=1, queries_used=1, queries_limit=5))
    await session.commit()

    snap = await BillingService(session).snapshot(1)

    assert snap.allowed
    assert snap.remaining == 4
    assert isinstance(snap, QuotaCheck)


@pytest.mark.asyncio
async def test_try_consume_ignores_limit_when_billing_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With BILLING_ENFORCED=false the service never blocks — every
    search is allowed and the counter still increments for analytics."""
    monkeypatch.setenv("BILLING_ENFORCED", "false")
    from leadgen.config import get_settings

    get_settings.cache_clear()

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: User.__table__.create(sync_conn))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as s:
            # User already at the cap; enforcement off should still allow.
            s.add(User(id=1, queries_used=3, queries_limit=3))
            await s.commit()

            for _ in range(3):
                result = await BillingService(s).try_consume(1)
                assert result.allowed

            snap = await BillingService(s).snapshot(1)
            # Counter climbed well past the limit — exactly what we want
            # during the internal-only phase.
            assert snap.queries_used == 6
    finally:
        await engine.dispose()
        get_settings.cache_clear()
