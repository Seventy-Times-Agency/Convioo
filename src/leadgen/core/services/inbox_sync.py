"""Unified-Inbox sync — pull a user's mailbox into ``email_messages``.

Wave 3. Once a user connects Gmail (with ``gmail.readonly``) or Outlook
(with ``Mail.Read``) we mirror recent messages into the local
``email_messages`` table so the Inbox UI can render threads without a
live provider round-trip per page load and so a reply can be threaded
correctly.

Idempotency comes from the unique constraint on
``(user_id, provider, provider_message_id)``: a re-sync upserts rather
than duplicating. We deliberately *don't* track a per-message watermark
column — instead we re-scan a fixed recent window (``SYNC_WINDOW_DAYS``)
each tick and let the upsert dedup. That is simpler than a watermark and
correct under overlapping ticks; the window keeps it cheap. (The reply
tracker's ``User.email_reply_last_checked_at`` is a *separate* marker for
a different feature and is left untouched here.)

The whole sync is defensive: a single malformed message is logged and
skipped, never aborting the run, mirroring the reply-tracker's contract.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.core.services.oauth_store import (
    OAuthStoreError,
    ensure_fresh_token,
    get_credential,
)
from leadgen.db.models import EmailMessage, Lead, OAuthCredential, SearchQuery
from leadgen.integrations import gmail as gmail_mod
from leadgen.integrations import outlook as outlook_mod

logger = logging.getLogger(__name__)

# Providers that have a mailbox we can read, in preference order.
_MAILBOX_PROVIDERS = ("gmail", "outlook")
# How far back a sync looks. The unique constraint makes re-scans cheap
# and idempotent, so we re-walk this window every tick instead of
# threading a watermark.
SYNC_WINDOW_DAYS = 30
# Hard cap on messages fetched + parsed per sync so a huge inbox can't
# stall the worker.
MAX_MESSAGES = 200
# Commit every N upserts so a long sync doesn't hold one fat transaction.
_BATCH_SIZE = 25


@dataclass(slots=True)
class SyncResult:
    """Outcome of one user's inbox sync."""

    synced: int
    needs_reconnect: bool


def _scope_has(scope: str | None, needle: str) -> bool:
    return bool(scope) and needle in scope


async def has_read_scope(cred: OAuthCredential | None) -> bool:
    """True when the stored grant can read the mailbox.

    Gmail needs ``gmail.readonly``; Outlook needs ``Mail.Read``. Users
    who connected with the old send-only grant return False and must
    reconnect once to add the read scope.
    """
    if cred is None:
        return False
    if cred.provider == "gmail":
        return _scope_has(cred.scope, "gmail.readonly")
    if cred.provider == "outlook":
        # Graph reports granted scopes lower-cased in some flows.
        scope = (cred.scope or "").lower()
        return "mail.read" in scope
    return False


async def _connected_mailbox(
    session: AsyncSession, user_id: int
) -> OAuthCredential | None:
    """Return the user's first connected mailbox credential, if any."""
    for provider in _MAILBOX_PROVIDERS:
        cred = await get_credential(
            session, user_id=user_id, provider=provider
        )
        if cred is not None:
            return cred
    return None


async def _match_lead_id(
    session: AsyncSession, user_id: int, counterpart: str | None
) -> uuid.UUID | None:
    """Best-effort map an email address to one of the user's leads.

    Matches on ``Lead.contact_email`` (case-insensitive). Leads belong
    to a user through their ``SearchQuery``; we join on that so we never
    leak another user's lead. Returns ``None`` when nothing matches.
    """
    if not counterpart:
        return None
    addr = counterpart.strip().lower()
    if "@" not in addr:
        return None
    row = (
        await session.execute(
            select(Lead.id)
            .join(SearchQuery, SearchQuery.id == Lead.query_id)
            .where(SearchQuery.user_id == user_id)
            .where(Lead.deleted_at.is_(None))
            .where(func.lower(Lead.contact_email) == addr)
            .limit(1)
        )
    ).scalar_one_or_none()
    return row


def _counterpart_email(parsed: dict, account_email: str | None) -> str | None:
    """The non-account address on a message (who we talked to)."""
    acct = (account_email or "").strip().lower()
    from_email = parsed.get("from_email")
    to_email = parsed.get("to_email")
    if parsed.get("direction") == "outbound":
        return to_email
    # inbound: counterpart is the sender, unless it's us (rare)
    if from_email and from_email.strip().lower() != acct:
        return from_email
    return to_email


async def _upsert_message(
    session: AsyncSession,
    *,
    user_id: int,
    provider: str,
    account_email: str | None,
    parsed: dict,
) -> bool:
    """Insert a new ``email_messages`` row or update a known one.

    Returns True when a row was inserted or meaningfully updated.
    Keyed by the unique ``(user_id, provider, provider_message_id)``.
    """
    provider_message_id = parsed.get("provider_message_id")
    if not provider_message_id:
        return False

    existing = (
        await session.execute(
            select(EmailMessage)
            .where(EmailMessage.user_id == user_id)
            .where(EmailMessage.provider == provider)
            .where(
                EmailMessage.provider_message_id == provider_message_id
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        # Only the volatile bits can change on a re-sync.
        changed = False
        new_read = bool(parsed.get("is_read", existing.is_read))
        if existing.is_read != new_read:
            existing.is_read = new_read
            changed = True
        if parsed.get("snippet") and existing.snippet != parsed["snippet"]:
            existing.snippet = parsed["snippet"]
            changed = True
        return changed

    counterpart = _counterpart_email(parsed, account_email)
    lead_id = await _match_lead_id(session, user_id, counterpart)
    session.add(
        EmailMessage(
            user_id=user_id,
            provider=provider,
            account_email=account_email,
            provider_thread_id=parsed.get("thread_id") or "",
            provider_message_id=provider_message_id,
            lead_id=lead_id,
            direction=parsed.get("direction") or "inbound",
            from_email=parsed.get("from_email"),
            to_email=parsed.get("to_email"),
            subject=parsed.get("subject"),
            snippet=parsed.get("snippet"),
            body_text=parsed.get("body_text"),
            body_html=parsed.get("body_html"),
            message_sent_at=parsed.get("message_sent_at"),
            is_read=bool(parsed.get("is_read", False)),
            headers=parsed.get("headers"),
        )
    )
    return True


async def sync_inbox_for_user(
    session: AsyncSession, user_id: int
) -> SyncResult:
    """Pull recent mailbox messages for one user into ``email_messages``.

    Returns a :class:`SyncResult`. When the connected mailbox lacks the
    read scope (or nothing is connected) we no-op and flag
    ``needs_reconnect`` so the UI can prompt a one-time reconnect.
    """
    cred = await _connected_mailbox(session, user_id)
    if cred is None:
        return SyncResult(synced=0, needs_reconnect=False)
    if not await has_read_scope(cred):
        return SyncResult(synced=0, needs_reconnect=True)

    provider = cred.provider
    try:
        fresh = await ensure_fresh_token(
            session, user_id=user_id, provider=provider
        )
    except OAuthStoreError as exc:
        logger.info(
            "inbox_sync: token unavailable user_id=%s provider=%s err=%s",
            user_id,
            provider,
            exc,
        )
        return SyncResult(synced=0, needs_reconnect=True)

    account_email = fresh.account_email or cred.account_email
    since = datetime.now(timezone.utc) - timedelta(days=SYNC_WINDOW_DAYS)
    synced = 0
    pending = 0

    if provider == "gmail":
        try:
            ids = await gmail_mod.list_message_ids(
                fresh.access_token,
                after_epoch=int(since.timestamp()),
                max_results=MAX_MESSAGES,
            )
        except gmail_mod.GmailError as exc:
            logger.warning(
                "inbox_sync: gmail list failed user_id=%s err=%s",
                user_id,
                exc,
            )
            return SyncResult(synced=0, needs_reconnect=False)
        for msg_id in ids[:MAX_MESSAGES]:
            try:
                parsed = await gmail_mod.get_message(
                    fresh.access_token, msg_id
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "inbox_sync: gmail get failed user_id=%s msg=%s err=%s",
                    user_id,
                    msg_id,
                    exc,
                )
                continue
            try:
                if await _upsert_message(
                    session,
                    user_id=user_id,
                    provider=provider,
                    account_email=account_email,
                    parsed=parsed,
                ):
                    synced += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "inbox_sync: gmail upsert failed user_id=%s err=%s",
                    user_id,
                    exc,
                )
                continue
            pending += 1
            if pending >= _BATCH_SIZE:
                await session.commit()
                pending = 0
    else:  # outlook
        try:
            messages = await outlook_mod.list_messages(
                fresh.access_token,
                since=since,
                account_email=account_email,
                top=MAX_MESSAGES,
            )
        except outlook_mod.OutlookError as exc:
            logger.warning(
                "inbox_sync: outlook list failed user_id=%s err=%s",
                user_id,
                exc,
            )
            return SyncResult(synced=0, needs_reconnect=False)
        for parsed in messages[:MAX_MESSAGES]:
            try:
                if await _upsert_message(
                    session,
                    user_id=user_id,
                    provider=provider,
                    account_email=account_email,
                    parsed=parsed,
                ):
                    synced += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "inbox_sync: outlook upsert failed user_id=%s err=%s",
                    user_id,
                    exc,
                )
                continue
            pending += 1
            if pending >= _BATCH_SIZE:
                await session.commit()
                pending = 0

    await session.commit()
    return SyncResult(synced=synced, needs_reconnect=False)
