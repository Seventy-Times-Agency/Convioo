"""Tests for ProfileService — partial updates + reset + is_onboarded gate."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.core.services import ProfileService, ProfileUpdate
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
async def test_apply_patches_only_supplied_fields(session: AsyncSession) -> None:
    session.add(
        User(id=1, queries_limit=5, profession="old", home_region="Berlin")
    )
    await session.commit()

    await ProfileService(session).apply(
        1, ProfileUpdate(profession="new")
    )
    await session.commit()

    fresh = await session.get(User, 1)
    assert fresh is not None
    assert fresh.profession == "new"
    assert fresh.home_region == "Berlin"  # untouched


@pytest.mark.asyncio
async def test_apply_sets_onboarded_at_when_bar_met(session: AsyncSession) -> None:
    session.add(User(id=1, queries_limit=5))
    await session.commit()

    await ProfileService(session).apply(
        1,
        ProfileUpdate(
            profession="agency",
            niches=["roofing", "dental"],
            home_region="NYC",
        ),
    )
    fresh = await session.get(User, 1)
    assert fresh is not None
    assert fresh.onboarded_at is not None


@pytest.mark.asyncio
async def test_apply_does_not_reset_onboarded_at(session: AsyncSession) -> None:
    original = datetime(2026, 1, 1, tzinfo=timezone.utc)
    session.add(
        User(
            id=1,
            queries_limit=5,
            profession="agency",
            niches=["roofing"],
            onboarded_at=original,
        )
    )
    await session.commit()

    await ProfileService(session).apply(1, ProfileUpdate(display_name="Alex"))
    fresh = await session.get(User, 1)
    # Once a user has onboarded, a partial edit shouldn't stamp a new
    # onboarded_at — we preserve the first onboarding time. Compare as
    # naive datetimes because SQLite strips tzinfo on round-trip.
    assert fresh.onboarded_at is not None
    assert fresh.onboarded_at.replace(tzinfo=None) == original.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_reset_wipes_profile_but_keeps_user(session: AsyncSession) -> None:
    session.add(
        User(
            id=1,
            queries_limit=5,
            queries_used=3,
            username="alex",
            display_name="Alex",
            profession="agency",
            niches=["roofing"],
            onboarded_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    )
    await session.commit()

    await ProfileService(session).reset(1)
    fresh = await session.get(User, 1)
    assert fresh is not None
    # User identity + quota history survive; profile data is cleared.
    assert fresh.username == "alex"
    assert fresh.queries_used == 3
    assert fresh.display_name is None
    assert fresh.profession is None
    assert fresh.niches is None
    assert fresh.onboarded_at is None


@pytest.mark.asyncio
async def test_is_onboarded_requires_profession_and_niches() -> None:
    # Unit-level check on the predicate — no DB needed.
    u = User(id=1, queries_limit=5)
    assert not ProfileService.is_onboarded(u)
    u.profession = "agency"
    assert not ProfileService.is_onboarded(u)  # missing niches
    u.niches = ["roofing"]
    assert not ProfileService.is_onboarded(u)  # missing onboarded_at
    u.onboarded_at = datetime.now(timezone.utc)
    assert ProfileService.is_onboarded(u)
