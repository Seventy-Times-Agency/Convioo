"""``/api/v1/webhooks`` — outbound webhook subscriptions CRUD + test ping.

Carved out of ``app.py``. Webhooks are signed with HMAC-SHA256 (one
secret per row) and dispatched by ``core.services.webhooks``; this
module only exposes the CRUD surface the SPA + Zapier app talk to.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.schemas import (
    WebhookCreatedResponse,
    WebhookCreateRequest,
    WebhookListResponse,
    WebhookSchema,
    WebhookUpdateRequest,
)
from leadgen.core.services.webhooks import (
    ALLOWED_EVENTS,
    emit_event_sync,
    generate_secret,
)
from leadgen.db.models import User, Webhook
from leadgen.db.session import session_factory

router = APIRouter(tags=["webhooks"])


def _to_schema(row: Webhook) -> WebhookSchema:
    secret = row.secret or ""
    preview = f"{secret[:4]}…{secret[-4:]}" if len(secret) >= 12 else "…"
    return WebhookSchema(
        id=row.id,
        target_url=row.target_url,
        event_types=list(row.event_types or []),
        description=row.description,
        active=row.active,
        failure_count=row.failure_count,
        secret_preview=preview,
        last_delivery_at=row.last_delivery_at,
        last_delivery_status=row.last_delivery_status,
        last_failure_at=row.last_failure_at,
        last_failure_message=row.last_failure_message,
        created_at=row.created_at,
    )


def _validate_input(
    target_url: str | None, event_types: list[str] | None
) -> None:
    if target_url is not None:
        cleaned = target_url.strip()
        if not cleaned.lower().startswith(("https://", "http://")):
            raise HTTPException(
                status_code=400,
                detail="target_url must start with http:// or https://",
            )
    if event_types is not None:
        unknown = [e for e in event_types if e not in ALLOWED_EVENTS]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"unknown event types: {', '.join(unknown)}. "
                    f"Allowed: {', '.join(ALLOWED_EVENTS)}."
                ),
            )


@router.get("/api/v1/webhooks", response_model=WebhookListResponse)
async def list_webhooks(
    current_user: User = Depends(get_current_user),
) -> WebhookListResponse:
    async with session_factory() as session:
        rows = list(
            (
                await session.execute(
                    select(Webhook)
                    .where(Webhook.user_id == current_user.id)
                    .order_by(Webhook.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
    return WebhookListResponse(items=[_to_schema(r) for r in rows])


@router.post("/api/v1/webhooks", response_model=WebhookCreatedResponse)
async def create_webhook(
    body: WebhookCreateRequest,
    current_user: User = Depends(get_current_user),
) -> WebhookCreatedResponse:
    _validate_input(body.target_url, body.event_types)
    secret_plaintext = generate_secret()
    async with session_factory() as session:
        row = Webhook(
            user_id=current_user.id,
            target_url=body.target_url.strip(),
            secret=secret_plaintext,
            event_types=list(dict.fromkeys(body.event_types)),
            description=(body.description or "").strip() or None,
            active=True,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
    schema = _to_schema(row)
    return WebhookCreatedResponse(
        **schema.model_dump(), secret=secret_plaintext
    )


@router.patch(
    "/api/v1/webhooks/{webhook_id}", response_model=WebhookSchema
)
async def update_webhook(
    webhook_id: uuid.UUID,
    body: WebhookUpdateRequest,
    current_user: User = Depends(get_current_user),
) -> WebhookSchema:
    _validate_input(body.target_url, body.event_types)
    async with session_factory() as session:
        row = await session.get(Webhook, webhook_id)
        if row is None or row.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="webhook not found")
        if body.target_url is not None:
            row.target_url = body.target_url.strip()
        if body.event_types is not None:
            row.event_types = list(dict.fromkeys(body.event_types))
        if body.description is not None:
            row.description = (body.description or "").strip() or None
        if body.active is not None:
            row.active = bool(body.active)
            # Re-enabling a disabled webhook resets the failure counter
            # so the next attempt isn't immediately the 5th-and-disable.
            if body.active:
                row.failure_count = 0
        await session.commit()
        await session.refresh(row)
    return _to_schema(row)


@router.delete("/api/v1/webhooks/{webhook_id}")
async def delete_webhook(
    webhook_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    async with session_factory() as session:
        row = await session.get(Webhook, webhook_id)
        if row is None or row.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="webhook not found")
        await session.delete(row)
        await session.commit()
    return {"ok": True}


@router.post("/api/v1/webhooks/{webhook_id}/test")
async def test_webhook(
    webhook_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    """Schedule a ``webhook.test`` event so the user can confirm their
    endpoint is reachable. The dispatcher reads from the DB; we just
    confirm the row belongs to the caller and kick the event."""
    async with session_factory() as session:
        row = await session.get(Webhook, webhook_id)
        if row is None or row.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="webhook not found")
    background_tasks.add_task(
        emit_event_sync,
        current_user.id,
        "webhook.test",
        {
            "message": "ping from convioo",
            "webhook_id": str(webhook_id),
        },
    )
    return {"ok": True}
