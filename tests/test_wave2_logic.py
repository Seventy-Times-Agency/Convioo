"""Волна 2 аудита: автописьма воронки с Gmail менеджера, повтор
сохранённого поиска общим путём, регион по стране города, очередь
звонков без шагов-писем."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from leadgen.adapters.web_api.routes import _helpers as helpers_mod
from leadgen.core.services.outreach import gmail_outreach
from leadgen.core.services.sales import funnel_engine
from leadgen.db.models import (
    Funnel,
    FunnelStep,
    Lead,
    LeadActivity,
    OutreachTemplate,
    SavedSearch,
    SearchQuery,
)
from leadgen.pipeline.search import _collector_locale

pytest_plugins = ["tests.test_team_roles_wave1"]


@pytest.fixture
def no_inline_run(monkeypatch):
    async def _noop(query_id, profile=None):
        return None

    monkeypatch.setattr(helpers_mod, "run_web_search_inline", _noop)


async def _auto_email_funnel(session, crew, *, due: datetime) -> tuple[Funnel, Lead]:
    team_id = crew["team_id"]
    manager_id = crew["ids"]["manager"]
    tpl = OutreachTemplate(
        id=uuid.uuid4(),
        user_id=manager_id,
        team_id=team_id,
        name="первое",
        subject="Про {niche} в {region}",
        body="Здравствуйте, {name}",
    )
    session.add(tpl)
    funnel = Funnel(
        id=uuid.uuid4(),
        team_id=team_id,
        name="Авто",
        status="active",
        goal_name="Созвон",
        goal_action="booking",
        created_by_user_id=manager_id,
    )
    funnel.steps = [
        FunnelStep(id=uuid.uuid4(), order_index=0, kind="email", day_offset=0, auto=True, template_id=tpl.id),
        FunnelStep(id=uuid.uuid4(), order_index=1, kind="call", day_offset=2),
    ]
    session.add(funnel)
    await session.flush()
    lead = await session.get(Lead, crew["assigned_lead"])
    lead.contact_email = "client@example.test"
    lead.funnel_id = funnel.id
    lead.funnel_step = 0
    lead.next_touch_at = due
    await session.commit()
    return funnel, lead


@pytest.mark.asyncio
async def test_auto_email_goes_from_rep_gmail_with_placeholders(
    crew, patched_session_factory, monkeypatch
):
    calls: list[dict] = []

    async def _fake_send(session, **kw):
        calls.append(kw)
        return gmail_outreach.SentEmail(
            to=kw["to"], subject=kw["subject"], message_id="m1", thread_id="t1",
            sent_at=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(gmail_outreach, "send_cold_email", _fake_send)
    async with patched_session_factory() as session:
        await _auto_email_funnel(session, crew, due=datetime.now(timezone.utc) - timedelta(minutes=5))

    async with patched_session_factory() as session:
        stats = await funnel_engine.process_due_email_touches(session)
        # Второй прогон по тому же лиду ничего не шлёт.
        again = await funnel_engine.process_due_email_touches(session)
    assert stats["sent"] == 1 and again["sent"] == 0
    assert len(calls) == 1
    # Отправитель — владелец лида, плейсхолдеры заполнены из поиска.
    assert calls[0]["user_id"] == crew["ids"]["sales"]
    assert calls[0]["subject"] == "Про roofing в Miami"

    async with patched_session_factory() as session:
        lead = await session.get(Lead, crew["assigned_lead"])
        assert lead.funnel_step == 1
        sent = (
            await session.execute(
                select(LeadActivity).where(LeadActivity.kind == "email_sent")
            )
        ).scalars().all()
        assert len(sent) == 1 and sent[0].payload["thread_id"] == "t1"


@pytest.mark.asyncio
async def test_auto_email_without_gmail_waits_for_rep(
    crew, patched_session_factory, monkeypatch
):
    async def _no_mailbox(session, **kw):
        raise gmail_outreach.OutreachSendError("not_connected", "no gmail")

    monkeypatch.setattr(gmail_outreach, "send_cold_email", _no_mailbox)
    due = datetime.now(timezone.utc) - timedelta(minutes=5)
    async with patched_session_factory() as session:
        await _auto_email_funnel(session, crew, due=due)
        stats = await funnel_engine.process_due_email_touches(session)
    assert stats["drafted"] == 1

    async with patched_session_factory() as session:
        lead = await session.get(Lead, crew["assigned_lead"])
        assert lead.funnel_step == 0
        assert lead.next_touch_at is not None  # срок вернули, лид не потерян
        waiting = (
            await session.execute(
                select(LeadActivity).where(LeadActivity.kind == "funnel_email_due")
            )
        ).scalars().all()
        assert waiting[0].payload["reason"] == "no_mailbox"


@pytest.mark.asyncio
async def test_call_queue_skips_email_steps(crew, patched_session_factory):
    async with patched_session_factory() as session:
        await _auto_email_funnel(session, crew, due=datetime.now(timezone.utc) - timedelta(hours=2))
    r = crew["clients"]["sales"].get(
        "/api/v1/work/queue", params={"team_id": str(crew["team_id"])}
    )
    assert r.status_code == 200, r.text
    ids = {q["id"] for b in ("callbacks", "hot", "rest", "later") for q in r.json()[b]}
    assert str(crew["assigned_lead"]) not in ids


@pytest.mark.asyncio
async def test_saved_search_repeat_keeps_params(
    crew, patched_session_factory, no_inline_run
):
    owner = crew["clients"]["owner"]
    r = owner.post(
        "/api/v1/saved-searches",
        json={
            "name": "roofing · Miami",
            "niche": "roofing",
            "region": "Miami",
            "scope": "city",
            "max_results": 30,
            "schedule": "weekly",
            "team_id": str(crew["team_id"]),
            "launch_params": {
                "country_code": "US",
                "profession": "SEO",
                "website_filter": "without",
                "find_decision_makers": True,
            },
        },
    )
    assert r.status_code == 200, r.text
    saved_id = r.json()["id"]
    # Та же ниша и город, что у поиска команды из фикстуры, — у повтора
    # это не повод для отказа.
    r = owner.post(f"/api/v1/saved-searches/{saved_id}/run")
    assert r.status_code == 200, r.text
    async with patched_session_factory() as session:
        q = await session.get(SearchQuery, uuid.UUID(r.json()["id"]))
        assert q.country_code == "US"
        assert q.max_results == 30
        assert q.prefilters == {"website": "without"}
        assert q.find_decision_makers is True
        saved = await session.get(SavedSearch, uuid.UUID(saved_id))
        assert saved.launch_params["profession"] == "SEO"


def test_collector_locale_uses_city_country_and_english():
    assert _collector_locale([], "pl") == ("en", "PL")
    assert _collector_locale(["uk"], "PL") == ("uk", "PL")
    assert _collector_locale(["uk"], None) == ("uk", "UA")
    assert _collector_locale([], None) == ("en", None)
    assert _collector_locale(["ru"], "RU") == ("ru", None)


@pytest.mark.asyncio
async def test_sales_counts_are_own_leads_only(crew):
    r = crew["clients"]["sales"].get(
        "/api/v1/leads", params={"team_id": str(crew["team_id"])}
    )
    assert r.status_code == 200, r.text
    counts = r.json()["counts"]
    # В команде два лида, селзу назначен один — свободный пул ему не виден.
    assert counts["total"] == 1
    assert counts["free"] == 0


@pytest.mark.asyncio
async def test_telegram_relink_from_new_chat_replaces_old(
    crew, patched_session_factory, monkeypatch
):
    from leadgen.adapters.telegram_v2 import bot as bot_mod
    from leadgen.db.models import TelegramConnection

    sent: list[tuple[int, str]] = []

    async def _fake_send(chat_id, text, **_kw):
        sent.append((chat_id, text))

    monkeypatch.setattr(bot_mod.tg, "send_message", _fake_send)
    user_id = crew["ids"]["sales"]
    await bot_mod._link_account(111, bot_mod.generate_link_token(user_id))
    await bot_mod._link_account(222, bot_mod.generate_link_token(user_id))
    async with patched_session_factory() as session:
        rows = (
            await session.execute(
                select(TelegramConnection).where(TelegramConnection.user_id == user_id)
            )
        ).scalars().all()
    assert [r.chat_id for r in rows] == [222]
    assert sent[-1][0] == 222


def test_exclusions_reach_the_scoring_prompt():
    from leadgen.analysis.prompts.system import _build_system_prompt

    prompt = _build_system_prompt({"exclusions": "сети и франшизы"})
    assert "сети и франшизы" in prompt
    assert '"excluded": true' in prompt


@pytest.mark.asyncio
async def test_exclusions_saved_with_search(crew, patched_session_factory, no_inline_run):
    r = crew["clients"]["owner"].post(
        "/api/v1/searches",
        json={
            "niche": "dentists",
            "region": "Warsaw",
            "country_code": "PL",
            "team_id": str(crew["team_id"]),
            "exclusions": "сети и франшизы, маркетплейсы",
        },
    )
    assert r.status_code == 200, r.text
    async with patched_session_factory() as session:
        q = await session.get(SearchQuery, uuid.UUID(r.json()["id"]))
        assert q.prefilters["exclude"] == "сети и франшизы, маркетплейсы"
        assert q.country_code == "PL"
