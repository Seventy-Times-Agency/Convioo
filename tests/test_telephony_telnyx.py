"""Telnyx: звонок из браузера, токен WebRTC, три события webhook.

HTTP к Telnyx подменён — проверяем свою логику: выдачу токена с
credential на человека, строку звонка в режиме браузера, подпись
webhook, привязку ответа/итога/записи к звонку и запуск расшифровки.
"""

from __future__ import annotations

import base64
import json
import uuid

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.core.services.sales.telephony.telnyx import TelnyxProvider
from leadgen.db.models import (
    Base,
    Call,
    Lead,
    SearchQuery,
    Team,
    TeamMembership,
    User,
)

TOKEN = "hook-secret-123"
CALLER = "+13055550100"


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
    monkeypatch.setenv("TELEPHONY_PROVIDER", "")
    monkeypatch.setenv("TELEPHONY_ROUTES", "380:ringostat,1:telnyx")
    monkeypatch.setenv("RINGOSTAT_AUTH_KEY", "rs-key")
    monkeypatch.setenv("TELNYX_API_KEY", "tx-key")
    monkeypatch.setenv("TELNYX_CONNECTION_ID", "conn-1")
    monkeypatch.setenv("TELNYX_CALLER_ID", CALLER)
    monkeypatch.setenv("TELNYX_PUBLIC_KEY", "")
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


async def _team_with_lead(factory, *, user_id, phone):
    team_id = uuid.uuid4()
    async with factory() as session:
        session.add(Team(id=team_id, name="US"))
        session.add(
            TeamMembership(team_id=team_id, user_id=user_id, role="sales")
        )
        q = SearchQuery(
            id=uuid.uuid4(), user_id=user_id, team_id=team_id,
            niche="n", region="r", status="done", source="web",
        )
        session.add(q)
        await session.flush()
        lead = Lead(
            query_id=q.id, name="Roofer", source="g",
            source_id=str(uuid.uuid4()), phone=phone,
            owner_user_id=user_id,
        )
        session.add(lead)
        await session.commit()
        return team_id, lead.id


def _event(event_type: str, **payload) -> dict:
    return {"data": {"event_type": event_type, "payload": payload}}


# ── разбор событий ────────────────────────────────────────────────────


def test_parse_events_from_browser_call():
    p = TelnyxProvider("k", "conn", CALLER)
    answered = p.parse_event(
        _event(
            "call.answered",
            call_control_id="cc-1",
            call_session_id="sess-1",
            from_="sip:convioo-u5@sip.telnyx.com",
            to="+13055551234",
        )
    )
    assert answered is not None
    assert answered.kind == "answered"
    assert answered.call_control_id == "cc-1"
    assert answered.provider_call_id == "sess-1"
    assert answered.to_number == "13055551234"

    hangup = p.parse_event(
        _event(
            "call.hangup",
            call_session_id="sess-1",
            to="+13055551234",
            hangup_cause="normal_clearing",
            start_time="2026-10-03T10:00:00Z",
            end_time="2026-10-03T10:02:30Z",
        )
    )
    assert hangup is not None
    assert hangup.kind == "result"
    assert hangup.answered is True
    assert hangup.duration_sec == 150
    assert hangup.talk_sec == 150

    missed = p.parse_event(
        _event("call.hangup", call_session_id="s2", to="+13055551234", hangup_cause="timeout")
    )
    assert missed is not None and missed.answered is False

    rec = p.parse_event(
        _event(
            "call.recording.saved",
            call_session_id="sess-1",
            recording_urls={"mp3": "https://rec.telnyx.com/a.mp3"},
        )
    )
    assert rec is not None and rec.kind == "recording"
    assert rec.recording_url == "https://rec.telnyx.com/a.mp3"

    assert p.parse_event(_event("call.initiated", to="+13055551234")) is None


def test_webhook_signature_is_verified():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv = Ed25519PrivateKey.generate()
    pub_b64 = base64.b64encode(
        priv.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
    ).decode()
    p = TelnyxProvider("k", "conn", CALLER, public_key=pub_b64)
    body = b'{"data":{"event_type":"call.hangup"}}'
    sig = base64.b64encode(priv.sign(b"1700000000|" + body)).decode()
    assert p.verify_signature(body, sig, "1700000000")
    assert not p.verify_signature(body + b" ", sig, "1700000000")
    assert not p.verify_signature(body, sig, "1700000001")
    # Без ключа подпись не требуется — защищает токен в адресе.
    assert TelnyxProvider("k", "conn", CALLER).verify_signature(body, None, None)


# ── API ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_browser_call_token_and_webhook_flow(factory, monkeypatch):
    from leadgen.adapters.web_api import create_app
    from leadgen.core.services.sales.telephony import processing

    posted: list[tuple[str, dict | None]] = []

    async def fake_post(self, path, body=None):
        posted.append((path, body))
        if path == "/telephony_credentials":
            return {"data": {"id": "cred-42"}}
        if path.endswith("/token"):
            return {"text": "jwt-token-xyz"}
        return {}

    monkeypatch.setattr(TelnyxProvider, "_post", fake_post)

    scheduled: list[uuid.UUID] = []

    async def fake_schedule(call_id):
        scheduled.append(call_id)

    monkeypatch.setattr(processing, "schedule", fake_schedule)

    client = TestClient(create_app())
    user_id = _register(client, "tx-rep@example.test")
    team_id, lead_id = await _team_with_lead(
        factory, user_id=user_id, phone="(305) 555-1234"
    )

    # Статус: режим браузера, номер определителя, вебхук для Telnyx.
    r = client.get(f"/api/v1/teams/{team_id}/telephony")
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "browser"
    assert r.json()["caller_number"] == CALLER

    # Токен: credential создаётся один раз и запоминается у пользователя.
    r = client.post("/api/v1/telephony/webrtc-token", json={"team_id": str(team_id)})
    assert r.status_code == 200, r.text
    assert r.json()["token"] == "jwt-token-xyz"
    assert r.json()["provider"] == "telnyx"
    r = client.post("/api/v1/telephony/webrtc-token", json={"team_id": str(team_id)})
    assert r.status_code == 200
    assert [p for p, _b in posted if p == "/telephony_credentials"] == [
        "/telephony_credentials"
    ]
    assert posted[0][1] == {"connection_id": "conn-1", "name": f"convioo-u{user_id}"}
    async with factory() as session:
        u = await session.get(User, user_id)
        assert u.webrtc_credential_id == "cred-42"

    # Звонок в режиме браузера: строка «набор» без номера сотрудника.
    r = client.post(f"/api/v1/leads/{lead_id}/call")
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "browser"
    assert r.json()["destination"] == "+13055551234"
    call_id = uuid.UUID(r.json()["call_id"])

    hook = f"/api/v1/telephony/telnyx/webhook?token={TOKEN}"
    # Соединились → привязали сессию, попросили запись.
    r = client.post(
        hook,
        json=_event(
            "call.answered",
            call_control_id="cc-9",
            call_session_id="sess-9",
            to="+13055551234",
        ),
    )
    assert r.status_code == 200, r.text
    assert ("/calls/cc-9/actions/record_start", {"format": "mp3", "channels": "dual"}) in posted

    # Итог → completed с длительностью.
    r = client.post(
        hook,
        json=_event(
            "call.hangup",
            call_session_id="sess-9",
            to="+13055551234",
            hangup_cause="normal_clearing",
            start_time="2026-10-03T10:00:00Z",
            end_time="2026-10-03T10:01:00Z",
        ),
    )
    assert r.status_code == 200
    async with factory() as session:
        call = await session.get(Call, call_id)
        assert call.state == "completed"
        assert call.provider_call_id == "sess-9"
        assert call.talk_sec == 60

    # Запись приходит позже → ссылка сохранена, расшифровка запущена.
    r = client.post(
        hook,
        json=_event(
            "call.recording.saved",
            call_session_id="sess-9",
            recording_urls={"mp3": "https://rec.telnyx.com/9.mp3"},
        ),
    )
    assert r.status_code == 200
    assert scheduled == [call_id]
    async with factory() as session:
        call = await session.get(Call, call_id)
        assert call.recording_url == "https://rec.telnyx.com/9.mp3"

    # Повтор записи — не второй раз.
    r = client.post(
        hook,
        json=_event(
            "call.recording.saved",
            call_session_id="sess-9",
            recording_urls={"mp3": "https://rec.telnyx.com/9.mp3"},
        ),
    )
    assert r.json().get("ignored") == "duplicate"
    assert scheduled == [call_id]


@pytest.mark.asyncio
async def test_refused_recording_blocks_record_start(factory, monkeypatch):
    from leadgen.adapters.web_api import create_app

    posted: list[str] = []

    async def fake_post(self, path, body=None):
        posted.append(path)
        return {}

    monkeypatch.setattr(TelnyxProvider, "_post", fake_post)
    client = TestClient(create_app())
    user_id = _register(client, "tx-rep2@example.test")
    _team_id, lead_id = await _team_with_lead(
        factory, user_id=user_id, phone="+1 305 555 0199"
    )
    call_id = client.post(f"/api/v1/leads/{lead_id}/call").json()["call_id"]
    r = client.post(f"/api/v1/calls/{call_id}/consent", json={"allowed": False})
    assert r.status_code == 200
    r = client.post(
        f"/api/v1/telephony/telnyx/webhook?token={TOKEN}",
        json=_event(
            "call.answered", call_control_id="cc-2", call_session_id="s-2",
            to="+13055550199",
        ),
    )
    assert r.status_code == 200
    assert not any(p.endswith("record_start") for p in posted)


@pytest.mark.asyncio
async def test_webhook_rejects_bad_signature(factory, monkeypatch):
    from leadgen.adapters.web_api import create_app
    from leadgen.config import get_settings

    monkeypatch.setenv(
        "TELNYX_PUBLIC_KEY", base64.b64encode(b"\x00" * 32).decode()
    )
    get_settings.cache_clear()
    client = TestClient(create_app())
    r = client.post(
        f"/api/v1/telephony/telnyx/webhook?token={TOKEN}",
        content=json.dumps(_event("call.hangup", to="+13055551234")),
        headers={
            "content-type": "application/json",
            "telnyx-timestamp": "1",
            "telnyx-signature-ed25519": base64.b64encode(b"\x00" * 64).decode(),
        },
    )
    assert r.status_code == 403


def test_region_route_picks_telnyx_for_us(factory):
    from leadgen.core.services.sales import telephony as tel

    assert tel.get_provider_for("+13055551234").name == "telnyx"
    assert tel.get_provider_for("+380671234567").name == "ringostat"
    assert tel.browser_provider().name == "telnyx"
    assert sorted(tel.enabled_providers()) == ["ringostat", "telnyx"]
