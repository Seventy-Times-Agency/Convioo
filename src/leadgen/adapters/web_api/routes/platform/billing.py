"""``/api/v1/billing/*`` — Stripe Checkout, Portal, webhooks.

Stage-mode: when STRIPE_SECRET_KEY is empty, all endpoints respond
503 with a friendly JSON body so the rest of the API stays useful
for development without billing keys.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.schemas import (
    BillingSubscriptionResponse,
    CheckoutRequest,
    CheckoutResponse,
    PortalRequest,
    PortalResponse,
)
from leadgen.config import get_settings
from leadgen.db.models import StripeEvent, User
from leadgen.db.session import session_factory

router = APIRouter(tags=["billing"])


def _billing_configured() -> bool:
    s = get_settings()
    return bool(s.stripe_secret_key)


def _stripe_unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=(
            "Stripe is not configured on this deployment. Set "
            "STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, "
            "STRIPE_PRICE_ID_PRO and STRIPE_PRICE_ID_AGENCY to "
            "enable billing."
        ),
    )


@router.get(
    "/api/v1/billing/subscription",
    response_model=BillingSubscriptionResponse,
)
async def billing_subscription(
    current_user: User = Depends(get_current_user),
) -> BillingSubscriptionResponse:
    """Return the user's current plan / trial state."""
    async with session_factory() as session:
        user = await session.get(User, current_user.id)
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")

        now = datetime.now(timezone.utc)
        trial_active = bool(
            user.trial_ends_at
            and (
                user.trial_ends_at.replace(tzinfo=timezone.utc)
                if user.trial_ends_at.tzinfo is None
                else user.trial_ends_at
            )
            > now
        )
        paid_active = (
            user.plan != "free"
            and user.plan_until is not None
            and (
                user.plan_until.replace(tzinfo=timezone.utc)
                if user.plan_until.tzinfo is None
                else user.plan_until
            )
            > now
        )
        return BillingSubscriptionResponse(
            plan=user.plan,
            plan_until=user.plan_until,
            trial_ends_at=user.trial_ends_at,
            trial_active=trial_active,
            paid_active=paid_active,
            has_stripe_customer=bool(user.stripe_customer_id),
            queries_used=user.queries_used,
            queries_limit=user.queries_limit,
        )


@router.post(
    "/api/v1/billing/checkout", response_model=CheckoutResponse
)
async def billing_checkout(
    body: CheckoutRequest,
    current_user: User = Depends(get_current_user),
) -> CheckoutResponse:
    """Mint a Stripe Checkout Session and return its hosted URL."""
    if not _billing_configured():
        raise _stripe_unavailable()
    from leadgen.integrations.stripe_client import (
        StripeClient,
        StripeError,
    )

    settings = get_settings()
    if body.plan == "pro":
        price_id = settings.stripe_price_id_pro
    else:
        price_id = settings.stripe_price_id_agency
    if not price_id:
        raise HTTPException(
            status_code=503,
            detail=f"price id for plan '{body.plan}' is not set",
        )

    async with session_factory() as session:
        user = await session.get(User, current_user.id)
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")
        customer_id = user.stripe_customer_id
        email = user.email

    try:
        async with StripeClient(settings.stripe_secret_key) as client:
            cs = await client.create_checkout_session(
                price_id=price_id,
                success_url=body.success_url,
                cancel_url=body.cancel_url,
                customer_id=customer_id,
                customer_email=email if not customer_id else None,
                client_reference_id=str(current_user.id),
            )
    except StripeError as exc:
        raise HTTPException(
            status_code=502, detail=f"stripe error: {exc}"
        ) from exc

    if cs.customer and not customer_id:
        async with session_factory() as session:
            await session.execute(
                update(User)
                .where(User.id == current_user.id)
                .values(stripe_customer_id=cs.customer)
            )
            await session.commit()
    return CheckoutResponse(url=cs.url, session_id=cs.id)


@router.post(
    "/api/v1/billing/portal", response_model=PortalResponse
)
async def billing_portal(
    body: PortalRequest,
    current_user: User = Depends(get_current_user),
) -> PortalResponse:
    """Mint a Customer Portal session for plan management."""
    if not _billing_configured():
        raise _stripe_unavailable()
    from leadgen.integrations.stripe_client import (
        StripeClient,
        StripeError,
    )

    async with session_factory() as session:
        user = await session.get(User, current_user.id)
        if user is None or not user.stripe_customer_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No Stripe customer for this user yet — "
                    "run checkout first."
                ),
            )
        customer_id = user.stripe_customer_id

    settings = get_settings()
    try:
        async with StripeClient(settings.stripe_secret_key) as client:
            portal = await client.create_portal_session(
                customer_id=customer_id, return_url=body.return_url
            )
    except StripeError as exc:
        raise HTTPException(
            status_code=502, detail=f"stripe error: {exc}"
        ) from exc
    return PortalResponse(url=portal.url)


async def _apply_stripe_event(
    kind: str, obj: dict[str, Any]
) -> None:
    """Map the supported event types onto ``users`` columns."""
    from leadgen.integrations.stripe_client import plan_for_price

    settings = get_settings()
    if kind == "checkout.session.completed":
        user_id_str = obj.get("client_reference_id")
        customer = obj.get("customer")
        if not user_id_str or not customer:
            return
        try:
            user_id = int(user_id_str)
        except ValueError:
            return
        async with session_factory() as session:
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(stripe_customer_id=customer)
            )
            await session.commit()
        return

    if kind in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "invoice.payment_succeeded",
        "invoice.payment_failed",
    ):
        customer = obj.get("customer")
        if not customer:
            return
        price_id: str | None = None
        items = (obj.get("items") or {}).get("data") or []
        if items:
            price_id = (items[0].get("price") or {}).get("id")
        if price_id is None:
            lines = (obj.get("lines") or {}).get("data") or []
            if lines:
                price_id = (lines[0].get("price") or {}).get("id")
        current_period_end = (
            obj.get("current_period_end") or obj.get("period_end")
        )
        status_value = obj.get("status") or ""

        new_plan = plan_for_price(
            price_id,
            pro_price_id=settings.stripe_price_id_pro,
            agency_price_id=settings.stripe_price_id_agency,
        )
        if kind == "customer.subscription.deleted" or status_value in (
            "canceled",
            "unpaid",
        ):
            new_plan = "free"
            plan_until = None
        else:
            plan_until = (
                datetime.fromtimestamp(
                    int(current_period_end), tz=timezone.utc
                )
                if current_period_end
                else None
            )

        async with session_factory() as session:
            await session.execute(
                update(User)
                .where(User.stripe_customer_id == customer)
                .values(plan=new_plan, plan_until=plan_until)
            )
            await session.commit()


@router.post("/api/v1/billing/webhook")
async def billing_webhook(request: Request) -> Response:
    """Receive Stripe events and reflect plan changes onto users."""
    if not _billing_configured():
        raise _stripe_unavailable()
    from leadgen.integrations.stripe_client import (
        StripeSignatureError,
        verify_webhook_signature,
    )

    settings = get_settings()
    body = await request.body()
    sig = request.headers.get("stripe-signature")
    try:
        verify_webhook_signature(body, sig, settings.stripe_webhook_secret)
    except StripeSignatureError as exc:
        raise HTTPException(
            status_code=400, detail=f"signature: {exc}"
        ) from exc

    try:
        event = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=400, detail="invalid json body"
        ) from exc

    event_id = event.get("id") or ""
    kind = event.get("type") or ""
    if not event_id or not kind:
        raise HTTPException(status_code=400, detail="missing id/type")

    async with session_factory() as session:
        session.add(StripeEvent(id=event_id, kind=kind))
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return Response(status_code=200, content="duplicate")

    data = (event.get("data") or {}).get("object") or {}
    await _apply_stripe_event(kind, data)
    return Response(status_code=200, content="ok")
