"""Thin async wrapper around the Telegram Bot HTTP API."""
from __future__ import annotations

import httpx

from leadgen.config import get_settings


async def _call(method: str, **payload) -> dict:  # type: ignore[type-arg]
    token = get_settings().telegram_bot_token
    if not token:
        return {}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"https://api.telegram.org/bot{token}/{method}",
            json={k: v for k, v in payload.items() if v is not None},
        )
        return r.json()


async def send_message(chat_id: int, text: str, parse_mode: str = "HTML") -> dict:  # type: ignore[type-arg]
    return await _call("sendMessage", chat_id=chat_id, text=text, parse_mode=parse_mode)


async def edit_message_text(
    chat_id: int, message_id: int, text: str, parse_mode: str = "HTML"
) -> dict:  # type: ignore[type-arg]
    return await _call(
        "editMessageText",
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        parse_mode=parse_mode,
    )


async def set_webhook(url: str, secret_token: str | None = None) -> dict:  # type: ignore[type-arg]
    return await _call("setWebhook", url=url, secret_token=secret_token)


_BOT_USERNAME: str | None = None


async def bot_username() -> str | None:
    """@имя бота для ссылки t.me/<bot>?start=<код>. Кэшируется на процесс."""
    global _BOT_USERNAME
    if _BOT_USERNAME:
        return _BOT_USERNAME
    try:
        me = await _call("getMe")
    except Exception:  # noqa: BLE001
        return None
    name = (me.get("result") or {}).get("username") if isinstance(me, dict) else None
    if name:
        _BOT_USERNAME = name
    return name
