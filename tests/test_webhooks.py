"""Outbound webhook subscriptions: signing, CRUD, dispatch, auto-disable."""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.core.services import webhooks as webhook_svc
from leadgen.core.services.webhooks import (
    MAX_CONSECUTIVE_FAILURES,
    SIGNATURE_HEADER,
    emit_event_sync,
    sign_body,
)
from leadgen.db import session as db_session_mod
from leadgen.db.models import Base, Webhook
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


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    for name in (
        "login_limiter",
        "register_limiter",
        "forgot_password_limiter",
        "forgot_email_limiter",
        "reset_password_limiter",
        "resend_verification_limiter",
        "search_user_limiter",
        "search_team_limiter",
        "search_ip_limiter",
        "assistant_user_limiter",
        "assistant_team_limiter",
    ):
        getattr(rate_limit_mod, name)._events.clear()
    yield


@pytest.fixture
def client(patched_session_factory):
    from leadgen.adapters.web_api import create_app

    return TestClient(create_app())


def _register(client: TestClient, email: str = "hooks@example.test") -> int:
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Hook",
            "last_name": "Owner",
            "email": email,
            "password": "correcthorse123",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


def test_sign_body_is_hmac_sha256():
    body = b'{"event":"x"}'
    sig = sign_body("supersecret", body)
    expected = hmac.new(
        b"supersecret", body, hashlib.sha256
    ).hexdigest()
    assert sig == f"sha256={expected}"


def test_create_list_update_delete_webhook(client: TestClient):
    _register(client)
    # Create — secret is exposed exactly once.
    r = client.post(
        "/api/v1/webhooks",
        json={
            "target_url": "https://hooks.example.test/inbox",
            "event_types": ["lead.created", "search.finished"],
            "description": "primary",
        },
    )
    assert r.status_code == 200, r.text
    created = r.json()
    assert created["secret"]
    assert created["secret_preview"].startswith(created["secret"][:4])
    webhook_id = created["id"]

    # List — secret is masked.
    r = client.get("/api/v1/webhooks")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert "secret" not in items[0]
    assert items[0]["secret_preview"] == created["secret_preview"]

    # Update — toggle off, change events.
    r = client.patch(
        f"/api/v1/webhooks/{webhook_id}",
        json={"active": False, "event_types": ["lead.status_changed"]},
    )
    assert r.status_code == 200
    assert r.json()["active"] is False
    assert r.json()["event_types"] == ["lead.status_changed"]

    # Delete.
    r = client.delete(f"/api/v1/webhooks/{webhook_id}")
    assert r.status_code == 200
    assert client.get("/api/v1/webhooks").json()["items"] == []


def test_create_rejects_bad_url_and_unknown_events(client: TestClient):
    _register(client)
    # Bad scheme.
    r = client.post(
        "/api/v1/webhooks",
        json={
            "target_url": "ftp://nope.example.test/x",
            "event_types": ["lead.created"],
        },
    )
    assert r.status_code == 400

    # Unknown event.
    r = client.post(
        "/api/v1/webhooks",
        json={
            "target_url": "https://ok.example.test/x",
            "event_types": ["lead.created", "lead.exploded"],
        },
    )
    assert r.status_code == 400


def test_only_owner_sees_their_webhooks(
    client: TestClient, patched_session_factory
):
    _register(client, email="alice@example.test")
    client.post(
        "/api/v1/webhooks",
        json={
            "target_url": "https://hooks.example.test/alice",
            "event_types": ["lead.created"],
        },
    )
    # Switch session to a different user.
    client.cookies.clear()
    _register(client, email="bob@example.test")
    items = client.get("/api/v1/webhooks").json()["items"]
    assert items == []


@pytest.mark.asyncio
async def test_dispatch_signs_body_and_records_success(
    client: TestClient, patched_session_factory, monkeypatch
):
    user_id = _register(client)
    # Persist a webhook directly so we control the secret.
    secret = "test-secret-abc"
    async with patched_session_factory() as s:
        hook = Webhook(
            user_id=user_id,
            target_url="https://hooks.example.test/inbox",
            secret=secret,
            event_types=["lead.created"],
            description="t",
            active=True,
        )
        s.add(hook)
        await s.commit()
        await s.refresh(hook)
        hook_id = hook.id

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(webhook_svc.httpx, "AsyncClient", fake_client)

    await emit_event_sync(
        user_id,
        "lead.created",
        {"hello": "world"},
        session_factory_override=patched_session_factory,
    )

    assert captured["url"] == "https://hooks.example.test/inbox"
    body = captured["body"]
    payload = json.loads(body)
    assert payload["event"] == "lead.created"
    assert payload["data"] == {"hello": "world"}
    assert "delivery_id" in payload

    expected_sig = sign_body(secret, body)
    assert captured["headers"][SIGNATURE_HEADER.lower()] == expected_sig

    async with patched_session_factory() as s:
        row = await s.get(Webhook, hook_id)
        assert row.last_delivery_status == 200
        assert row.failure_count == 0
        assert row.active is True


@pytest.mark.asyncio
async def test_dispatch_skips_inactive_or_unsubscribed(
    client: TestClient, patched_session_factory, monkeypatch
):
    user_id = _register(client)
    async with patched_session_factory() as s:
        s.add(
            Webhook(
                user_id=user_id,
                target_url="https://x.example.test/a",
                secret="s",
                event_types=["lead.created"],
                active=False,  # inactive
            )
        )
        s.add(
            Webhook(
                user_id=user_id,
                target_url="https://x.example.test/b",
                secret="s",
                event_types=["search.finished"],  # not subscribed to lead.created
                active=True,
            )
        )
        await s.commit()

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(webhook_svc.httpx, "AsyncClient", fake_client)

    await emit_event_sync(
        user_id,
        "lead.created",
        {},
        session_factory_override=patched_session_factory,
    )
    assert calls == []


@pytest.mark.asyncio
async def test_dispatch_auto_disables_after_consecutive_failures(
    client: TestClient, patched_session_factory, monkeypatch
):
    user_id = _register(client)
    async with patched_session_factory() as s:
        hook = Webhook(
            user_id=user_id,
            target_url="https://broken.example.test/x",
            secret="s",
            event_types=["lead.created"],
            active=True,
        )
        s.add(hook)
        await s.commit()
        await s.refresh(hook)
        hook_id = hook.id

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"err": "boom"})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(webhook_svc.httpx, "AsyncClient", fake_client)

    for _ in range(MAX_CONSECUTIVE_FAILURES):
        await emit_event_sync(
            user_id,
            "lead.created",
            {},
            session_factory_override=patched_session_factory,
        )

    async with patched_session_factory() as s:
        row = await s.get(Webhook, hook_id)
        assert row.failure_count == MAX_CONSECUTIVE_FAILURES
        assert row.active is False
        assert row.last_delivery_status == 503
        assert "503" in (row.last_failure_message or "")


@pytest.mark.asyncio
async def test_success_resets_failure_counter(
    client: TestClient, patched_session_factory, monkeypatch
):
    user_id = _register(client)
    async with patched_session_factory() as s:
        hook = Webhook(
            user_id=user_id,
            target_url="https://flaky.example.test/x",
            secret="s",
            event_types=["lead.created"],
            active=True,
            failure_count=3,
        )
        s.add(hook)
        await s.commit()
        await s.refresh(hook)
        hook_id = hook.id

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(webhook_svc.httpx, "AsyncClient", fake_client)

    await emit_event_sync(
        user_id,
        "lead.created",
        {},
        session_factory_override=patched_session_factory,
    )

    async with patched_session_factory() as s:
        row = await s.get(Webhook, hook_id)
        assert row.failure_count == 0
        assert row.active is True
        assert row.last_delivery_status == 204


@pytest.mark.asyncio
async def test_emit_event_unknown_event_is_dropped(
    patched_session_factory,
):
    # Just ensure no exception bubbles when called with an event the
    # platform doesn't know about — defensive guard.
    await emit_event_sync(
        1,
        "lead.exploded",
        {},
        session_factory_override=patched_session_factory,
    )
