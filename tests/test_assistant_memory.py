"""Smoke tests for the Henry memory store."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.core.services.assistant_memory import (
    SUMMARY_EVERY_N_USER_MSGS,
    load_memories,
    record_memory,
    should_summarise,
)
from leadgen.db.models import AssistantMemory, Team, User


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: User.__table__.create(c))
        await conn.run_sync(lambda c: Team.__table__.create(c))
        await conn.run_sync(lambda c: AssistantMemory.__table__.create(c))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_record_and_load_personal_memories(session: AsyncSession) -> None:
    user = User(id=42, queries_limit=5)
    session.add(user)
    await session.commit()

    await record_memory(
        session, user_id=42, team_id=None, kind="summary", content="recent chat"
    )
    await record_memory(
        session, user_id=42, team_id=None, kind="fact", content="продаёт SEO"
    )
    await session.commit()

    rows = await load_memories(session, user_id=42)
    assert len(rows) == 2
    contents = {r["content"] for r in rows}
    assert contents == {"recent chat", "продаёт SEO"}


@pytest.mark.asyncio
async def test_team_scoped_memories_visible_to_team_member(
    session: AsyncSession,
) -> None:
    user = User(id=42, queries_limit=5)
    team = Team(id=uuid.uuid4(), name="Acme", plan="free")
    session.add(user)
    session.add(team)
    await session.commit()

    await record_memory(
        session,
        user_id=42,
        team_id=None,
        kind="fact",
        content="личный факт юзера",
    )
    await record_memory(
        session,
        user_id=42,
        team_id=team.id,
        kind="fact",
        content="командный факт",
    )
    await session.commit()

    # Personal call only sees the personal memory.
    personal_only = await load_memories(session, user_id=42, team_id=None)
    assert {r["content"] for r in personal_only} == {"личный факт юзера"}

    # Team call sees both — we union team-scoped and personal so Henry
    # has full context inside the team workspace.
    in_team = await load_memories(session, user_id=42, team_id=team.id)
    assert {r["content"] for r in in_team} == {
        "личный факт юзера",
        "командный факт",
    }


def test_should_summarise_triggers_every_n_user_msgs() -> None:
    history: list[dict[str, str]] = []
    for i in range(SUMMARY_EVERY_N_USER_MSGS):
        history.append({"role": "user", "content": f"msg {i}"})
        history.append({"role": "assistant", "content": "reply"})
    assert should_summarise(history) is True

    history.append({"role": "user", "content": "one more"})
    assert should_summarise(history) is False


def test_should_summarise_false_on_empty() -> None:
    assert should_summarise([]) is False
    assert should_summarise([{"role": "assistant", "content": "hi"}]) is False
