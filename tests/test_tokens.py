"""Учёт токенов: тарификация и двухшаговое списание.

Главное, что здесь проверяется, — что с команды списывают за
фактически доставленных лидов, а не за заказанных. Поиск почти всегда
приносит меньше заказанного, и ошибка в эту сторону означала бы
систематический перебор денег у всех клиентов сразу.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from leadgen.core.services import tokens
from leadgen.db.models import (
    KIND_HOLD,
    KIND_REFUND,
    KIND_SPEND,
    Base,
    Team,
    TokenLedger,
)


@pytest_asyncio.fixture
async def session_factory():
    """Изолированная in-memory база на тест — учёт токенов не должен
    зависеть от порядка выполнения."""
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


def test_quote_base_lead_is_one_token():
    q = tokens.quote(50)
    assert q.total == 50
    assert q.per_lead == 1
    assert q.breakdown == {"leads": 50}


def test_quote_decision_makers_add_a_surcharge():
    q = tokens.quote(50, find_decision_makers=True)
    assert q.per_lead == 2
    assert q.total == 100
    assert q.breakdown["decision_makers"] == 50


def test_quote_zero_and_negative_are_free():
    assert tokens.quote(0).total == 0
    assert tokens.quote(-10).total == 0


@pytest.mark.asyncio
async def test_settle_charges_actual_not_ordered(session_factory):
    """Заказали 20, доставили 18 — списать должно 18."""
    async with session_factory() as session:
        team = Team(id=uuid.uuid4(), name="T", plan="free")
        session.add(team)
        await session.flush()

        await tokens.grant(session, team.id, 100, reason="старт")
        search_id = uuid.uuid4()
        await tokens.hold(
            session, team.id, search_id, tokens.quote(20).total
        )
        assert await tokens.balance(session, team.id) == 80

        await tokens.settle(
            session, team.id, search_id, actual_leads=18
        )
        await session.commit()

        assert await tokens.balance(session, team.id) == 82

        rows = (
            (
                await session.execute(
                    select(TokenLedger)
                    .where(TokenLedger.team_id == team.id)
                    .order_by(TokenLedger.created_at)
                )
            )
            .scalars()
            .all()
        )
        kinds = [r.kind for r in rows]
        assert KIND_HOLD in kinds
        assert KIND_REFUND in kinds
        assert KIND_SPEND in kinds
        spend = next(r for r in rows if r.kind == KIND_SPEND)
        assert spend.amount == -18


@pytest.mark.asyncio
async def test_failed_search_returns_the_whole_hold(session_factory):
    async with session_factory() as session:
        team = Team(id=uuid.uuid4(), name="T2", plan="free")
        session.add(team)
        await session.flush()

        await tokens.grant(session, team.id, 50)
        search_id = uuid.uuid4()
        await tokens.hold(session, team.id, search_id, 30)
        await tokens.release(session, team.id, search_id)
        await session.commit()

        assert await tokens.balance(session, team.id) == 50


@pytest.mark.asyncio
async def test_balance_always_equals_the_ledger(session_factory):
    """Кэш на команде — не отдельная правда, а сумма журнала."""
    async with session_factory() as session:
        team = Team(id=uuid.uuid4(), name="T3", plan="free")
        session.add(team)
        await session.flush()

        await tokens.grant(session, team.id, 100)
        await tokens.topup(session, team.id, 40)
        sid = uuid.uuid4()
        await tokens.hold(session, team.id, sid, 25)
        await tokens.settle(session, team.id, sid, actual_leads=10)
        await tokens.adjust(session, team.id, -5, reason="правка")
        await session.commit()

        rows = (
            (
                await session.execute(
                    select(TokenLedger).where(TokenLedger.team_id == team.id)
                )
            )
            .scalars()
            .all()
        )
        assert sum(r.amount for r in rows) == await tokens.balance(
            session, team.id
        )


@pytest.mark.asyncio
async def test_settle_never_charges_more_than_held(session_factory):
    """Даже если фактических лидов больше заказанных, списываем не
    больше занятого: в минус за счёт округлений уходить нельзя."""
    async with session_factory() as session:
        team = Team(id=uuid.uuid4(), name="T4", plan="free")
        session.add(team)
        await session.flush()

        await tokens.grant(session, team.id, 100)
        sid = uuid.uuid4()
        await tokens.hold(session, team.id, sid, 10)
        await tokens.settle(session, team.id, sid, actual_leads=999)
        await session.commit()

        assert await tokens.balance(session, team.id) == 90
