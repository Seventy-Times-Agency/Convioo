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

from leadgen.core.services.sales.telephony import (
    TelephonyError,
    normalize_number,
)
from leadgen.core.services.sales.telephony.processing import _segments
from leadgen.core.services.sales.telephony.ringostat import RingostatProvider
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
    # США без кода страны — как отдаёт Google Places.
    assert normalize_number("(305) 555-1234") == "13055551234"
    assert normalize_number("+1 305-555-1234") == "13055551234"


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
    from leadgen.core.services.sales.telephony import processing

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
    # Обе стороны уходят провайдеру в E.164: в настройках номер пишут
    # как привыкли, приводим его здесь.
    assert started == [
        {"extension": "+380501112233", "destination": "+380671234567"}
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

    async def fake_transcribe(audio, stereo_hint=True, rep_channel=0):
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
    # Автоматика по умолчанию только расшифровывает; оценку включает команда.
    async with factory() as session:
        team = (await session.execute(select(Team))).scalar_one()
        team.call_auto_analyze = True
        await session.commit()
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
    from leadgen.core.services.sales import telephony as tel

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
    from leadgen.core.services.sales.telephony import processing

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


# ── повторы, чужие команды, зависшие звонки ───────────────────────────


async def _team_with_lead(
    factory, *, user_id, phone, extension="380500000000", name="K"
):
    team_id = uuid.uuid4()
    async with factory() as session:
        session.add(Team(id=team_id, name=name))
        session.add(
            TeamMembership(
                team_id=team_id, user_id=user_id, role="sales",
                phone_extension=extension,
            )
        )
        q = SearchQuery(
            id=uuid.uuid4(), user_id=user_id, team_id=team_id,
            niche="n", region="r", status="done", source="web",
        )
        session.add(q)
        await session.flush()
        lead = Lead(
            query_id=q.id, name=name, source="g",
            source_id=str(uuid.uuid4()), phone=phone,
            owner_user_id=user_id,
        )
        session.add(lead)
        await session.commit()
        return team_id, lead.id


@pytest.mark.asyncio
async def test_repeated_webhook_is_processed_once(factory, monkeypatch):
    """Провайдер прислал итог дважды — расшифровка и разбор один раз,
    уже разобранный звонок не откатывается назад."""
    from leadgen.adapters.web_api import create_app
    from leadgen.core.services.sales.telephony import processing

    async def fake_start(self, *, extension, destination):
        return None

    monkeypatch.setattr(RingostatProvider, "start_call", fake_start)
    scheduled: list = []

    async def fake_schedule(call_id):
        scheduled.append(call_id)

    monkeypatch.setattr(processing, "schedule", fake_schedule)

    c = TestClient(create_app())
    uid = _register(c, "dup@example.test")
    _team, lead_id = await _team_with_lead(
        factory, user_id=uid, phone="+380931112244"
    )
    assert c.post(f"/api/v1/leads/{lead_id}/call").status_code == 200

    event = {
        "cdr_id": "rs-dup",
        "dst": "380931112244",
        "disposition": "ANSWERED",
        "billsec": "70",
        "recording_wav": "https://records.example.com/dup.wav",
    }
    hook = f"/api/v1/telephony/ringostat/webhook?token={TOKEN}"
    r = TestClient(create_app()).post(hook, json=event)
    assert r.status_code == 200 and r.json() == {"ok": True}

    async with factory() as session:
        call = (await session.execute(select(Call))).scalar_one()
        call.state = "analyzed"
        call.analysis = {"summary": "s"}
        await session.commit()

    r = TestClient(create_app()).post(hook, json=event)
    assert r.json() == {"ok": True, "ignored": "duplicate"}
    assert len(scheduled) == 1
    async with factory() as session:
        call = (await session.execute(select(Call))).scalar_one()
        assert call.state == "analyzed"
        assert call.analysis == {"summary": "s"}


@pytest.mark.asyncio
async def test_direct_call_matches_only_telephony_teams(factory):
    """Звонок мимо кнопки привязывается к лиду только в команде с
    настроенной телефонией; номер в двух таких командах — не угадываем."""
    from leadgen.adapters.web_api import create_app

    c = TestClient(create_app())
    uid = _register(c, "direct@example.test")
    hook = f"/api/v1/telephony/ringostat/webhook?token={TOKEN}"

    # Демо-команда: лид с тем же номером, но телефония не настроена.
    await _team_with_lead(
        factory, user_id=uid, phone="067 555 44 33",
        extension=None, name="Demo",
    )
    r = TestClient(create_app()).post(
        hook, data={"callee": "380675554433", "status": "NO ANSWER"}
    )
    assert r.json() == {"ok": True, "ignored": "unknown number"}

    # Рабочая команда — звонок ложится к её лиду.
    team_id, lead_id = await _team_with_lead(
        factory, user_id=uid, phone="+380675554433", name="Work"
    )
    r = TestClient(create_app()).post(
        hook, data={"callee": "380675554433", "status": "NO ANSWER"}
    )
    assert r.json() == {"ok": True}
    async with factory() as session:
        call = (await session.execute(select(Call))).scalar_one()
        assert call.lead_id == lead_id and call.team_id == team_id
        assert call.state == "missed"

    # Тот же номер у второй команды с телефонией — неоднозначно.
    await _team_with_lead(
        factory, user_id=uid, phone="0675554433", name="Other"
    )
    r = TestClient(create_app()).post(
        hook, data={"callee": "380675554433", "status": "ANSWERED"}
    )
    assert r.json() == {"ok": True, "ignored": "unknown number"}


@pytest.mark.asyncio
async def test_stale_dialing_calls_expire(factory):
    from datetime import datetime, timedelta, timezone

    from leadgen.core.services.sales.telephony.processing import (
        expire_stale_dialing,
    )

    now = datetime.now(timezone.utc)
    async with factory() as session:
        session.add_all(
            [
                Call(
                    provider="ringostat", to_number="1", state="dialing",
                    created_at=now - timedelta(minutes=45),
                ),
                Call(
                    provider="ringostat", to_number="2", state="dialing",
                    created_at=now - timedelta(minutes=5),
                ),
                Call(
                    provider="ringostat", to_number="3", state="completed",
                    created_at=now - timedelta(hours=2),
                ),
            ]
        )
        await session.commit()

    assert await expire_stale_dialing(now) == 1
    async with factory() as session:
        calls = {
            c.to_number: c
            for c in (await session.execute(select(Call))).scalars()
        }
    assert calls["1"].state == "missed" and calls["1"].completed_at
    assert calls["2"].state == "dialing"
    assert calls["3"].state == "completed"


@pytest.mark.asyncio
async def test_start_call_uses_extended_method(monkeypatch):
    """Звоним через /a/v2, а не через простой callback.

    Простому методу нужен виртуальный номер проекта, подключённый как
    "incoming"; расширенный принимает обычные мобильные с обеих сторон.
    """
    sent: dict[str, object] = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json() -> dict[str, object]:
            return {"jsonrpc": "2.0", "id": 1, "result": {"status": "ok"}}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, json=None, **_kw):
            sent["url"] = url
            sent["headers"] = headers
            sent["json"] = json
            return _Resp()

    monkeypatch.setattr(
        "leadgen.core.services.sales.telephony.ringostat.httpx.AsyncClient",
        lambda *a, **k: _Client(),
    )
    provider = RingostatProvider("key", "247726")
    await provider.start_call(
        extension="380680597724", destination="380669841897"
    )

    assert sent["url"].endswith("/a/v2")
    assert sent["headers"]["Auth-key"] == "key"
    params = sent["json"]["params"]
    # caller — клиент, callee — сотрудник; manager_dst=0 — сначала
    # звонит сотруднику, после ответа — клиенту.
    assert params["caller"] == "380669841897"
    assert params["callee"] == "380680597724"
    assert params["manager_dst"] == 0
    assert params["direction"] == "out"
    assert params["projectId"] == "247726"


@pytest.mark.asyncio
async def test_start_call_raises_on_jsonrpc_error(monkeypatch):
    """Отказ приходит в теле при HTTP 200 — он не должен сойти за успех."""

    class _Resp:
        status_code = 200

        @staticmethod
        def json() -> dict[str, object]:
            return {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32602, "message": "Invalid params"},
            }

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(
        "leadgen.core.services.sales.telephony.ringostat.httpx.AsyncClient",
        lambda *a, **k: _Client(),
    )
    with pytest.raises(TelephonyError, match="Invalid params"):
        await RingostatProvider("key").start_call(
            extension="380680597724", destination="380669841897"
        )



@pytest.mark.asyncio
async def test_sip_online_check(monkeypatch):
    """Smart Phone не в сети → звонок не отправляем, а объясняем."""

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return ["seventytimescom_matychyn"]

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None, **_kw):
            assert url.endswith("/sipstatus/online")
            assert headers["Auth-key"] == "key"
            return _Resp()

    monkeypatch.setattr(
        "leadgen.core.services.sales.telephony.ringostat.httpx.AsyncClient",
        lambda *a, **k: _Client(),
    )
    provider = RingostatProvider("key")
    assert await provider.sip_online("seventytimescom_matychyn") is True
    assert await provider.sip_online("seventytimescom_tomachok") is False



def test_ringostat_real_inbound_event_puts_client_first():
    """Тело реального события (30.09): dst — номер проекта, клиент — в
    E164/userfield. Раньше брали dst и клиента не находили."""
    event = RingostatProvider("k").parse_event(
        {
            "call_type": "in",
            "dst": "380736506881",
            "E164": "+380732135997",
            "userfield": "380732135997",
            "connected_with": "seventytimescom_matychyn",
            "disposition": "ANSWERED",
            "billsec": "3",
            "duration": "14",
            "cdr_id": "ua9_-1790775458.2139025",
            "recording_wav": "https://app.ringostat.com/recordings/x.wav?token=t",
        }
    )
    assert event is not None
    assert event.direction == "in"
    assert event.candidates == ("380732135997", "380736506881")
    assert event.to_number == "380732135997"
    assert event.answered and event.talk_sec == 3
    assert event.recording_url.endswith(".wav?token=t")


def test_ringostat_voicemail_is_not_a_conversation():
    event = RingostatProvider("k").parse_event(
        {
            "call_type": "in",
            "dst": "380736506881",
            "E164": "+380736506881",
            "disposition": "VOICEMAIL",
            "billsec": "3",
            "recording_wav": "https://app.ringostat.com/recordings/v.wav",
        }
    )
    assert event is not None
    assert event.answered is False
    assert event.recording_url is None


@pytest.mark.asyncio
async def test_webhook_matches_dialing_call_by_any_number(factory, monkeypatch):
    """Клиент не в dst, а в userfield — звонок из карточки всё равно
    находит свой итог и запись."""
    from leadgen.adapters.web_api import create_app
    from leadgen.core.services.sales.telephony import processing

    async def fake_start(self, *, extension, destination):
        return None

    monkeypatch.setattr(RingostatProvider, "start_call", fake_start)
    scheduled: list[uuid.UUID] = []

    async def fake_schedule(call_id):
        scheduled.append(call_id)

    monkeypatch.setattr(processing, "schedule", fake_schedule)

    client = TestClient(create_app())
    user_id = _register(client, "tel-any@example.test")
    _team_id, lead_id = await _team_with_lead(
        factory, user_id=user_id, phone="+380 66 984 18 97"
    )
    r = client.post(f"/api/v1/leads/{lead_id}/call")
    assert r.status_code == 200, r.text
    call_id = uuid.UUID(r.json()["call_id"])

    r = client.post(
        f"/api/v1/telephony/ringostat/webhook?token={TOKEN}",
        json={
            "call_type": "out",
            "dst": "380736506881",
            "userfield": "380669841897",
            "E164": "+380669841897",
            "disposition": "ANSWERED",
            "billsec": "42",
            "duration": "55",
            "cdr_id": "ua1_-1.1",
            "recording_wav": "https://app.ringostat.com/recordings/a.wav",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}
    assert scheduled == [call_id]
    async with factory() as session:
        call = await session.get(Call, call_id)
        assert call.state == "completed"
        assert call.talk_sec == 42
        assert call.recording_url.endswith("a.wav")


@pytest.mark.asyncio
async def test_sync_pulls_results_from_provider_log(factory, monkeypatch):
    """Webhook на исходящие в кабинете не настроен — итог и запись
    забираем из журнала провайдера. Тела строк — из живого calls/list."""
    from datetime import datetime, timedelta, timezone

    from leadgen.adapters.web_api import create_app
    from leadgen.core.services.sales.telephony import processing, sync

    async def fake_start(self, *, extension, destination):
        return None

    monkeypatch.setattr(RingostatProvider, "start_call", fake_start)
    scheduled: list[uuid.UUID] = []

    async def fake_schedule(call_id):
        scheduled.append(call_id)

    monkeypatch.setattr(processing, "schedule", fake_schedule)

    client = TestClient(create_app())
    user_id = _register(client, "tel-sync@example.test")
    _team_id, lead_id = await _team_with_lead(
        factory, user_id=user_id, phone="+380 66 984 18 97"
    )
    call_id = uuid.UUID(client.post(f"/api/v1/leads/{lead_id}/call").json()["call_id"])

    now = datetime.now(timezone.utc)
    stamp = (now + timedelta(seconds=8)).strftime("%Y-%m-%dT%H:%M:%S+0000")
    direct = (now - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%S+0000")

    async def fake_list(self, since):
        return [
            {   # звонок из Convioo: клиент — в caller, SIP — в dst
                "calldate": stamp,
                "caller": "380669841897",
                "dst": "seventytimescom_matychyn",
                "disposition": "PROPER",
                "billsec": 212,
                "duration": 220,
                "call_type": "out",
                "has_recording": "1",
                "recording": "https://app.ringostat.com/recordings/a.wav?token=t",
                "uniqueid": "ua15_-1.1",
                "connected_with": "seventytimescom_matychyn",
            },
            {   # звонок прямо из Smart Phone: SIP — в caller, клиент — в dst
                "calldate": direct,
                "caller": '"seventytimescom_matychyn" <seventytimescom_matychyn>',
                "dst": "380669841897",
                "disposition": "ANSWERED",
                "billsec": 163,
                "duration": 176,
                "call_type": "out",
                "has_recording": "1",
                "recording": "https://app.ringostat.com/recordings/b.wav?token=t",
                "uniqueid": "ua6_-2.2",
                "connected_with": "380669841897",
            },
        ]

    monkeypatch.setattr(RingostatProvider, "list_calls", fake_list)

    assert await sync.sync_ringostat_calls() == 2
    async with factory() as session:
        call = await session.get(Call, call_id)
        assert call.state == "completed"
        assert call.talk_sec == 212
        assert call.provider_call_id == "ua15_-1.1"
        assert call.recording_url.endswith("a.wav?token=t")
        others = (
            (await session.execute(select(Call).where(Call.id != call_id)))
            .scalars()
            .all()
        )
        assert len(others) == 1 and others[0].talk_sec == 163
        # История идёт по времени разговора, а не загрузки.
        assert others[0].created_at.replace(tzinfo=None) < call.created_at.replace(tzinfo=None)
    assert call_id in scheduled and len(scheduled) == 2
    # Повторный проход ничего не дублирует.
    assert await sync.sync_ringostat_calls() == 0



@pytest.mark.asyncio
async def test_sync_does_not_close_a_call_in_progress(factory, monkeypatch):
    """Пока идёт разговор, журнал показывает строку с нулями. Её нельзя
    принимать за недозвон; а если так уже случилось — итог дополняется,
    когда появляются разговор и запись (звонок 05.10, 7 минут)."""
    from datetime import datetime, timedelta, timezone

    from leadgen.adapters.web_api import create_app
    from leadgen.core.services.sales.telephony import processing, sync

    async def fake_start(self, *, extension, destination):
        return None

    monkeypatch.setattr(RingostatProvider, "start_call", fake_start)
    scheduled: list[uuid.UUID] = []

    async def fake_schedule(call_id):
        scheduled.append(call_id)

    monkeypatch.setattr(processing, "schedule", fake_schedule)

    client = TestClient(create_app())
    user_id = _register(client, "tel-live@example.test")
    _team_id, lead_id = await _team_with_lead(
        factory, user_id=user_id, phone="+380 66 984 18 97"
    )
    call_id = uuid.UUID(client.post(f"/api/v1/leads/{lead_id}/call").json()["call_id"])
    now = datetime.now(timezone.utc)
    stamp = (now + timedelta(seconds=9)).strftime("%Y-%m-%dT%H:%M:%S+0000")
    row = {
        "calldate": stamp,
        "caller": "380669841897",
        "dst": "seventytimescom_matychyn",
        "disposition": "NO ANSWER",
        "billsec": 0,
        "duration": 0,
        "call_type": "out",
        "has_recording": "0",
        "recording": "",
        "uniqueid": "ua10_-9.9",
    }

    async def fake_list(self, since):
        return [dict(row)]

    monkeypatch.setattr(RingostatProvider, "list_calls", fake_list)

    # Разговор идёт: строка без разговора — не трогаем.
    assert await sync.sync_ringostat_calls() == 0
    async with factory() as session:
        assert (await session.get(Call, call_id)).state == "dialing"

    # Допустим, итог всё же сняли рано (так было до исправления).
    async with factory() as session:
        call = await session.get(Call, call_id)
        call.state = "missed"
        call.provider_call_id = "ua10_-9.9"
        await session.commit()

    row.update(
        disposition="REPEATED",
        billsec=425,
        duration=433,
        has_recording="1",
        recording="https://app.ringostat.com/recordings/big.wav?token=t",
    )
    assert await sync.sync_ringostat_calls() == 1
    async with factory() as session:
        call = await session.get(Call, call_id)
        assert call.state == "completed"
        assert call.talk_sec == 425
        assert call.recording_url.endswith("big.wav?token=t")
    assert scheduled == [call_id]
    assert await sync.sync_ringostat_calls() == 0


def test_segments_respect_rep_channel():
    """При звонке из карточки первая дорожка записи — клиент."""
    stt = {
        "transcripts": [
            {"channel_index": 0, "words": [{"text": "Алло, кто это?", "start": 0.5, "type": "word"}]},
            {"channel_index": 1, "words": [{"text": "Добрый день, Роман.", "start": 0.1, "type": "word"}]},
        ]
    }
    default = _segments(stt)
    assert [s["speaker"] for s in default] == ["client", "rep"]
    flipped = _segments(stt, rep_channel=1)
    assert [s["speaker"] for s in flipped] == ["rep", "client"]
    assert flipped[0]["text"] == "Добрый день, Роман."


def test_ringostat_rep_is_on_second_channel():
    """Живые записи: клиент на первой дорожке, SIP сотрудника — на
    второй, и при звонке из карточки, и при наборе из Smart Phone."""
    from leadgen.core.services.sales.telephony import rep_channel_for

    p = RingostatProvider("k")
    callback = p.parse_event(
        {"call_type": "out", "caller": "380669841897", "dst": "seventytimescom_matychyn",
         "disposition": "PROPER", "billsec": 212, "uniqueid": "a"}
    )
    direct = p.parse_event(
        {"call_type": "out", "caller": '"sip" <seventytimescom_matychyn>', "dst": "380669841897",
         "disposition": "ANSWERED", "billsec": 163, "uniqueid": "b"}
    )
    assert rep_channel_for(callback, "380669841897") == 1
    assert rep_channel_for(direct, "380669841897") == 1
