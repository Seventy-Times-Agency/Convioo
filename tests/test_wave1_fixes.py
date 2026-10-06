"""Волна 1 аудита: очередь мультигорода, возврат резерва токенов,
доступ к лиду при отправке письма, шаг-письмо воронки после ручной
отправки, сопоставление ответа по threadId."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from leadgen.adapters.web_api.routes import _helpers as helpers_mod
from leadgen.core.services.account import tokens
from leadgen.core.services.outreach import email_reply_tracker as tracker
from leadgen.core.services.sales import funnel_engine
from leadgen.db.models import (
    Funnel,
    FunnelStep,
    Lead,
    LeadActivity,
    SearchQuery,
    Team,
    TokenLedger,
    User,
)

pytest_plugins = ["tests.test_team_roles_wave1"]


@pytest.fixture
def no_inline_run(monkeypatch):
    """Поиск не запускается по-настоящему — проверяем только очередь."""

    async def _noop(query_id, profile=None):
        return None

    monkeypatch.setattr(helpers_mod, "run_web_search_inline", _noop)


# ── мультигород ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_second_city_waits_in_queue_then_starts(
    crew, patched_session_factory, no_inline_run
):
    owner = crew["clients"]["owner"]
    team_id = str(crew["team_id"])
    first = owner.post(
        "/api/v1/searches",
        json={"niche": "dentists", "region": "Kyiv", "team_id": team_id, "limit": 20, "profession": "SEO"},
    )
    assert first.status_code == 200, first.text
    second = owner.post(
        "/api/v1/searches",
        json={"niche": "dentists", "region": "Lviv", "team_id": team_id, "limit": 20, "profession": "SEO"},
    )
    assert second.status_code == 200, second.text
    first_id = uuid.UUID(first.json()["id"])
    second_id = uuid.UUID(second.json()["id"])

    async with patched_session_factory() as session:
        a = await session.get(SearchQuery, first_id)
        b = await session.get(SearchQuery, second_id)
        assert a.status == "pending"
        assert b.status == "queued"
        assert b.launch_profile["profession"] == "SEO"
        a.status = "done"
        await session.commit()

    await helpers_mod.finish_search_run(first_id)

    async with patched_session_factory() as session:
        b = await session.get(SearchQuery, second_id)
        assert b.status == "pending"
        assert b.launch_profile is None


# ── токены ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_failed_search_returns_hold_once(crew, patched_session_factory):
    team_id = crew["team_id"]
    owner_id = crew["ids"]["owner"]
    async with patched_session_factory() as session:
        team = await session.get(Team, team_id)
        team.token_balance = 100
        sq = SearchQuery(
            id=uuid.uuid4(),
            user_id=owner_id,
            team_id=team_id,
            niche="cafes",
            region="Odesa",
            status="running",
            source="web",
        )
        session.add(sq)
        await session.flush()
        await tokens.hold(session, team_id, sq.id, 50, user_id=owner_id)
        await session.commit()
        sq_id = sq.id

    async with patched_session_factory() as session:
        assert (await session.get(Team, team_id)).token_balance == 50

    # Пайплайн вышел, не закрыв статус: финал считает это сбоем.
    await helpers_mod.finish_search_run(sq_id)
    await helpers_mod.finish_search_run(sq_id)

    async with patched_session_factory() as session:
        assert (await session.get(Team, team_id)).token_balance == 100
        assert (await session.get(SearchQuery, sq_id)).status == "failed"
        refunds = (
            await session.execute(
                select(TokenLedger)
                .where(TokenLedger.search_id == sq_id)
                .where(TokenLedger.kind == "refund")
            )
        ).scalars().all()
        assert len(refunds) == 1


@pytest.mark.asyncio
async def test_done_search_settles_by_fact(crew, patched_session_factory):
    team_id = crew["team_id"]
    owner_id = crew["ids"]["owner"]
    async with patched_session_factory() as session:
        team = await session.get(Team, team_id)
        team.token_balance = 100
        sq = SearchQuery(
            id=uuid.uuid4(),
            user_id=owner_id,
            team_id=team_id,
            niche="cafes",
            region="Odesa",
            status="done",
            leads_count=7,
            source="web",
        )
        session.add(sq)
        await session.flush()
        await tokens.hold(session, team_id, sq.id, 50, user_id=owner_id)
        await session.commit()
        sq_id = sq.id

    await helpers_mod.finish_search_run(sq_id)

    async with patched_session_factory() as session:
        assert (await session.get(Team, team_id)).token_balance == 93


# ── доступ к лиду ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_email_requires_lead_access(crew, monkeypatch):
    from leadgen.adapters.web_api.routes.outreach import gmail as gmail_route

    monkeypatch.setattr(gmail_route, "_gmail_oauth_configured", lambda: True)
    payload = {"subject": "Hi", "body": "Hello", "to": "x@example.test"}
    # Селз не видит чужого лида — для него лида нет.
    r = crew["clients"]["sales2"].post(
        f"/api/v1/leads/{crew['assigned_lead']}/send-email", json=payload
    )
    assert r.status_code == 404, r.text
    # Свой лид проходит проверку доступа и упирается уже в почту.
    r = crew["clients"]["sales"].post(
        f"/api/v1/leads/{crew['assigned_lead']}/send-email", json=payload
    )
    assert r.status_code == 400, r.text


# ── воронка ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_manual_send_closes_funnel_email_step(crew, patched_session_factory):
    team_id = crew["team_id"]
    async with patched_session_factory() as session:
        funnel = Funnel(
            id=uuid.uuid4(),
            team_id=team_id,
            name="Ручная",
            status="active",
            goal_name="Созвон",
            goal_action="booking",
        )
        funnel.steps = [
            FunnelStep(id=uuid.uuid4(), order_index=0, kind="email", day_offset=0, auto=False),
            FunnelStep(id=uuid.uuid4(), order_index=1, kind="call", day_offset=2),
        ]
        session.add(funnel)
        await session.flush()
        lead = await session.get(Lead, crew["assigned_lead"])
        lead.funnel_id = funnel.id
        lead.funnel_step = 0
        lead.next_touch_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await session.commit()

    async with patched_session_factory() as session:
        lead = await session.get(Lead, crew["assigned_lead"])
        moved = await funnel_engine.complete_email_step_by_hand(session, lead)
        await session.commit()
        assert moved is True
        assert lead.funnel_step == 1


# ── ответы на письма ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reply_matches_by_thread_and_skips_own_sent(
    crew, patched_session_factory, monkeypatch
):
    sales_id = crew["ids"]["sales"]
    async with patched_session_factory() as session:
        user = await session.get(User, sales_id)
        user.email_reply_tracking_enabled = True
        session.add(
            LeadActivity(
                lead_id=crew["assigned_lead"],
                user_id=sales_id,
                kind="email_sent",
                # Gmail API id — в заголовках ответа его не бывает.
                payload={"message_id": "18c0ffee", "thread_id": "thr-1"},
            )
        )
        await session.commit()

    async def _fake_list(access_token, *, after_epoch):
        return [{"id": "18c0ffee"}, {"id": "reply-1"}]

    async def _fake_headers(access_token, message_id):
        if message_id == "18c0ffee":
            return {"_thread_id": "thr-1", "_labels": "SENT"}
        return {
            "in-reply-to": "<CAF+abc@mail.gmail.com>",
            "from": "client@example.test",
            "_thread_id": "thr-1",
            "_labels": "INBOX,UNREAD",
        }

    async def _fake_get_message(access_token, msg_id):
        return {"from_email": "client@example.test", "subject": "Re", "body_text": "Да, давайте"}

    monkeypatch.setattr(tracker, "_list_recent_messages", _fake_list)
    monkeypatch.setattr(tracker, "_fetch_message_headers", _fake_headers)
    monkeypatch.setattr(tracker.gmail, "get_message", _fake_get_message)

    async with patched_session_factory() as session:
        user = await session.get(User, sales_id)
        found = await tracker.scan_replies_for_user(session, user, access_token="t")
    assert found == 1
