"""Thin Stripe wrapper for Checkout, Customer Portal and webhook ingest.

Stripe ships an official SDK but it's a heavy dependency for the
three endpoints we actually need. We hit ``api.stripe.com`` over
the same ``httpx.AsyncClient`` pattern the Notion integration uses
and verify webhook signatures by hand — it's ~80 LoC and the
official SDK does the same thing internally.

Docs:
- https://docs.stripe.com/api/checkout/sessions/create
- https://docs.stripe.com/api/customer_portal/sessions/create
- https://docs.stripe.com/webhooks/signatures
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

STRIPE_API_BASE = "https://api.stripe.com/v1"
STRIPE_API_VERSION = "2024-06-20"
# How far back a signed timestamp is allowed to drift before we treat
# the request as a replay. Stripe's reference uses 5 minutes.
SIGNATURE_TOLERANCE_SEC = 5 * 60


class StripeError(RuntimeError):
    """Raised when Stripe rejects a request or returns malformed JSON."""


class StripeSignatureError(StripeError):
    """Raised when the webhook signature header is missing or invalid."""


@dataclass(slots=True)
class CheckoutSession:
    id: str
    url: str
    customer: str | None


@dataclass(slots=True)
class PortalSession:
    id: str
    url: str


class StripeClient:
    """Async Stripe client. Use as ``async with StripeClient(key) as c``."""

    def __init__(self, secret_key: str, *, timeout: float = 15.0) -> None:
        if not secret_key:
            raise StripeError("STRIPE_SECRET_KEY is empty")
        self.secret_key = secret_key
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> StripeClient:
        self._client = self._build_client()
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self.timeout,
            headers={
                "Authorization": f"Bearer {self.secret_key}",
                "Stripe-Version": STRIPE_API_VERSION,
            },
        )

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    async def _post(self, path: str, form: dict[str, str]) -> dict[str, Any]:
        client = await self._http()
        resp = await client.post(
            f"{STRIPE_API_BASE}{path}",
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code >= 400:
            raise StripeError(
                f"Stripe POST {path} returned {resp.status_code}: "
                f"{resp.text[:300]}"
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise StripeError(f"Stripe POST {path} returned non-JSON") from exc

    async def create_checkout_session(
        self,
        *,
        price_id: str,
        success_url: str,
        cancel_url: str,
        customer_id: str | None = None,
        customer_email: str | None = None,
        client_reference_id: str | None = None,
        trial_days: int | None = None,
    ) -> CheckoutSession:
        """Create a hosted Checkout Session for a subscription purchase."""
        form: dict[str, str] = {
            "mode": "subscription",
            "line_items[0][price]": price_id,
            "line_items[0][quantity]": "1",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "allow_promotion_codes": "true",
        }
        if customer_id:
            form["customer"] = customer_id
        elif customer_email:
            form["customer_email"] = customer_email
        if client_reference_id is not None:
            form["client_reference_id"] = client_reference_id
        if trial_days is not None and trial_days > 0:
            form["subscription_data[trial_period_days]"] = str(trial_days)
        payload = await self._post("/checkout/sessions", form)
        return CheckoutSession(
            id=payload["id"],
            url=payload["url"],
            customer=payload.get("customer"),
        )

    async def create_portal_session(
        self, *, customer_id: str, return_url: str
    ) -> PortalSession:
        """Create a hosted Customer Portal session for plan management."""
        form = {
            "customer": customer_id,
            "return_url": return_url,
        }
        payload = await self._post("/billing_portal/sessions", form)
        return PortalSession(id=payload["id"], url=payload["url"])


def verify_webhook_signature(
    payload_body: bytes,
    signature_header: str | None,
    webhook_secret: str,
    *,
    tolerance_sec: int = SIGNATURE_TOLERANCE_SEC,
    now: float | None = None,
) -> None:
    """Validate the ``Stripe-Signature`` header against the raw body.

    Raises ``StripeSignatureError`` on any anomaly. We verify exactly
    what Stripe's reference implementation does:
    1. parse ``t=...,v1=...`` from the header
    2. compute HMAC-SHA256 of ``f"{t}.{body}"`` with the secret
    3. compare in constant time, and reject if ``t`` drifted too far
    """
    if not signature_header:
        raise StripeSignatureError("missing Stripe-Signature header")
    if not webhook_secret:
        raise StripeSignatureError("STRIPE_WEBHOOK_SECRET is empty")

    pairs = [p.strip() for p in signature_header.split(",") if "=" in p]
    parsed: dict[str, list[str]] = {}
    for pair in pairs:
        key, _, value = pair.partition("=")
        parsed.setdefault(key, []).append(value)
    timestamps = parsed.get("t") or []
    candidates = parsed.get("v1") or []
    if not timestamps or not candidates:
        raise StripeSignatureError("malformed Stripe-Signature header")
    try:
        timestamp = int(timestamps[0])
    except ValueError as exc:
        raise StripeSignatureError("non-numeric timestamp") from exc

    current = now if now is not None else time.time()
    if abs(current - timestamp) > tolerance_sec:
        raise StripeSignatureError("signature timestamp outside tolerance")

    signed = f"{timestamp}.".encode() + payload_body
    expected = hmac.new(
        webhook_secret.encode("utf-8"), signed, hashlib.sha256
    ).hexdigest()
    if not any(hmac.compare_digest(expected, c) for c in candidates):
        raise StripeSignatureError("signature mismatch")


# Map a Stripe price-id to one of our internal plan slugs. Configured
# at runtime from settings so we can move price ids without code edits.
def plan_for_price(
    price_id: str | None,
    *,
    pro_price_id: str,
    agency_price_id: str,
) -> str:
    if not price_id:
        return "free"
    if pro_price_id and price_id == pro_price_id:
        return "pro"
    if agency_price_id and price_id == agency_price_id:
        return "agency"
    return "free"
