"""Unified Inbox (Wave 3) — sync service + API + reply path.

No real network: provider list/get/send calls are monkeypatched. The
DB is an in-memory sqlite engine wired into ``leadgen.db.session`` the
same way the deliverability tests do it.
"""

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
from sqlalchemy.pool import StaticPool

from leadgen.core.services.inbox_sync import (
    SyncResult,
    has_read_scope,
    sync_inbox_for_user,
)
from leadgen.core.services.secrets_vault import encrypt
from leadgen.db import session as db_session_mod
from leadgen.db.models import (
    Base,
    EmailMessage,
    Lead,
    OAuthCredential,
    SearchQuery,
)
from leadgen.utils import rate_limit as rate_limit_mod

GMAIL_READ = (
    "https://www.googleapis.com/auth/gmail.send "
    "https://www.googleapis.com/auth/gmail.readonly"
)
GMAIL_SEND_ONLY = "https://www.googleapis.com/auth/gmail.send"


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


def _client() -> TestClient:
    from leadgen.adapters.web_api import create_app

    return TestClient(create_app())


def _register(client: TestClient, email: str) -> int:
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "In",
            "last_name": "Box",
            "email": email,
            "password": "correcthorse123",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


async def _add_gmail_cred(maker, *, user_id: int, scope: str) -> None:
    async with maker() as session:
        session.add(
            OAuthCredential(
                user_id=user_id,
                provider="gmail",
                access_token_ciphertext=encrypt("access-token"),
                refresh_token_ciphertext=encrypt("refresh-token"),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                scope=scope,
                account_email="me@example.test",
            )
        )
        await session.commit()


async def _seed_lead(
    maker, *, user_id: int, contact_email: str | None
) -> uuid.UUID:
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


def _fake_gmail_messages() -> dict[str, dict]:
    """Two messages in one thread: one inbound, one outbound."""
    sent_at = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    return {
        "m1": {
            "provider_message_id": "m1",
            "thread_id": "t1",
            "from_email": "jane@lead.test",
            "to_email": "me@example.test",
            "subject": "Interested",
            "snippet": "Hi there",
            "body_text": "Hi there",
            "body_html": "<p>Hi there</p>",
            "message_sent_at": sent_at,
            "headers": {
                "Message-ID": "<jane-1@lead.test>",
                "In-Reply-To": "",
                "References": "",
            },
            "direction": "inbound",
            "is_read": False,
        },
        "m2": {
            "provider_message_id": "m2",
            "thread_id": "t1",
            "from_email": "me@example.test",
            "to_email": "jane@lead.test",
            "subject": "Re: Interested",
            "snippet": "Thanks",
            "body_text": "Thanks",
            "body_html": None,
            "message_sent_at": sent_at + timedelta(minutes=5),
            "headers": {
                "Message-ID": "<me-1@example.test>",
                "In-Reply-To": "<jane-1@lead.test>",
                "References": "<jane-1@lead.test>",
            },
            "direction": "outbound",
            "is_read": True,
        },
    }


def _patch_gmail_read(monkeypatch):
    msgs = _fake_gmail_messages()

    async def _list_ids(access_token, *, after_epoch=None, max_results=100):
        return list(msgs.keys())

    async def _get(access_token, msg_id, **_):
        return dict(msgs[msg_id])

    monkeypatch.setattr(
        "leadgen.integrations.gmail.list_message_ids", _list_ids
    )
    monkeypatch.setattr("leadgen.integrations.gmail.get_message", _get)
    return msgs


# ── has_read_scope ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_has_read_scope_true_false():
    gmail_yes = OAuthCredential(
        user_id=1, provider="gmail", access_token_ciphertext="x",
        scope=GMAIL_READ,
    )
    gmail_no = OAuthCredential(
        user_id=1, provider="gmail", access_token_ciphertext="x",
        scope=GMAIL_SEND_ONLY,
    )
    outlook_yes = OAuthCredential(
        user_id=1, provider="outlook", access_token_ciphertext="x",
        scope="Mail.Send Mail.Read User.Read",
    )
    outlook_no = OAuthCredential(
        user_id=1, provider="outlook", access_token_ciphertext="x",
        scope="Mail.Send User.Read",
    )
    assert await has_read_scope(gmail_yes) is True
    assert await has_read_scope(gmail_no) is False
    assert await has_read_scope(outlook_yes) is True
    assert await has_read_scope(outlook_no) is False
    assert await has_read_scope(None) is False


# ── sync service ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sync_needs_reconnect_without_read_scope(maker, monkeypatch):
    client = _client()
    uid = _register(client, "sync-noscope@example.test")
    await _add_gmail_cred(maker, user_id=uid, scope=GMAIL_SEND_ONLY)

    async with maker() as session:
        result = await sync_inbox_for_user(session, uid)
    assert result == SyncResult(synced=0, needs_reconnect=True)


@pytest.mark.asyncio
async def test_sync_upserts_idempotently_and_matches_lead(
    maker, monkeypatch
):
    client = _client()
    uid = _register(client, "sync-up@example.test")
    await _add_gmail_cred(maker, user_id=uid, scope=GMAIL_READ)
    lead_id = await _seed_lead(
        maker, user_id=uid, contact_email="jane@lead.test"
    )
    _patch_gmail_read(monkeypatch)

    async with maker() as session:
        first = await sync_inbox_for_user(session, uid)
    assert first.needs_reconnect is False
    assert first.synced == 2

    async with maker() as session:
        rows = (
            await session.execute(EmailMessage.__table__.select())
        ).fetchall()
    assert len(rows) == 2

    # The inbound message's counterpart (jane@lead.test) matched the lead.
    import sqlalchemy

    async with maker() as session:
        msgs = (
            await session.execute(sqlalchemy.select(EmailMessage))
        ).scalars().all()
    matched = [m for m in msgs if m.lead_id is not None]
    assert matched, "expected at least one message matched to the lead"
    assert all(m.lead_id == lead_id for m in matched)

    # Re-run: no duplicate rows (idempotent upsert on unique key).
    async with maker() as session:
        await sync_inbox_for_user(session, uid)
    async with maker() as session:
        rows2 = (
            await session.execute(EmailMessage.__table__.select())
        ).fetchall()
    assert len(rows2) == 2


# ── API: threads ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_threads_groups_aggregates_and_reconnect_flag(
    maker, monkeypatch
):
    client = _client()
    uid = _register(client, "threads-a@example.test")
    await _add_gmail_cred(maker, user_id=uid, scope=GMAIL_READ)
    _patch_gmail_read(monkeypatch)

    r = client.post("/api/v1/inbox/sync")
    assert r.status_code == 200, r.text
    assert r.json() == {"synced": 2, "needs_reconnect": False}

    r = client.get("/api/v1/inbox/threads")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["connected"] is True
    assert body["needs_reconnect"] is False
    assert body["provider"] == "gmail"
    assert len(body["threads"]) == 1
    t = body["threads"][0]
    assert t["thread_id"] == "t1"
    assert t["message_count"] == 2
    assert t["unread_count"] == 1
    assert t["counterpart_email"] == "jane@lead.test"


@pytest.mark.asyncio
async def test_threads_needs_reconnect_when_send_only(maker, monkeypatch):
    client = _client()
    uid = _register(client, "threads-reconnect@example.test")
    await _add_gmail_cred(maker, user_id=uid, scope=GMAIL_SEND_ONLY)

    r = client.get("/api/v1/inbox/threads")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["connected"] is True
    assert body["needs_reconnect"] is True


@pytest.mark.asyncio
async def test_thread_ownership_404(maker, monkeypatch):
    client_a = _client()
    client_b = _client()
    uid_a = _register(client_a, "own-a@example.test")
    _register(client_b, "own-b@example.test")
    await _add_gmail_cred(maker, user_id=uid_a, scope=GMAIL_READ)
    _patch_gmail_read(monkeypatch)

    assert client_a.post("/api/v1/inbox/sync").status_code == 200

    # Owner can read.
    ra = client_a.get("/api/v1/inbox/threads/t1")
    assert ra.status_code == 200, ra.text
    assert len(ra.json()["messages"]) == 2

    # Stranger gets 404 — never 403.
    rb = client_b.get("/api/v1/inbox/threads/t1")
    assert rb.status_code == 404


@pytest.mark.asyncio
async def test_get_thread_marks_inbound_read(maker, monkeypatch):
    client = _client()
    uid = _register(client, "markread@example.test")
    await _add_gmail_cred(maker, user_id=uid, scope=GMAIL_READ)
    _patch_gmail_read(monkeypatch)
    assert client.post("/api/v1/inbox/sync").status_code == 200

    # Before: one unread inbound.
    r = client.get("/api/v1/inbox/threads")
    assert r.json()["threads"][0]["unread_count"] == 1

    # Reading the thread marks inbound read.
    assert client.get("/api/v1/inbox/threads/t1").status_code == 200

    r = client.get("/api/v1/inbox/threads")
    assert r.json()["threads"][0]["unread_count"] == 0

    import sqlalchemy

    async with maker() as session:
        msgs = (
            await session.execute(sqlalchemy.select(EmailMessage))
        ).scalars().all()
    inbound = [m for m in msgs if m.direction == "inbound"]
    assert all(m.is_read for m in inbound)


# ── API: reply ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reply_gmail_threads_and_stores_outbound(maker, monkeypatch):
    client = _client()
    uid = _register(client, "reply-gmail@example.test")
    await _add_gmail_cred(maker, user_id=uid, scope=GMAIL_READ)
    await _seed_lead(maker, user_id=uid, contact_email="jane@lead.test")
    _patch_gmail_read(monkeypatch)
    assert client.post("/api/v1/inbox/sync").status_code == 200

    captured: dict = {}

    def _fake_build(**kwargs):
        captured.update(kwargs)
        return "RAW"

    async def _fake_send(*, access_token, raw_message, thread_id=None, **_):
        captured["thread_id"] = thread_id
        captured["raw_message"] = raw_message
        return {"id": "sent-1", "threadId": "t1"}

    monkeypatch.setattr(
        "leadgen.integrations.gmail.build_raw_message", _fake_build
    )
    monkeypatch.setattr(
        "leadgen.integrations.gmail.send_message", _fake_send
    )

    r = client.post(
        "/api/v1/inbox/threads/t1/reply",
        json={"body": "Thanks for reaching out!"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "message_id": "sent-1"}

    # Threaded via threadId + In-Reply-To to the latest inbound message.
    assert captured["thread_id"] == "t1"
    assert captured["in_reply_to"] == "<jane-1@lead.test>"
    assert captured["to_addr"] == "jane@lead.test"

    # Outbound row stored locally (2 synced + 1 reply == 3).
    import sqlalchemy

    async with maker() as session:
        msgs = (
            await session.execute(sqlalchemy.select(EmailMessage))
        ).scalars().all()
    outbound = [
        m for m in msgs if m.provider_message_id == "sent-1"
    ]
    assert len(outbound) == 1
    assert outbound[0].direction == "outbound"
    assert outbound[0].to_email == "jane@lead.test"


@pytest.mark.asyncio
async def test_reply_unknown_thread_404(maker, monkeypatch):
    client = _client()
    uid = _register(client, "reply-404@example.test")
    await _add_gmail_cred(maker, user_id=uid, scope=GMAIL_READ)

    r = client.post(
        "/api/v1/inbox/threads/nope/reply", json={"body": "hi"}
    )
    assert r.status_code == 404
