"""Telegram bot webhook and account-linking endpoints."""
from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from leadgen.adapters.telegram_v2 import api as tg_api
from leadgen.adapters.telegram_v2.bot import generate_link_token, process_update
from leadgen.adapters.web_api.auth import get_current_user
from leadgen.config import get_settings
from leadgen.db.models import TelegramConnection, User
from leadgen.db.session import session_factory
from leadgen.utils import spawn

logger = logging.getLogger(__name__)
router = APIRouter(tags=["telegram"])


@router.post("/api/v1/telegram/webhook", include_in_schema=False)
async def telegram_webhook(request: Request) -> dict:  # type: ignore[type-arg]
    """Receives updates from Telegram's Bot API."""
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=503, detail="Telegram bot not configured")

    # Telegram echoes the webhook secret back in this header on every
    # call. Without a configured secret anyone who knows a linked chat id
    # could forge updates (and run /search as that user) — so the bot
    # does not accept updates at all until the secret is set.
    if not settings.telegram_webhook_secret:
        raise HTTPException(
            status_code=503, detail="Telegram webhook secret not configured"
        )
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
    #: Готовая ссылка на бота с кодом — открыл и нажал «Start».
    deep_link: str | None = None


class TelegramStatus(BaseModel):
    #: Бот компании подключён на сервере (есть токен).
    configured: bool
    bot_username: str | None = None
    linked: bool
    linked_at: str | None = None


@router.post("/api/v1/telegram/link-token", response_model=LinkTokenResponse)
async def create_link_token(
    current_user: User = Depends(get_current_user),
) -> LinkTokenResponse:
    """Generate a short-lived token to link the user's Telegram account."""
    if not get_settings().telegram_bot_token:
        raise HTTPException(status_code=503, detail="Telegram bot not configured")
    token = generate_link_token(current_user.id)
    name = await tg_api.bot_username()
    return LinkTokenResponse(
        token=token,
        expires_in_seconds=900,
        deep_link=f"https://t.me/{name}?start={token}" if name else None,
    )


@router.get("/api/v1/telegram/status", response_model=TelegramStatus)
async def telegram_status(current_user: User = Depends(get_current_user)) -> TelegramStatus:
    """Подключён ли бот компании и привязан ли к нему этот пользователь."""
    configured = bool(get_settings().telegram_bot_token)
    async with session_factory() as session:
        conn = (
            await session.execute(
                select(TelegramConnection)
                .where(TelegramConnection.user_id == current_user.id)
                .order_by(TelegramConnection.linked_at.desc())
            )
        ).scalars().first()
    return TelegramStatus(
        configured=configured,
        bot_username=await tg_api.bot_username() if configured else None,
        linked=conn is not None,
        linked_at=conn.linked_at.isoformat() if conn is not None else None,
    )


@router.delete("/api/v1/telegram/link")
async def telegram_unlink(current_user: User = Depends(get_current_user)) -> dict:  # type: ignore[type-arg]
    async with session_factory() as session:
        await session.execute(
            sa_delete(TelegramConnection).where(TelegramConnection.user_id == current_user.id)
        )
        await session.commit()
    return {"ok": True}
