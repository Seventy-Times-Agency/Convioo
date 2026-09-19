"""Телефония: звонок из карточки → webhook → расшифровка → разбор.

Провайдер, ElevenLabs и Claude подменены — проверяем нашу логику:
сопоставление webhook со звонком, безопасность токена, ролевой
доступ к записям и сборку реплик из слов.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.core.services.telephony import normalize_number
from leadgen.core.services.telephony.processing import _segments
from leadgen.core.services.telephony.ringostat import RingostatProvider
from leadgen.db.models import (
    Base,
    Call,
    Lead,
    LeadActivity,
    SearchQuery,
    Team,
    TeamMembership,
)

TOKEN = "hook-secret-123"


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
def factory(monkeypatch, db_engine):
    from leadgen.config import get_settings
    from leadgen.db import session as db_session_mod

    maker = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr(db_session_mod, "_engine", db_engine)
    monkeypatch.setattr(db_session_mod, "_session_factory", maker)
    monkeypatch.setenv("TELEPHONY_PROVIDER", "ringostat")
    monkeypatch.setenv("RINGOSTAT_AUTH_KEY", "test-key")
    monkeypatch.setenv("TELEPHONY_WEBHOOK_TOKEN", TOKEN)
    get_settings.cache_clear()
    yield maker
    get_settings.cache_clear()


def _register(client, email):
    from leadgen.utils import rate_limit as rate_limit_mod

    rate_limit_mod.register_limiter._events.clear()
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "T",
            "last_name": "L",
            "email": email,
            "password": "correcthorse123",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


# ── чистые функции ────────────────────────────────────────────────────


def test_normalize_ukrainian_numbers():
    assert normalize_number("+380 (67) 123-45-67") == "380671234567"
    assert normalize_number("067 123 45 67") == "380671234567"
    assert normalize_number("00380671234567") == "380671234567"
    assert normalize_number("") is None


def test_ringostat_event_parsing():
    p = RingostatProvider("k")
    ev = p.parse_event(
        {
            "call_id": "abc",
            "callee": "+380671234567",
            "status": "ANSWERED",
            "call_duration": "95",
            "dialog": "80",
            "recording_wav": "https://example.com/r.wav",
        }
    )
    assert ev.answered and ev.talk_sec == 80 and ev.duration_sec == 95
    assert ev.recording_url == "https://example.com/r.wav"

    # Не дозвонились — записи нет, даже если провайдер прислал ссылку.
    ev = p.parse_event(
        {"callee": "0671234567", "status": "NO ANSWER", "recording_wav": "x"}
    )
    assert not ev.answered and ev.recording_url is None
    # Служебное событие без номера клиента — не про звонок.
    assert p.parse_event({"status": "ANSWERED"}) is None


def test_segments_from_two_channels():
    stt = {
        "transcripts": [
            {
                "channel_index": 0,
                "words": [
                    {"text": "Добрий", "type": "word", "start": 0.1},
                    {"text": " ", "type": "spacing", "start": 0.5},
                    {"text": "день", "type": "word", "start": 0.6},
                ],
            },
            {
                "channel_index": 1,
                "words": [
                    {"text": "Слухаю", "type": "word", "start": 1.2},
                ],
            },
        ]
    }
    segs = _segments(stt)
    assert segs == [
        {"speaker": "rep", "start": 0.1, "text": "Добрий день"},
        {"speaker": "client", "start": 1.2, "text": "Слухаю"},
    ]


# ── полный путь через API ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_call_webhook_and_processing(factory, monkeypatch):
    from leadgen.adapters.web_api import create_app
    from leadgen.core.services.telephony import processing

    started: list[dict] = []

    async def fake_start(self, *, extension, destination):
        started.append({"extension": extension, "destination": destination})

    monkeypatch.setattr(RingostatProvider, "start_call", fake_start)

    scheduled: list[uuid.UUID] = []

    async def fake_schedule(call_id):
        scheduled.append(call_id)

    monkeypatch.setattr(processing, "schedule", fake_schedule)

    rep_c = TestClient(create_app())
    rep_id = _register(rep_c, "tel-rep@example.test")
    other_c = TestClient(create_app())
    other_id = _register(other_c, "tel-other@example.test")

    team_id = uuid.uuid4()
    async with factory() as session:
        session.add(Team(id=team_id, name="K"))
        session.add_all(
            [
                TeamMembership(team_id=team_id, user_id=rep_id, role="sales"),
                TeamMembership(team_id=team_id, user_id=other_id, role="sales"),
            ]
        )
        q = SearchQuery(
            id=uuid.uuid4(), user_id=rep_id, team_id=team_id,
            niche="n", region="r", status="done", source="web",
        )
        session.add(q)
        await session.flush()
        lead = Lead(
            query_id=q.id, name="Пекарня", source="g", source_id="x",
            phone="067 123 45 67", owner_user_id=rep_id,
        )
        session.add(lead)
        await session.commit()
        lead_id = lead.id

    # Без своего номера звонить нельзя — понятная ошибка.
    r = rep_c.post(f"/api/v1/leads/{lead_id}/call")
    assert r.status_code == 409

    r = rep_c.patch(
        f"/api/v1/teams/{team_id}/members/{rep_id}/phone",
        json={"phone_extension": "380501112233"},
    )
    assert r.status_code == 200
    # Чужой номер селз менять не может.
    r = rep_c.patch(
        f"/api/v1/teams/{team_id}/members/{other_id}/phone",
        json={"phone_extension": "1"},
    )
    assert r.status_code == 403

    r = rep_c.post(f"/api/v1/leads/{lead_id}/call")
    assert r.status_code == 200, r.text
    assert started == [
        {"extension": "380501112233", "destination": "+380671234567"}
    ]

    # Webhook с неверным токеном — отказ.
    hook = "/api/v1/telephony/ringostat/webhook"
    r = rep_c.post(f"{hook}?token=wrong", data={"callee": "380671234567"})
    assert r.status_code == 403

    # Правильный — звонок закрывается, запись уходит в обработку.
    r = TestClient(create_app()).post(
        f"{hook}?token={TOKEN}",
        data={
            "call_id": "rs-1",
            "callee": "+380671234567",
            "status": "ANSWERED",
            "call_duration": "140",
            "dialog": "125",
            "recording_wav": "https://records.example.com/1.wav",
        },
    )
    assert r.status_code == 200, r.text
    assert len(scheduled) == 1

    async with factory() as session:
        call = (await session.execute(select(Call))).scalar_one()
        assert call.state == "completed"
        assert call.talk_sec == 125
        assert call.provider_call_id == "rs-1"

    # Обработка: расшифровка и разбор подменены.
    async def fake_download(url):
        return b"RIFF"

    async def fake_transcribe(audio, stereo_hint=True):
        return [
            {"speaker": "rep", "start": 0.0, "text": "Добрий день"},
            {"speaker": "client", "start": 2.0, "text": "Передзвоніть у четвер"},
        ]

    async def fake_analyze(segments, funnel):
        return {
            "summary": "Клиент просит перезвонить в четверг",
            "next_step": "Перезвонить в четверг",
            "suggested_outcome": "callback",
            "objections": [],
            "quality_score": 7,
        }

    monkeypatch.setattr(processing, "_download", fake_download)
    monkeypatch.setattr(processing, "transcribe", fake_transcribe)
    monkeypatch.setattr(processing, "analyze", fake_analyze)
    await processing.process_call(scheduled[0])

    async with factory() as session:
        call = (await session.execute(select(Call))).scalar_one()
        assert call.state == "analyzed"
        assert call.analysis["suggested_outcome"] == "callback"
        act = (
            await session.execute(
                select(LeadActivity).where(LeadActivity.kind == "call_analyzed")
            )
        ).scalar_one()
        assert act.payload["talk_sec"] == 125

    # Карточка лида: владелец видит звонок с разбором…
    r = rep_c.get(f"/api/v1/leads/{lead_id}/calls")
    assert r.status_code == 200
    body = r.json()
    assert body[0]["analysis"]["next_step"] == "Перезвонить в четверг"
    assert body[0]["has_recording"] is True
    # …а чужой селз — нет (как и сам лид).
    r = other_c.get(f"/api/v1/leads/{lead_id}/calls")
    assert r.status_code == 404


def test_region_routes(monkeypatch):
    """Код страны номера выбирает провайдера; длинный префикс важнее."""
    from leadgen.config import get_settings
    from leadgen.core.services import telephony as tel

    monkeypatch.setenv("RINGOSTAT_AUTH_KEY", "k")
    monkeypatch.setenv("TELEPHONY_PROVIDER", "")
    monkeypatch.setenv("TELEPHONY_ROUTES", "380:ringostat, 1:twilio")
    get_settings.cache_clear()
    try:
        assert tel.get_provider_for("+380671234567").name == "ringostat"
        # Маршрут на ещё не подключённого провайдера → звонить нечем.
        assert tel.get_provider_for("+13055551234") is None
        # Номер вне маршрутов без провайдера по умолчанию → None.
        assert tel.get_provider_for("+442071234567") is None
        assert tel.enabled_providers() == ["ringostat"]
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_refused_recording_is_not_kept(factory, monkeypatch):
    """«Отменить запись»: ссылка не сохраняется, в обработку не идёт."""
    from leadgen.adapters.web_api import create_app
    from leadgen.core.services.telephony import processing

    async def fake_start(self, *, extension, destination):
        return None

    monkeypatch.setattr(RingostatProvider, "start_call", fake_start)
    scheduled: list = []

    async def fake_schedule(call_id):
        scheduled.append(call_id)

    monkeypatch.setattr(processing, "schedule", fake_schedule)

    c = TestClient(create_app())
    uid = _register(c, "consent@example.test")
    team_id = uuid.uuid4()
    async with factory() as session:
        session.add(Team(id=team_id, name="K"))
        session.add(
            TeamMembership(
                team_id=team_id, user_id=uid, role="sales",
                phone_extension="380500000000",
            )
        )
        q = SearchQuery(
            id=uuid.uuid4(), user_id=uid, team_id=team_id,
            niche="n", region="r", status="done", source="web",
        )
        session.add(q)
        await session.flush()
        lead = Lead(
            query_id=q.id, name="L", source="g", source_id="z",
            phone="+380931112233", owner_user_id=uid,
        )
        session.add(lead)
        await session.commit()
        lead_id = lead.id

    call_id = c.post(f"/api/v1/leads/{lead_id}/call").json()["call_id"]
    r = c.post(f"/api/v1/calls/{call_id}/consent", json={"allowed": False})
    assert r.status_code == 200

    r = TestClient(create_app()).post(
        f"/api/v1/telephony/ringostat/webhook?token={TOKEN}",
        data={
            "callee": "380931112233",
            "status": "ANSWERED",
            "dialog": "60",
            "recording_wav": "https://records.example.com/2.wav",
        },
    )
    assert r.status_code == 200
    assert scheduled == []
    async with factory() as session:
        call = (await session.execute(select(Call))).scalar_one()
        assert call.recording_url is None
        assert call.record_consent is False
        assert call.talk_sec == 60  # длительность всё равно считаем
