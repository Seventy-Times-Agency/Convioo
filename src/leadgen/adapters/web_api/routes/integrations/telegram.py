"""Telegram bot webhook and account-linking endpoints."""
from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from leadgen.adapters.telegram_v2.bot import generate_link_token, process_update
from leadgen.adapters.web_api.auth import get_current_user
from leadgen.config import get_settings
from leadgen.db.models import User
from leadgen.utils import spawn

logger = logging.getLogger(__name__)
router = APIRouter(tags=["telegram"])


@router.post("/api/v1/telegram/webhook", include_in_schema=False)
async def telegram_webhook(request: Request) -> dict:  # type: ignore[type-arg]
    """Receives updates from Telegram's Bot API."""
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=503, detail="Telegram bot not configured")

    # When a webhook secret is configured, Telegram echoes it back in this
    # header on every call. Reject anything that doesn't match so a forged
    # POST to this public URL can't inject /search or /start updates.
    if settings.telegram_webhook_secret:
        provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not secrets.compare_digest(provided, settings.telegram_webhook_secret):
            raise HTTPException(status_code=403, detail="invalid webhook secret")

    update = await request.json()
    # Dispatch in background — Telegram needs a fast 200 response
    spawn(process_update(update), name="tg-update")
    return {"ok": True}


class LinkTokenResponse(BaseModel):
    token: str
    expires_in_seconds: int


@router.post("/api/v1/telegram/link-token", response_model=LinkTokenResponse)
async def create_link_token(
    current_user: User = Depends(get_current_user),
) -> LinkTokenResponse:
    """Generate a short-lived token to link the user's Telegram account."""
    token = generate_link_token(current_user.id)
    return LinkTokenResponse(token=token, expires_in_seconds=900)
