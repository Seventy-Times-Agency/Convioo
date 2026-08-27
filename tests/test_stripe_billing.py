"""Stripe integration: signature verify, plan mapping, webhook handler.

The Stripe HTTP surface is mocked the same way the Notion test mocks
Notion — this is a pure unit suite, no network."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.config import get_settings
from leadgen.core.services.billing_service import (
    BillingService,
    QuotaVerdict,
    _is_paid_or_trialing,
)
from leadgen.db import session as db_session_mod
from leadgen.db.models import Base, StripeEvent, User
from leadgen.integrations.stripe_client import (
    StripeSignatureError,
    plan_for_price,
    verify_webhook_signature,
)
from leadgen.utils import rate_limit as rate_limit_mod

# ── Signature verification ───────────────────────────────────────────────


def _sign(secret: str, body: bytes, ts: int | None = None) -> str:
    timestamp = ts if ts is not None else int(time.time())
    signed = f"{timestamp}.".encode() + body
    digest = hmac.new(
        secret.encode("utf-8"), signed, hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


def test_verify_signature_accepts_correctly_signed_payload() -> None:
    secret = "whsec_test_123"
    body = b'{"id":"evt_1","type":"checkout.session.completed"}'
    header = _sign(secret, body)
    verify_webhook_signature(body, header, secret)  # does not raise


def test_verify_signature_rejects_missing_header() -> None:
    with pytest.raises(StripeSignatureError):
        verify_webhook_signature(b"x", None, "whsec_x")


def test_verify_signature_rejects_empty_secret() -> None:
    with pytest.raises(StripeSignatureError):
        verify_webhook_signature(b"x", "t=1,v1=abc", "")


def test_verify_signature_rejects_tampered_body() -> None:
    secret = "whsec_test"
    body = b'{"id":"evt_1"}'
    header = _sign(secret, body)
    with pytest.raises(StripeSignatureError):
        verify_webhook_signature(body + b"xx", header, secret)


def test_verify_signature_rejects_old_timestamp() -> None:
    secret = "whsec_test"
    body = b'{"id":"evt_1"}'
    # Sign with a timestamp 10 minutes in the past
    header = _sign(secret, body, ts=int(time.time()) - 600)
    with pytest.raises(StripeSignatureError):
        verify_webhook_signature(body, header, secret)


def test_verify_signature_rejects_malformed_header() -> None:
    with pytest.raises(StripeSignatureError):
        verify_webhook_signature(b"x", "garbage", "whsec_x")


# ── Price → plan mapping ─────────────────────────────────────────────────


def test_plan_for_price_resolves_known_prices() -> None:
    assert (
        plan_for_price(
            "price_pro_123",
            pro_price_id="price_pro_123",
            agency_price_id="price_agency_456",
        )
        == "pro"
    )
    assert (
        plan_for_price(
            "price_agency_456",
            pro_price_id="price_pro_123",
            agency_price_id="price_agency_456",
        )
        == "agency"
    )


def test_plan_for_price_unknown_price_falls_back_to_free() -> None:
    assert (
        plan_for_price(
            "price_unknown",
            pro_price_id="price_pro",
            agency_price_id="price_agency",
        )
        == "free"
    )
    assert (
        plan_for_price(
            None, pro_price_id="price_pro", agency_price_id="price_agency"
        )
        == "free"
    )


# ── Trial / paid check ───────────────────────────────────────────────────


def test_is_paid_or_trialing_picks_up_active_trial() -> None:
    user = User(
        id=1,
        plan="free",
        trial_ends_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    assert _is_paid_or_trialing(user) is True


def test_is_paid_or_trialing_ignores_expired_trial() -> None:
    user = User(
        id=1,
        plan="free",
        trial_ends_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    assert _is_paid_or_trialing(user) is False


def test_is_paid_or_trialing_picks_up_active_paid_plan() -> None:
    user = User(
        id=1,
        plan="pro",
        plan_until=datetime.now(timezone.utc) + timedelta(days=30),
    )
    assert _is_paid_or_trialing(user) is True


def test_is_paid_or_trialing_ignores_expired_plan() -> None:
    user = User(
        id=1,
        plan="pro",
        plan_until=datetime.now(timezone.utc) - timedelta(days=1),
    )
    assert _is_paid_or_trialing(user) is False


def test_is_paid_or_trialing_free_plan_with_plan_until_does_not_count() -> None:
    user = User(
        id=1,
        plan="free",
        plan_until=datetime.now(timezone.utc) + timedelta(days=30),
    )
    assert _is_paid_or_trialing(user) is False


# ── BillingService respects trial / paid bypass ──────────────────────────


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def patched_session_factory(monkeypatch, db_engine):
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
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
    ):
        getattr(rate_limit_mod, name)._events.clear()
    yield


@pytest.mark.asyncio
async def test_billing_service_allows_trialing_user_past_quota(
    patched_session_factory, monkeypatch
) -> None:
    monkeypatch.setattr(
        get_settings(), "billing_enforced", True, raising=False
    )
    async with patched_session_factory() as session:
        user = User(
            id=42,
            email="u@example.com",
            queries_used=10,
            queries_limit=5,
            plan="free",
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        session.add(user)
        await session.commit()
        check = await BillingService(session).try_consume(42)
        assert check.verdict == QuotaVerdict.ALLOWED


@pytest.mark.asyncio
async def test_billing_service_blocks_free_user_at_limit(
    patched_session_factory, monkeypatch
) -> None:
    monkeypatch.setattr(
        get_settings(), "billing_enforced", True, raising=False
    )
    async with patched_session_factory() as session:
        user = User(
            id=43,
            email="u@example.com",
            queries_used=5,
            queries_limit=5,
            plan="free",
        )
        session.add(user)
        await session.commit()
        check = await BillingService(session).try_consume(43)
        assert check.verdict == QuotaVerdict.EXHAUSTED


# ── Webhook endpoint ─────────────────────────────────────────────────────


@pytest.fixture
def stripe_env(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "stripe_secret_key", "sk_test_x", raising=False)
    monkeypatch.setattr(
        s, "stripe_webhook_secret", "whsec_test", raising=False
    )
    monkeypatch.setattr(
        s, "stripe_price_id_pro", "price_pro", raising=False
    )
    monkeypatch.setattr(
        s, "stripe_price_id_agency", "price_agency", raising=False
    )
    return s


def _post_event(client: TestClient, event: dict[str, Any], secret: str) -> Any:
    body = json.dumps(event).encode("utf-8")
    header = _sign(secret, body)
    return client.post(
        "/api/v1/billing/webhook",
        content=body,
        headers={
            "stripe-signature": header,
            "content-type": "application/json",
        },
    )


def test_webhook_503_when_stripe_not_configured(patched_session_factory):
    from leadgen.adapters.web_api.app import create_app

    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=x"},
    )
    assert resp.status_code == 503


def test_webhook_rejects_bad_signature(patched_session_factory, stripe_env):
    from leadgen.adapters.web_api.app import create_app

    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/billing/webhook",
        content=b'{"id":"evt_1","type":"checkout.session.completed"}',
        headers={"stripe-signature": "t=1,v1=deadbeef"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_webhook_checkout_completed_binds_customer(
    patched_session_factory, stripe_env
):
    from leadgen.adapters.web_api.app import create_app

    async with patched_session_factory() as session:
        user = User(id=99, email="u@example.com")
        session.add(user)
        await session.commit()

    client = TestClient(create_app())
    event = {
        "id": "evt_test_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": "99",
                "customer": "cus_abc123",
            }
        },
    }
    resp = _post_event(client, event, "whsec_test")
    assert resp.status_code == 200

    async with patched_session_factory() as session:
        user = await session.get(User, 99)
        assert user is not None
        assert user.stripe_customer_id == "cus_abc123"


@pytest.mark.asyncio
async def test_webhook_subscription_updated_promotes_plan(
    patched_session_factory, stripe_env
):
    from leadgen.adapters.web_api.app import create_app

    async with patched_session_factory() as session:
        user = User(
            id=100,
            email="u@example.com",
            stripe_customer_id="cus_xyz",
        )
        session.add(user)
        await session.commit()

    client = TestClient(create_app())
    period_end = int(
        (datetime.now(timezone.utc) + timedelta(days=30)).timestamp()
    )
    event = {
        "id": "evt_sub_1",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "customer": "cus_xyz",
                "status": "active",
                "current_period_end": period_end,
                "items": {"data": [{"price": {"id": "price_pro"}}]},
            }
        },
    }
    resp = _post_event(client, event, "whsec_test")
    assert resp.status_code == 200

    async with patched_session_factory() as session:
        user = await session.get(User, 100)
        assert user is not None
        assert user.plan == "pro"
        assert user.plan_until is not None


@pytest.mark.asyncio
async def test_webhook_idempotent_on_duplicate_event(
    patched_session_factory, stripe_env
):
    from leadgen.adapters.web_api.app import create_app

    async with patched_session_factory() as session:
        user = User(
            id=101,
            email="u@example.com",
            stripe_customer_id="cus_dup",
        )
        session.add(user)
        await session.commit()

    client = TestClient(create_app())
    period_end = int(
        (datetime.now(timezone.utc) + timedelta(days=30)).timestamp()
    )
    event = {
        "id": "evt_dup",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "customer": "cus_dup",
                "status": "active",
                "current_period_end": period_end,
                "items": {"data": [{"price": {"id": "price_agency"}}]},
            }
        },
    }
    r1 = _post_event(client, event, "whsec_test")
    r2 = _post_event(client, event, "whsec_test")
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Second response signals duplicate so the test confirms we hit
    # the idempotency branch.
    assert r2.text == "duplicate"

    async with patched_session_factory() as session:
        rows = (
            (await session.execute(StripeEvent.__table__.select()))
            .fetchall()
        )
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_webhook_subscription_deleted_downgrades_to_free(
    patched_session_factory, stripe_env
):
    from leadgen.adapters.web_api.app import create_app

    async with patched_session_factory() as session:
        user = User(
            id=102,
            email="u@example.com",
            stripe_customer_id="cus_cancel",
            plan="pro",
            plan_until=datetime.now(timezone.utc) + timedelta(days=20),
        )
        session.add(user)
        await session.commit()

    client = TestClient(create_app())
    event = {
        "id": "evt_cancel",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "customer": "cus_cancel",
                "status": "canceled",
            }
        },
    }
    resp = _post_event(client, event, "whsec_test")
    assert resp.status_code == 200

    async with patched_session_factory() as session:
        user = await session.get(User, 102)
        assert user is not None
        assert user.plan == "free"
        assert user.plan_until is None


# ── Subscription endpoint ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_subscription_endpoint_reports_trial_and_plan(
    patched_session_factory, stripe_env
):

    trial_end = datetime.now(timezone.utc) + timedelta(days=10)
    async with patched_session_factory() as session:
        user = User(
            id=200,
            email="u@example.com",
            plan="free",
            trial_ends_at=trial_end,
        )
        session.add(user)
        await session.commit()

    # Call the subscription handler directly — bypassing auth saves us
    # from minting a real session cookie just to read public state.
    from leadgen.adapters.web_api.app import create_app as _create

    app = _create()
    fn = None
    for r in app.router.routes:
        if getattr(r, "path", None) == "/api/v1/billing/subscription":
            fn = r.endpoint  # type: ignore[attr-defined]
            break
    assert fn is not None
    async with patched_session_factory() as session:
        user = await session.get(User, 200)
    resp = await fn(current_user=user)  # type: ignore[misc]
    assert resp.plan == "free"
    assert resp.trial_active is True
    assert resp.paid_active is False
