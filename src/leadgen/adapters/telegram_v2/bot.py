"""Telegram update processor — parses incoming updates and dispatches commands.

Commands:
  /start <token>          Link this Telegram chat to a Convioo account.
                          The user must first generate a token at
                          Settings -> Telegram in the web app.
  /search <niche> in <region>   Run a lead search.
  /help                   Show available commands.
"""
from __future__ import annotations

import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from leadgen.adapters.telegram_v2 import api as tg
from leadgen.adapters.telegram_v2.sinks import TelegramDeliverySink, TelegramProgressSink
from leadgen.db.models import SearchQuery, User
from leadgen.db.models.telegram import TelegramConnection
from leadgen.db.session import session_factory
from leadgen.pipeline.search import run_search_with_sinks
from leadgen.utils import spawn

logger = logging.getLogger(__name__)

# In-memory token store: token -> (user_id, expires_at)
# Not crash-safe, but tokens are only valid for 15 min — acceptable for a bot flow.
_PENDING_TOKENS: dict[str, tuple[int, datetime]] = {}
_TOKEN_TTL_SECONDS = 900  # 15 minutes


def generate_link_token(user_id: int) -> str:
    """Generate a short-lived link token for a user. Returns the token string."""
    _purge_expired()
    token = secrets.token_hex(4).upper()  # 8-char hex
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
        seconds=_TOKEN_TTL_SECONDS
    )
    _PENDING_TOKENS[token] = (user_id, expires_at)
    return token


def _purge_expired() -> None:
    now = datetime.utcnow()
    expired = [k for k, (_, exp) in _PENDING_TOKENS.items() if exp < now]
    for k in expired:
        del _PENDING_TOKENS[k]


async def _link_account(chat_id: int, token: str) -> None:
    _purge_expired()
    entry = _PENDING_TOKENS.pop(token, None)
    if entry is None:
        await tg.send_message(
            chat_id,
            "Invalid or expired token. Generate a new one in Convioo Settings -> Telegram.",
        )
        return
    user_id, _ = entry
    async with session_factory() as session:
        existing = (
            await session.execute(
                select(TelegramConnection).where(TelegramConnection.chat_id == chat_id)
            )
        ).scalar_one_or_none()
        if existing:
            existing.user_id = user_id
        else:
            session.add(TelegramConnection(user_id=user_id, chat_id=chat_id))
        await session.commit()
    await tg.send_message(
        chat_id, "Linked! Send /search <niche> in <region> to start searching."
    )


async def _run_search(chat_id: int, user_id: int, niche: str, region: str) -> None:
    async with session_factory() as session:
        user = await session.get(User, user_id)
        user_profile = None
        if user:
            user_profile = {
                "display_name": user.display_name or user.first_name,
                "language_code": user.language_code,
            }
        query = SearchQuery(
            id=uuid.uuid4(),
            user_id=user_id,
            niche=niche,
            region=region,
            scope="city",
            source="telegram",
        )
        session.add(query)
        await session.commit()
        query_id = query.id

    progress = TelegramProgressSink(chat_id)
    delivery = TelegramDeliverySink(chat_id)
    try:
        await run_search_with_sinks(query_id, progress, delivery, user_profile)
    except Exception:
        logger.exception(
            "telegram search failed chat_id=%s query_id=%s", chat_id, query_id
        )
        await tg.send_message(chat_id, "Search failed. Please try again.")


async def process_update(update: dict) -> None:  # type: ignore[type-arg]
    """Entry point called by the webhook route for each Telegram update."""
    message = update.get("message") or update.get("edited_message")
    if not message:
        return
    chat_id: int = message["chat"]["id"]
    text: str = (message.get("text") or "").strip()
    if not text:
        return

    if text.startswith("/start"):
        parts = text.split(None, 1)
        token = parts[1].strip() if len(parts) > 1 else ""
        if token:
            await _link_account(chat_id, token)
        else:
            await tg.send_message(
                chat_id,
                "Welcome to Convioo! Generate a link token in Settings -> Telegram "
                "to connect your account.",
            )
        return

    if text.startswith("/help"):
        await tg.send_message(
            chat_id,
            "<b>Convioo Bot</b>\n\n"
            "/search <niche> in <region> — find and score leads\n"
            "  Example: /search roofing companies in London\n\n"
            "/start <token> — link your Convioo account\n"
            "  Generate the token in Convioo Settings -> Telegram",
        )
        return

    # Resolve linked user
    async with session_factory() as session:
        conn = (
            await session.execute(
                select(TelegramConnection).where(TelegramConnection.chat_id == chat_id)
            )
        ).scalar_one_or_none()
    if conn is None:
        await tg.send_message(
            chat_id,
            "Please link your Convioo account first with /start <token>.",
        )
        return

    if text.startswith("/search"):
        query_text = text[len("/search") :].strip()
        # Parse "niche in region" — "in" is the separator
        match = re.match(r"^(.+?)\s+in\s+(.+)$", query_text, re.IGNORECASE)
        if not match:
            await tg.send_message(
                chat_id,
                "Usage: /search <niche> in <region>\nExample: /search plumbers in London",
            )
            return
        niche, region = match.group(1).strip(), match.group(2).strip()
        await tg.send_message(
            chat_id, f"Starting search: <b>{niche}</b> in <b>{region}</b>..."
        )
        spawn(_run_search(chat_id, conn.user_id, niche, region), name=f"tg-search-{chat_id}")
        return

    await tg.send_message(
        chat_id, "Use /search <niche> in <region> to search, or /help for commands."
    )
