"""Deliverability API + send-path enforcement.

* GET /api/v1/deliverability/status returns the documented keys.
* POST /api/v1/leads/{id}/verify-email enforces ownership (B -> 404)
  and persists the verdict.
* send_sequence_step blocks invalid emails and defers past the cap.

Resolvers are patched / verification disabled so no real DNS happens.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from leadgen.db import session as db_session_mod
from leadgen.db.models import (
    Base,
    EmailSequence,
    Lead,
    SearchQuery,
    SequenceEnrollment,
)
from leadgen.utils import rate_limit as rate_limit_mod


@pytest_asyncio.fixture
async def db_engine():
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
def maker(monkeypatch, db_engine):
    m = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr(db_session_mod, "_engine", db_engine)
    monkeypatch.setattr(db_session_mod, "_session_factory", m)
    return m


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    for name in ("register_limiter", "login_limiter"):
        getattr(rate_limit_mod, name)._events.clear()
    yield


@pytest.fixture(autouse=True)
def _disable_dns(monkeypatch):
    # No network: the verifier returns syntax-only "unknown". Individual
    # tests that need a specific verdict patch verify_email directly.
    from leadgen.config import get_settings

    monkeypatch.setattr(
        get_settings(), "email_verification_enabled", False
    )
    yield


def _client() -> TestClient:
    from leadgen.adapters.web_api import create_app

    return TestClient(create_app())


def _register(client: TestClient, email: str) -> int:
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Del",
            "last_name": "Tester",
            "email": email,
            "password": "correcthorse123",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


async def _seed_lead(maker, *, user_id: int, contact_email: str | None) -> uuid.UUID:
    async with maker() as session:
        sq = SearchQuery(
            id=uuid.uuid4(),
            user_id=user_id,
            team_id=None,
            niche="roofing",
            region="NY",
            status="done",
            source="web",
        )
        session.add(sq)
        await session.flush()
        lead = Lead(
            id=uuid.uuid4(),
            query_id=sq.id,
            name="Acme Roofing",
            source="google_places",
            source_id=f"place-{uuid.uuid4()}",
            lead_status="new",
            contact_email=contact_email,
        )
        session.add(lead)
        await session.commit()
        return lead.id


@pytest.mark.asyncio
async def test_status_endpoint_returns_documented_keys(maker):
    client = _client()
    _register(client, "del-status@example.test")
    r = client.get("/api/v1/deliverability/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {
        "connected",
        "provider",
        "domain",
        "warmup_day",
        "daily_cap",
        "sent_today",
        "remaining",
        "spf",
        "dmarc",
    }
    assert body["connected"] is False
    assert set(body["spf"].keys()) == {"present", "record"}
    assert set(body["dmarc"].keys()) == {"present", "policy"}


@pytest.mark.asyncio
async def test_verify_email_endpoint_ownership_and_update(maker, monkeypatch):
    client_a = _client()
    client_b = _client()
    user_a = _register(client_a, "del-a@example.test")
    _register(client_b, "del-b@example.test")

    lead_id = await _seed_lead(
        maker, user_id=user_a, contact_email="jane@example.com"
    )

    # Force a deterministic verdict regardless of DNS state.
    from leadgen.core.services.email_verification import EmailVerification

    async def _fake_verify(_email):
        return EmailVerification(status="valid", reason="mx ok", mx_host="mx")

    monkeypatch.setattr(
        "leadgen.adapters.web_api.routes.deliverability.verify_email",
        _fake_verify,
    )

    # Stranger gets 404 — never 403.
    rb = client_b.post(f"/api/v1/leads/{lead_id}/verify-email")
    assert rb.status_code == 404

    # Owner re-verifies and the verdict persists.
    ra = client_a.post(f"/api/v1/leads/{lead_id}/verify-email")
    assert ra.status_code == 200, ra.text
    body = ra.json()
    assert body["contact_email"] == "jane@example.com"
    assert body["email_status"] == "valid"
    assert body["email_checked_at"] is not None

    async with maker() as session:
        lead = await session.get(Lead, lead_id)
        assert lead.email_status == "valid"


# ── send-path enforcement ───────────────────────────────────────────────


async def _enroll(maker, *, user_id: int, lead_id: uuid.UUID) -> str:
    async with maker() as session:
        seq = EmailSequence(
            id=uuid.uuid4(),
            user_id=user_id,
            name="Test seq",
            steps=[{"day": 0, "subject": "Hi {{name}}", "body": "Hello"}],
        )
        session.add(seq)
        await session.flush()
        enr = SequenceEnrollment(
            id=uuid.uuid4(),
            sequence_id=seq.id,
            lead_id=lead_id,
            user_id=user_id,
            current_step=0,
            status="active",
        )
        session.add(enr)
        await session.commit()
        return str(enr.id)


@pytest.mark.asyncio
async def test_send_path_skips_invalid_email(maker, monkeypatch):
    client = _client()
    user_id = _register(client, "del-send@example.test")
    lead_id = await _seed_lead(
        maker, user_id=user_id, contact_email="bad@nope.example"
    )
    enrollment_id = await _enroll(maker, user_id=user_id, lead_id=lead_id)

    from leadgen.core.services.email_verification import EmailVerification

    async def _invalid(_email):
        return EmailVerification(status="invalid", reason="no mail", mx_host=None)

    monkeypatch.setattr(
        "leadgen.core.services.email_verification.verify_email", _invalid
    )

    sent = {"called": False}

    async def _no_send(**_kw):
        sent["called"] = True

    monkeypatch.setattr(
        "leadgen.core.services.email_sender.send_email", _no_send
    )

    from leadgen.queue.worker import send_sequence_step

    result = await send_sequence_step({}, enrollment_id)
    assert result == {"skipped": "invalid email"}
    assert sent["called"] is False

    async with maker() as session:
        enr = await session.get(SequenceEnrollment, uuid.UUID(enrollment_id))
        assert enr.status == "paused"


@pytest.mark.asyncio
async def test_send_path_defers_past_daily_cap(maker, monkeypatch):
    client = _client()
    user_id = _register(client, "del-cap@example.test")
    lead_id = await _seed_lead(
        maker, user_id=user_id, contact_email="jane@example.com"
    )
    enrollment_id = await _enroll(maker, user_id=user_id, lead_id=lead_id)

    from leadgen.core.services.email_verification import EmailVerification

    async def _valid(_email):
        return EmailVerification(status="valid", reason="mx ok", mx_host="mx")

    monkeypatch.setattr(
        "leadgen.core.services.email_verification.verify_email", _valid
    )

    # Force the reservation to report the cap is exhausted.
    from leadgen.core.services.send_quota import ReserveResult

    async def _blocked(_session, _user_id):
        return ReserveResult(allowed=False, cap=20, sent=20)

    monkeypatch.setattr(
        "leadgen.core.services.send_quota.check_and_reserve_send", _blocked
    )

    sent = {"called": False}

    async def _no_send(**_kw):
        sent["called"] = True

    monkeypatch.setattr(
        "leadgen.core.services.email_sender.send_email", _no_send
    )

    from leadgen.queue.worker import send_sequence_step

    result = await send_sequence_step({}, enrollment_id)
    assert result == {"skipped": "daily cap"}
    assert sent["called"] is False

    async with maker() as session:
        enr = await session.get(SequenceEnrollment, uuid.UUID(enrollment_id))
        assert enr.next_send_at is not None
