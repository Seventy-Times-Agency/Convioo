"""Wave-1 team events: Telegram notifications for action-requiring
moments — пакет назначен, цель достигнута, просроченные перезвоны,
дневные сводки."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.core.services import team_events
from leadgen.db import session as db_session_mod
from leadgen.db.models import (
    Base,
    Funnel,
    FunnelStep,
    Lead,
    LeadActivity,
    SearchQuery,
    Team,
    TeamMembership,
    TelegramConnection,
)
from leadgen.utils import rate_limit as rate_limit_mod


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


@pytest.fixture
def sent_messages(monkeypatch):
    """Capture telegram sends instead of hitting the API."""
    captured: list[tuple[int, str]] = []

    async def fake_send(chat_id: int, text: str, parse_mode: str = "HTML"):
        captured.append((chat_id, text))
        return {"ok": True}

    import leadgen.adapters.telegram_v2.api as tg_api

    monkeypatch.setattr(tg_api, "send_message", fake_send)
    return captured


def _client(patched_session_factory) -> TestClient:
    from leadgen.adapters.web_api import create_app

    return TestClient(create_app())


def _register(client: TestClient, email: str) -> int:
    rate_limit_mod.register_limiter._events.clear()
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Ev",
            "last_name": "Ent",
            "email": email,
            "password": "correcthorse123",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


@pytest_asyncio.fixture
async def crew(patched_session_factory):
    maker = patched_session_factory
    clients = {
        r: _client(maker) for r in ("owner", "manager", "sales")
    }
    ids = {
        r: _register(c, f"events-{r}@example.test")
        for r, c in clients.items()
    }
    team_id = uuid.uuid4()
    async with maker() as session:
        session.add(Team(id=team_id, name="Dept"))
        for role, uid in ids.items():
            session.add(
                TeamMembership(team_id=team_id, user_id=uid, role=role)
            )
        # Everyone linked to Telegram; chat_id = 1000 + user_id.
        for uid in ids.values():
            session.add(
                TelegramConnection(user_id=uid, chat_id=1000 + uid)
            )
        funnel = Funnel(
            id=uuid.uuid4(),
            team_id=team_id,
            name="Аудит-первый",
            status="active",
            goal_name="Платный аудит",
            goal_action="payment_calendar",
            no_answer_attempts=3,
            no_answer_pause_days=14,
        )
        funnel.steps = [
            FunnelStep(order_index=0, kind="call", day_offset=0)
        ]
        session.add(funnel)
        sq = SearchQuery(
            id=uuid.uuid4(),
            user_id=ids["manager"],
            team_id=team_id,
            niche="salons",
            region="Miami",
            status="done",
            source="web",
        )
        session.add(sq)
        await session.flush()
        lead = Lead(
            id=uuid.uuid4(),
            query_id=sq.id,
            name="Golden Touch Salon",
            source="google_places",
            source_id="ev-1",
            lead_status="new",
            owner_user_id=ids["sales"],
            funnel_id=funnel.id,
            score_ai=88,
        )
        session.add(lead)
        await session.commit()
        return {
            "clients": clients,
            "ids": ids,
            "team_id": team_id,
            "funnel_id": funnel.id,
            "search_id": sq.id,
            "lead_id": lead.id,
        }


@pytest.mark.asyncio
async def test_notify_user_without_link(
    patched_session_factory, sent_messages
):
    async with patched_session_factory() as session:
        ok = await team_events.notify_user(session, 424242, "hi")
    assert ok is False
    assert sent_messages == []


@pytest.mark.asyncio
async def test_batch_assigned_pings_rep(crew, sent_messages):
    r = crew["clients"]["manager"].post(
        f"/api/v1/funnels/{crew['funnel_id']}/assign",
        json={
            "lead_ids": [str(crew["lead_id"])],
            "owner_user_id": crew["ids"]["sales"],
        },
    )
    assert r.status_code == 200, r.text
    rep_chat = 1000 + crew["ids"]["sales"]
    assert any(
        chat == rep_chat and "пакет" in text.lower()
        for chat, text in sent_messages
    )


@pytest.mark.asyncio
async def test_goal_reached_pings_manager(crew, sent_messages):
    r = crew["clients"]["sales"].post(
        f"/api/v1/leads/{crew['lead_id']}/call-outcome",
        json={"outcome": "goal"},
    )
    assert r.status_code == 200, r.text
    mgr_chat = 1000 + crew["ids"]["manager"]
    assert any(
        chat == mgr_chat and "Платный аудит" in text
        for chat, text in sent_messages
    )
    # Селз не получает собственное уведомление о цели.
    rep_chat = 1000 + crew["ids"]["sales"]
    assert not any(chat == rep_chat for chat, _ in sent_messages)


@pytest.mark.asyncio
async def test_overdue_and_escalation(
    crew, patched_session_factory, sent_messages
):
    now = datetime.now(timezone.utc)
    async with patched_session_factory() as session:
        lead = await session.get(Lead, crew["lead_id"])
        lead.next_touch_at = now - timedelta(hours=3)  # просрочен
        stale = Lead(
            id=uuid.uuid4(),
            query_id=crew["search_id"],
            name="Alex Auto Repair",
            source="google_places",
            source_id="ev-2",
            lead_status="new",
            owner_user_id=crew["ids"]["sales"],
            next_touch_at=now - timedelta(hours=30),  # > суток
        )
        session.add(stale)
        await session.commit()

    async with patched_session_factory() as session:
        stats = await team_events.process_overdue_callbacks(
            session, now=now
        )
    assert stats["nudged"] == 1
    assert stats["escalated"] >= 1
    rep_chat = 1000 + crew["ids"]["sales"]
    mgr_chat = 1000 + crew["ids"]["manager"]
    rep_msgs = [t for c, t in sent_messages if c == rep_chat]
    mgr_msgs = [t for c, t in sent_messages if c == mgr_chat]
    assert len(rep_msgs) == 1 and "Просроченные" in rep_msgs[0]
    assert any("Эскалация" in t for t in mgr_msgs)


@pytest.mark.asyncio
async def test_digests(crew, patched_session_factory, sent_messages):
    async with patched_session_factory() as session:
        session.add(
            LeadActivity(
                lead_id=crew["lead_id"],
                user_id=crew["ids"]["sales"],
                team_id=crew["team_id"],
                kind="call",
                payload={"outcome": "no_answer"},
            )
        )
        await session.commit()

    async with patched_session_factory() as session:
        sent = await team_events.send_team_digests(
            session, audience="managers"
        )
    assert sent >= 1
    mgr_chat = 1000 + crew["ids"]["manager"]
    assert any(
        c == mgr_chat and "Вечерняя сводка" in t for c, t in sent_messages
    )

    sent_messages.clear()
    async with patched_session_factory() as session:
        sent = await team_events.send_team_digests(
            session, audience="owners"
        )
    assert sent >= 1
    owner_chat = 1000 + crew["ids"]["owner"]
    assert any(
        c == owner_chat and "Утренняя сводка" in t
        for c, t in sent_messages
    )
