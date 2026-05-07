"""Billing / Stripe schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CheckoutRequest(BaseModel):
    """Body for ``POST /api/v1/billing/checkout``."""

    plan: str = Field(..., pattern=r"^(pro|agency)$")
    # Where Stripe redirects the customer when they finish or cancel.
    # Frontend hands these in so prod / preview / dev all work without
    # the backend hard-coding a domain.
    success_url: str = Field(..., min_length=10, max_length=2048)
    cancel_url: str = Field(..., min_length=10, max_length=2048)


class CheckoutResponse(BaseModel):
    """Hosted Checkout URL the frontend should ``window.location`` to."""

    url: str
    session_id: str


class PortalRequest(BaseModel):
    """Body for ``POST /api/v1/billing/portal``."""

    return_url: str = Field(..., min_length=10, max_length=2048)


class PortalResponse(BaseModel):
    url: str


class BillingSubscriptionResponse(BaseModel):
    """Snapshot of the user's current plan state."""

    plan: str
    plan_until: datetime | None
    trial_ends_at: datetime | None
    trial_active: bool
    paid_active: bool
    has_stripe_customer: bool
    queries_used: int
    queries_limit: int
