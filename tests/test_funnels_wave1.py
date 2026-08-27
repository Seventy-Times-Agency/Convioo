"""Wave-1 funnels: entity CRUD, batch assignment, engine scheduling,
call outcomes and the worker's due-email pass."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.core.services import funnel_engine
from leadgen.db import session as db_session_mod
from leadgen.db.models import (
    Base,
    Funnel,
    FunnelStep,
    Lead,
    LeadActivity,
    OutreachTemplate,
    SearchQuery,
    Team,
    TeamMembership,
)
from leadgen.utils import rate_limit as rate_limit_mod

NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)


def _funnel(**over) -> Funnel:
    f = Funnel(
        id=uuid.uuid4(),
        team_id=over.pop("team_id", uuid.uuid4()),
        name=over.pop("name", "Аудит-первый"),
        status=over.pop("status", "active"),
        goal_name=over.pop("goal_name", "Платный аудит"),
        goal_action=over.pop("goal_action", "payment_calendar"),
        **over,
    )
    f.steps = [
        FunnelStep(id=uuid.uuid4(), order_index=0, kind="call", day_offset=0),
        FunnelStep(
            id=uuid.uuid4(), order_index=1, kind="email", day_offset=1, auto=True
        ),
        FunnelStep(id=uuid.uuid4(), order_index=2, kind="call", day_offset=3),
    ]
    return f


def _lead(**over) -> Lead:
    return Lead(
        id=uuid.uuid4(),
        query_id=over.pop("query_id", uuid.uuid4()),
        name=over.pop("name", "Golden Touch Salon"),
        source="google_places",
        source_id=over.pop("source_id", uuid.uuid4().hex),
        lead_status="new",
        **over,
    )


# ── engine units ───────────────────────────────────────────────────────


def test_attach_and_advance_scheduling():
    f = _funnel()
    lead = _lead()
    funnel_engine.attach_lead(lead, f, now=NOW)
    assert lead.funnel_id == f.id
    assert lead.funnel_step == 0
    assert lead.next_touch_at == NOW  # step 0 is day 0

    funnel_engine.advance_lead(lead, f, now=NOW)
    assert lead.funnel_step == 1
    assert lead.next_touch_at == NOW + timedelta(days=1)

    funnel_engine.advance_lead(lead, f, now=NOW)
    assert lead.funnel_step == 2
    assert lead.next_touch_at == NOW + timedelta(days=3)

    funnel_engine.advance_lead(lead, f, now=NOW)
    assert lead.next_touch_at is None  # path exhausted


def test_no_answer_rule_releases_after_attempts():
    f = _funnel()
    lead = _lead(owner_user_id=7)
    funnel_engine.attach_lead(lead, f, now=NOW)

    r1 = funnel_engine.apply_call_outcome(lead, f, "no_answer", now=NOW)
    assert r1["attempt"] == 1
    assert lead.next_touch_at == NOW + timedelta(days=1)
    assert lead.owner_user_id == 7

    funnel_engine.apply_call_outcome(lead, f, "no_answer", now=NOW)
    r3 = funnel_engine.apply_call_outcome(lead, f, "no_answer", now=NOW)
    assert r3.get("released") is True
    assert r3["paused_days"] == 14
    assert lead.owner_user_id is None  # back to the free pool
    assert lead.no_answer_count == 0
    assert lead.next_touch_at == NOW + timedelta(days=14)


def test_callback_thinking_goal_outcomes():
    f = _funnel()
    lead = _lead()
    funnel_engine.attach_lead(lead, f, now=NOW)

    when = NOW + timedelta(hours=3)
    r = funnel_engine.apply_call_outcome(
        lead, f, "callback", callback_at=when, now=NOW
    )
    assert lead.next_touch_at == when and r["outcome"] == "callback"

    r = funnel_engine.apply_call_outcome(lead, f, "thinking", now=NOW)
    assert lead.funnel_step == 1  # advanced to the follow-up email
    assert lead.next_touch_at == NOW + timedelta(days=1)

    r = funnel_engine.apply_call_outcome(lead, f, "goal", now=NOW)
    assert r["goal_reached"] is True
    assert r["goal_name"] == "Платный аудит"
    assert lead.goal_reached_at == NOW
    assert lead.next_touch_at is None

    with pytest.raises(ValueError):
        funnel_engine.apply_call_outcome(lead, f, "nonsense", now=NOW)


def test_render_template_placeholders():
    tpl = OutreachTemplate(
        id=uuid.uuid4(),
        user_id=1,
        name="t",
        subject="Привет, {name}",
        body="Мы помогаем {niche} в {region}. {name}, интересно?",
    )
    lead = _lead(name="Odessa Bakery")
    subject, body = funnel_engine.render_template(
        tpl, lead, {"niche": "пекарни", "region": "Майами"}
    )
    assert subject == "Привет, Odessa Bakery"
    assert "пекарни" in body and "Майами" in body and "Odessa Bakery" in body


# ── API + worker harness ───────────────────────────────────────────────


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


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    for name in ("login_limiter", "register_limiter"):
        getattr(rate_limit_mod, name)._events.clear()
    yield


def _make_client(patched_session_factory) -> TestClient:
    from leadgen.adapters.web_api import create_app

    return TestClient(create_app())


def _register(client: TestClient, email: str) -> int:
    rate_limit_mod.register_limiter._events.clear()
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Fun",
            "last_name": "Nel",
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
        role: _make_client(maker) for role in ("manager", "sales")
    }
    ids = {
        role: _register(c, f"funnel-{role}@example.test")
        for role, c in clients.items()
    }
    team_id = uuid.uuid4()
    async with maker() as session:
        session.add(Team(id=team_id, name="Dept", plan="free"))
        session.add(
            TeamMembership(
                team_id=team_id, user_id=ids["manager"], role="manager"
            )
        )
        session.add(
            TeamMembership(
                team_id=team_id, user_id=ids["sales"], role="sales"
            )
        )
        sq = SearchQuery(
            id=uuid.uuid4(),
            user_id=ids["manager"],
            team_id=team_id,
            niche="bakery",
            region="Miami",
            status="done",
            source="web",
        )
        session.add(sq)
        await session.flush()
        leads = [
            _lead(query_id=sq.id, name=f"Lead {i}", source_id=f"p-{i}")
            for i in range(3)
        ]
        session.add_all(leads)
        await session.commit()
        return {
            "clients": clients,
            "ids": ids,
            "team_id": team_id,
            "lead_ids": [lead.id for lead in leads],
        }


FUNNEL_BODY = {
    "name": "Аудит-первый",
    "goal_name": "Платный аудит",
    "goal_price": 100,
    "goal_action": "payment_calendar",
    "status": "active",
    "script": "холодный заход v2",
    "steps": [
        {"kind": "call", "day_offset": 0},
        {"kind": "email", "day_offset": 1, "auto": True},
        {"kind": "call", "day_offset": 3},
    ],
}


@pytest.mark.asyncio
async def test_funnel_crud_and_permissions(crew):
    team_id = crew["team_id"]
    # Sales can't create.
    r = crew["clients"]["sales"].post(
        f"/api/v1/teams/{team_id}/funnels", json=FUNNEL_BODY
    )
    assert r.status_code == 403
    # Manager creates.
    r = crew["clients"]["manager"].post(
        f"/api/v1/teams/{team_id}/funnels", json=FUNNEL_BODY
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["goal_name"] == "Платный аудит"
    assert [s["kind"] for s in out["steps"]] == ["call", "email", "call"]
    funnel_id = out["id"]
    # Duplicate name → 409.
    r = crew["clients"]["manager"].post(
        f"/api/v1/teams/{team_id}/funnels", json=FUNNEL_BODY
    )
    assert r.status_code == 409
    # Bad enum → 400.
    bad = dict(FUNNEL_BODY, name="X", goal_action="teleport")
    r = crew["clients"]["manager"].post(
        f"/api/v1/teams/{team_id}/funnels", json=bad
    )
    assert r.status_code == 400
    # Update: rename + replace steps.
    r = crew["clients"]["manager"].patch(
        f"/api/v1/funnels/{funnel_id}",
        json={"steps": [{"kind": "call", "day_offset": 0}]},
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["steps"]) == 1
    # Duplicate.
    r = crew["clients"]["manager"].post(
        f"/api/v1/funnels/{funnel_id}/duplicate"
    )
    assert r.status_code == 200
    assert r.json()["status"] == "draft"
    # Sales sees the list (read-only) but can't mutate.
    r = crew["clients"]["sales"].get(f"/api/v1/teams/{team_id}/funnels")
    assert r.status_code == 200
    r = crew["clients"]["sales"].patch(
        f"/api/v1/funnels/{funnel_id}", json={"name": "hack"}
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_assign_batch_and_lead_funnel_view(
    crew, patched_session_factory
):
    team_id = crew["team_id"]
    r = crew["clients"]["manager"].post(
        f"/api/v1/teams/{team_id}/funnels", json=FUNNEL_BODY
    )
    funnel_id = r.json()["id"]

    # Sales can't distribute.
    r = crew["clients"]["sales"].post(
        f"/api/v1/funnels/{funnel_id}/assign",
        json={
            "lead_ids": [str(i) for i in crew["lead_ids"]],
            "owner_user_id": crew["ids"]["sales"],
        },
    )
    assert r.status_code == 403

    # Manager: выбор → селз → воронка → назначить.
    r = crew["clients"]["manager"].post(
        f"/api/v1/funnels/{funnel_id}/assign",
        json={
            "lead_ids": [str(i) for i in crew["lead_ids"]],
            "owner_user_id": crew["ids"]["sales"],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["assigned"] == 3

    async with patched_session_factory() as session:
        lead = await session.get(Lead, crew["lead_ids"][0])
        assert str(lead.funnel_id) == funnel_id
        assert lead.owner_user_id == crew["ids"]["sales"]
        assert lead.next_touch_at is not None
        acts = (
            (
                await session.execute(
                    select(LeadActivity).where(
                        LeadActivity.kind == "assigned"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(acts) == 3

    # The rep reads the funnel of their lead — green button data.
    r = crew["clients"]["sales"].get(
        f"/api/v1/leads/{crew['lead_ids'][0]}/funnel"
    )
    assert r.status_code == 200, r.text
    assert r.json()["goal_name"] == "Платный аудит"


@pytest.mark.asyncio
async def test_delete_funnel_detaches_leads(crew, patched_session_factory):
    team_id = crew["team_id"]
    r = crew["clients"]["manager"].post(
        f"/api/v1/teams/{team_id}/funnels", json=FUNNEL_BODY
    )
    funnel_id = r.json()["id"]
    crew["clients"]["manager"].post(
        f"/api/v1/funnels/{funnel_id}/assign",
        json={"lead_ids": [str(i) for i in crew["lead_ids"]]},
    )
    r = crew["clients"]["manager"].delete(f"/api/v1/funnels/{funnel_id}")
    assert r.status_code == 200
    async with patched_session_factory() as session:
        lead = await session.get(Lead, crew["lead_ids"][0])
        assert lead.funnel_id is None
        assert lead.next_touch_at is None


@pytest.mark.asyncio
async def test_worker_due_email_pass(crew, patched_session_factory):
    """Auto email step sends (log-only sender returns True) and
    advances; non-auto step drafts a single approval activity."""
    maker = patched_session_factory
    team_id = crew["team_id"]
    manager_id = crew["ids"]["manager"]

    async with maker() as session:
        tpl = OutreachTemplate(
            id=uuid.uuid4(),
            user_id=manager_id,
            team_id=team_id,
            name="догрев",
            subject="Привет, {name}",
            body="Текст для {name}",
        )
        session.add(tpl)
        auto_funnel = _funnel(team_id=team_id, name="Авто")
        auto_funnel.created_by_user_id = manager_id
        auto_funnel.steps[1].template_id = tpl.id
        manual_funnel = _funnel(team_id=team_id, name="Ручная")
        manual_funnel.created_by_user_id = manager_id
        manual_funnel.steps[1].auto = False
        session.add_all([auto_funnel, manual_funnel])
        await session.flush()

        lead_auto = await session.get(Lead, crew["lead_ids"][0])
        lead_auto.contact_email = "auto@example.test"
        lead_auto.funnel_id = auto_funnel.id
        lead_auto.funnel_step = 1  # the email step
        lead_auto.next_touch_at = NOW - timedelta(hours=1)

        lead_manual = await session.get(Lead, crew["lead_ids"][1])
        lead_manual.contact_email = "manual@example.test"
        lead_manual.owner_user_id = crew["ids"]["sales"]
        lead_manual.funnel_id = manual_funnel.id
        lead_manual.funnel_step = 1
        lead_manual.next_touch_at = NOW - timedelta(hours=1)
        await session.commit()

    async with maker() as session:
        stats = await funnel_engine.process_due_email_touches(
            session, now=NOW
        )
    assert stats["sent"] == 1
    assert stats["drafted"] == 1

    async with maker() as session:
        lead_auto = await session.get(Lead, crew["lead_ids"][0])
        assert lead_auto.funnel_step == 2  # advanced past the email
        acts = (
            (
                await session.execute(
                    select(LeadActivity).where(
                        LeadActivity.kind == "funnel_email_due"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(acts) == 1

        # Re-run: the approval activity is not duplicated.
        stats2 = await funnel_engine.process_due_email_touches(
            session, now=NOW
        )
        assert stats2["drafted"] == 0
