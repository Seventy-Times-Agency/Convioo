"""Живое состояние CRM для Henry: цифры и ролевая линза.

ИИ не должен видеть больше, чем видит человек на экране: селзу —
своё, тимлиду — команда и свободный пул, РОПу — всё.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.core.services import crm_snapshot
from leadgen.db.models import (
    Base,
    Lead,
    SearchQuery,
    Team,
    TeamMembership,
    TeamSquad,
)


@pytest_asyncio.fixture
async def session_factory():
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


@pytest.mark.asyncio
async def test_snapshot_counts_and_lens(session_factory):
    team_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        session.add(Team(id=team_id, name="K", token_balance=950))
        squad = TeamSquad(team_id=team_id, name="A", lead_user_id=2)
        session.add(squad)
        await session.flush()
        session.add_all(
            [
                TeamMembership(team_id=team_id, user_id=1, role="owner"),
                TeamMembership(
                    team_id=team_id, user_id=2, role="manager",
                    squad_id=squad.id,
                ),
                TeamMembership(
                    team_id=team_id, user_id=3, role="sales",
                    squad_id=squad.id,
                ),
                TeamMembership(team_id=team_id, user_id=4, role="sales"),
            ]
        )
        q = SearchQuery(
            id=uuid.uuid4(), user_id=1, team_id=team_id,
            niche="n", region="r", status="running", source="web",
        )
        session.add(q)
        await session.flush()
        session.add_all(
            [
                Lead(query_id=q.id, name="Горячий мой", source="g",
                     source_id="a", owner_user_id=3, score_ai=90,
                     next_touch_at=now - timedelta(hours=1)),
                Lead(query_id=q.id, name="Чужой", source="g",
                     source_id="b", owner_user_id=4, score_ai=80),
                Lead(query_id=q.id, name="Свободный", source="g",
                     source_id="c"),
            ]
        )
        await session.commit()

        # Владелец: вся компания.
        snap = await crm_snapshot.build(session, team_id, 1)
        assert snap["scope"] == "company"
        assert snap["total"] == 3
        assert snap["free"] == 1
        assert snap["hot"] == 2
        assert snap["overdue_callbacks"] == 1
        assert snap["running_searches"] == ["n · r"]
        assert snap["token_balance"] == 950

        # Тимлид: своя команда + свободный, чужого не видно.
        snap = await crm_snapshot.build(session, team_id, 2)
        assert snap["scope"] == "squad"
        assert snap["total"] == 2
        names = {h["name"] for h in snap["top_hot"]}
        assert "Чужой" not in names

        # Селз: только своё.
        snap = await crm_snapshot.build(session, team_id, 3)
        assert snap["scope"] == "own"
        assert snap["total"] == 1
        assert snap["top_hot"][0]["name"] == "Горячий мой"

        # Не участник — ничего.
        assert await crm_snapshot.build(session, team_id, 99) is None
