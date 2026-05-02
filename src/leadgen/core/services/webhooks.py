"""Outbound webhook dispatch.

Fires JSON POSTs at user-registered ``target_url``s when an event
happens. Each request carries an ``X-Convioo-Signature`` header set to
``sha256=<hex>`` of the body, HMAC'd with the per-row ``secret``.

Use ``emit_event(...)`` from anywhere in the codebase. It schedules
delivery on the running event loop and returns immediately so the
trigger flow never blocks on the network.

Five consecutive failures (network, timeout, or any non-2xx) flip the
row's ``active`` flag to false so we stop hammering a dead URL. The
counter resets on the next 2xx.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select

from leadgen.db.models import Webhook
from leadgen.db.session import session_factory as default_session_factory

logger = logging.getLogger(__name__)

ALLOWED_EVENTS: tuple[str, ...] = (
    "lead.created",
    "lead.status_changed",
    "search.finished",
    "webhook.test",
)

DELIVERY_TIMEOUT_S = 5.0
MAX_CONSECUTIVE_FAILURES = 5
SIGNATURE_HEADER = "X-Convioo-Signature"
EVENT_HEADER = "X-Convioo-Event"
DELIVERY_HEADER = "X-Convioo-Delivery"


def generate_secret() -> str:
    """Per-webhook HMAC secret. 32 random bytes, urlsafe-encoded."""
    return secrets.token_urlsafe(32)


def sign_body(secret: str, body: bytes) -> str:
    """Return the value for ``X-Convioo-Signature``."""
    digest = hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return f"sha256={digest}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _post_one(
    client: httpx.AsyncClient,
    webhook: Webhook,
    body: bytes,
    event: str,
    delivery_id: str,
) -> tuple[bool, int | None, str | None]:
    """One round-trip. Returns (ok, status, error_message)."""
    try:
        response = await client.post(
            webhook.target_url,
            content=body,
            headers={
                "Content-Type": "application/json",
                SIGNATURE_HEADER: sign_body(webhook.secret, body),
                EVENT_HEADER: event,
                DELIVERY_HEADER: delivery_id,
                "User-Agent": "Convioo-Webhooks/1.0",
            },
        )
    except httpx.HTTPError as exc:
        return False, None, f"{type(exc).__name__}: {exc}"
    except Exception as exc:  # pragma: no cover - defensive
        return False, None, f"{type(exc).__name__}: {exc}"
    ok = 200 <= response.status_code < 300
    msg = None if ok else f"non-2xx: {response.status_code}"
    return ok, response.status_code, msg


async def _dispatch(
    user_id: int,
    event: str,
    payload: dict[str, Any],
    session_factory_override: Any = None,
) -> None:
    """Find every active webhook subscribed to ``event`` for the user
    and fire one request per row. Updates the row's stats afterwards.
    Failures are absorbed — a dead URL must not surface as a 500 in
    the parent flow."""
    if event not in ALLOWED_EVENTS:
        logger.warning("webhook: refusing unknown event %r", event)
        return

    session_factory = session_factory_override or default_session_factory
    delivery_id = secrets.token_urlsafe(12)
    body_bytes = json.dumps(
        {
            "event": event,
            "delivery_id": delivery_id,
            "delivered_at": _utcnow().isoformat(),
            "data": payload,
        },
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")

    try:
        async with session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(Webhook).where(
                            Webhook.user_id == user_id,
                            Webhook.active.is_(True),
                        )
                    )
                )
                .scalars()
                .all()
            )
            targets = [r for r in rows if event in (r.event_types or [])]

            if not targets:
                return

            timeout = httpx.Timeout(DELIVERY_TIMEOUT_S)
            async with httpx.AsyncClient(timeout=timeout) as client:
                results = await asyncio.gather(
                    *[
                        _post_one(client, w, body_bytes, event, delivery_id)
                        for w in targets
                    ],
                    return_exceptions=False,
                )

            now = _utcnow()
            for hook, (ok, status, err) in zip(targets, results, strict=True):
                hook.last_delivery_at = now
                hook.last_delivery_status = status
                if ok:
                    hook.failure_count = 0
                    hook.last_failure_message = None
                else:
                    hook.failure_count = (hook.failure_count or 0) + 1
                    hook.last_failure_at = now
                    hook.last_failure_message = (err or "")[:500]
                    if hook.failure_count >= MAX_CONSECUTIVE_FAILURES:
                        hook.active = False
                        logger.warning(
                            "webhook: auto-disabled %s after %d failures",
                            hook.id,
                            hook.failure_count,
                        )
            await session.commit()
    except Exception:
        logger.exception("webhook dispatch failed for user=%s event=%s",
                         user_id, event)


def emit_event(
    user_id: int,
    event: str,
    payload: dict[str, Any],
) -> None:
    """Schedule a webhook event. Non-blocking — returns immediately.

    Safe to call outside an event loop; in that case the work is
    silently dropped (mirrors what we want during synchronous tests
    that aren't asserting on webhook delivery)."""
    if event not in ALLOWED_EVENTS:
        logger.warning("webhook: refusing unknown event %r", event)
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(_dispatch(user_id, event, payload))


async def emit_event_sync(
    user_id: int,
    event: str,
    payload: dict[str, Any],
    session_factory_override: Any = None,
) -> None:
    """Awaitable variant. Blocks until every dispatch finishes — used
    for tests and as the function FastAPI calls when added to
    ``BackgroundTasks``, since BackgroundTasks awaits the coroutine
    against the same event loop as the request."""
    await _dispatch(user_id, event, payload, session_factory_override)


def serialize_lead(lead: Any) -> dict[str, Any]:
    """Compact payload for lead.* events. We pick the columns most
    useful to a CRM consumer; raw provider blobs stay out."""
    return {
        "id": str(lead.id),
        "query_id": str(lead.query_id),
        "name": lead.name,
        "category": lead.category,
        "address": lead.address,
        "phone": lead.phone,
        "website": lead.website,
        "rating": lead.rating,
        "reviews_count": lead.reviews_count,
        "score_ai": lead.score_ai,
        "lead_status": lead.lead_status,
        "owner_user_id": lead.owner_user_id,
        "tags": lead.tags,
        "summary": lead.summary,
        "advice": lead.advice,
        "created_at": (
            lead.created_at.isoformat() if lead.created_at else None
        ),
    }


def serialize_search(search: Any) -> dict[str, Any]:
    return {
        "id": str(search.id),
        "user_id": search.user_id,
        "team_id": str(search.team_id) if search.team_id else None,
        "niche": search.niche,
        "region": search.region,
        "status": search.status,
        "leads_count": search.leads_count,
        "avg_score": search.avg_score,
        "created_at": (
            search.created_at.isoformat() if search.created_at else None
        ),
        "finished_at": (
            search.finished_at.isoformat() if search.finished_at else None
        ),
        "error": search.error,
    }


__all__ = [
    "ALLOWED_EVENTS",
    "MAX_CONSECUTIVE_FAILURES",
    "SIGNATURE_HEADER",
    "DELIVERY_HEADER",
    "EVENT_HEADER",
    "emit_event",
    "emit_event_sync",
    "generate_secret",
    "sign_body",
    "serialize_lead",
    "serialize_search",
]
