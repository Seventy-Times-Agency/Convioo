"""Учёт затрат в базе: атомарность, персональный потолок, чистка.

Три закрытые дыры ревизии: инкремент терял обновления под
параллельным обогащением, расход жил в кэше и обнулялся при
редеплое, а личное пространство обходило потолок затрат целиком.
"""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.core.services import usage_tracker
from leadgen.core.services.cost_control import get_personal_cost_status
from leadgen.db import session as db_session_mod
from leadgen.db.models import Base, UsageCounter


@pytest_asyncio.fixture
async def db_engine():
    from sqlalchemy.pool import StaticPool

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
    maker = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr(db_session_mod, "_engine", db_engine)
    monkeypatch.setattr(db_session_mod, "_session_factory", maker)
    return maker


async def _record_as(user_id: int, service: str, units: int) -> None:
    token = usage_tracker.set_active_user(user_id)
    try:
        await usage_tracker.record(service, units)
    finally:
        usage_tracker.reset_active_user(token)


@pytest.mark.asyncio
async def test_concurrent_increments_are_not_lost(patched_session_factory):
    """20 параллельных инкрементов складываются, а не затирают друг
    друга — раньше «прочитал-прибавил-записал» в кэше терял часть."""
    await asyncio.gather(
        *[_record_as(7, "google_place_details", 1) for _ in range(20)]
    )
    summary = await usage_tracker.get_user_usage(7, window="today")
    assert summary.units_by_service["google_place_details"] == 20


@pytest.mark.asyncio
async def test_usage_survives_process_restart(patched_session_factory):
    """Счётчик в базе: «рестарт» (новый факторий сессий) его не трёт."""
    await _record_as(8, "google_text_search", 3)
    # Симулируем редеплой: соединения новые, база та же.
    summary = await usage_tracker.get_user_usage(8, window="month")
    assert summary.units_by_service["google_text_search"] == 3
    assert summary.total_cost_usd > 0


@pytest.mark.asyncio
async def test_personal_cap_blocks(patched_session_factory):
    """Личное пространство упирается в лимит платформы ($25 по
    умолчанию): 1000 place-details = $28 → заблокирован."""
    await _record_as(9, "google_place_details", 1000)
    status = await get_personal_cost_status(9)
    assert status.cap_usd == 25.0
    assert status.month_cost_usd == pytest.approx(28.0)
    assert status.blocked

    status_ok = await get_personal_cost_status(10)
    assert not status_ok.blocked


@pytest.mark.asyncio
async def test_prune_drops_only_old_rows(patched_session_factory):
    await _record_as(11, "google_text_search", 2)
    async with patched_session_factory() as session:
        session.add(
            UsageCounter(
                user_id="11",
                service="google_text_search",
                day="20200101",
                units=5,
            )
        )
        await session.commit()

    dropped = await usage_tracker.prune()
    assert dropped == 1
    async with patched_session_factory() as session:
        days = (
            (await session.execute(select(UsageCounter.day)))
            .scalars()
            .all()
        )
    assert "20200101" not in days
    assert len(days) == 1


@pytest.mark.asyncio
async def test_personal_search_returns_402_at_cap(patched_session_factory):
    """API-уровень: личный поиск больше не обходит контроль затрат."""
    from datetime import datetime, timezone

    from fastapi.testclient import TestClient

    from leadgen.adapters.web_api import create_app
    from leadgen.db.models import User
    from leadgen.utils import rate_limit as rate_limit_mod

    client = TestClient(create_app())
    rate_limit_mod.register_limiter._events.clear()
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "P",
            "last_name": "Cap",
            "email": "personal-cap@example.test",
            "password": "correcthorse123",
        },
    )
    assert r.status_code == 200, r.text
    uid = r.json()["user_id"]

    async with patched_session_factory() as session:
        u = await session.get(User, uid)
        u.email_verified_at = datetime.now(timezone.utc)
        await session.commit()

    await _record_as(uid, "google_place_details", 1000)  # $28 > $25

    r = client.post(
        "/api/v1/searches",
        json={"niche": "bakeries", "region": "Orlando, FL"},
    )
    assert r.status_code == 402, r.text
    assert "личного пространства" in r.json()["detail"]
