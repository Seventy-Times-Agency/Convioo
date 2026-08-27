"""Periodic Gmail-reply tracker.

When a user opts into ``email_reply_tracking_enabled`` the worker calls
:func:`scan_replies_for_user` every few minutes. We list Gmail messages
the inbox received since the last watermark, walk the ``In-Reply-To``
header on each one, and match it to a previously-sent message we
recorded as ``LeadActivity(kind="email_sent", payload={message_id: ..."}``.
A match becomes a fresh ``LeadActivity(kind="email_replied")`` plus an
optional auto-status nudge to "replied".

The implementation keeps the I/O surface tight on purpose: the actual
Gmail History/List call lives in :mod:`leadgen.integrations.gmail`, this
module only orchestrates the scan + dedup + DB writes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.core.services.reply_classifier import classify_reply, routing_for
from leadgen.core.services.suppression import add_suppression
from leadgen.db.models import Lead, LeadActivity, User
from leadgen.integrations import gmail

logger = logging.getLogger(__name__)

# Mirror of reply_classifier's neutral verdict so we can build a payload even
# when the body fetch fails before classification runs.
_NEUTRAL_CLASSIFICATION = {
    "category": "other",
    "sentiment": "neutral",
    "confidence": 0.0,
    "summary": "",
    "suggested_reply": "",
}


def _address_from_header(raw: str | None) -> str | None:
    """Extract a bare email from a ``From:`` header like ``"Bob" <b@x.com>``."""
    if not raw:
        return None
    value = raw.strip()
    if "<" in value and ">" in value:
        value = value[value.rfind("<") + 1 : value.rfind(">")]
    value = value.strip().strip('"').strip()
    return value or None


GMAIL_LIST_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
GMAIL_GET_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/{id}"
# Cap per-tick work so a user with a huge inbox can't stall the worker.
SCAN_PAGE_SIZE = 25


class ReplyScanError(RuntimeError):
    """Raised on Gmail API failure. The worker logs and moves on."""


async def _list_recent_messages(
    access_token: str, *, after_epoch: int | None
) -> list[dict[str, str]]:
    """Return up to SCAN_PAGE_SIZE recent Gmail message metadata stubs.

    ``after_epoch`` lets us scope the query to "since the last scan" so
    a user who connected six months ago doesn't pay an O(inbox) walk
    every tick.
    """
    params: dict[str, str] = {"maxResults": str(SCAN_PAGE_SIZE)}
    if after_epoch:
        params["q"] = f"after:{after_epoch}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            GMAIL_LIST_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
    if resp.status_code != 200:
        raise ReplyScanError(
            f"gmail list returned {resp.status_code}: {resp.text[:200]}"
        )
    return list(resp.json().get("messages") or [])


async def _fetch_message_headers(
    access_token: str, message_id: str
) -> dict[str, str]:
    """Pull just the headers we care about for matching."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            GMAIL_GET_URL.format(id=message_id),
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "format": "metadata",
                "metadataHeaders": "In-Reply-To",
                # We pull References too — Gmail occasionally drops
                # In-Reply-To when the client (Outlook, mobile clients)
                # only set References.
            },
        )
    if resp.status_code != 200:
        raise ReplyScanError(
            f"gmail get returned {resp.status_code}: {resp.text[:200]}"
        )
    payload = resp.json()
    out: dict[str, str] = {}
    for h in (payload.get("payload") or {}).get("headers") or []:
        name = (h.get("name") or "").lower()
        if name in ("in-reply-to", "references", "message-id", "from"):
            out[name] = h.get("value") or ""
    out["_thread_id"] = payload.get("threadId") or ""
    return out


async def _find_outbound_activity(
    session: AsyncSession,
    *,
    user_id: int,
    rfc822_message_id: str,
) -> LeadActivity | None:
    """Look up the ``email_sent`` LeadActivity that matches a reply.

    Gmail-side IDs differ between Gmail's own ``id`` and the RFC-822
    ``Message-Id`` header. We logged Gmail's ``id`` (resp.id) in the
    payload, so this works only when the reply ``In-Reply-To`` matches
    what we sent. Mail clients commonly do this — but if a client
    rewrites the header we just won't match. Better to miss a few
    replies than to log false positives.
    """
    rows = (
        await session.execute(
            select(LeadActivity)
            .where(LeadActivity.user_id == user_id)
            .where(LeadActivity.kind == "email_sent")
        )
    ).scalars().all()
    for row in rows:
        payload = row.payload or {}
        if payload.get("message_id") and (
            payload["message_id"] == rfc822_message_id
            or payload["message_id"] in rfc822_message_id
        ):
            return row
    return None


async def scan_replies_for_user(
    session: AsyncSession,
    user: User,
    *,
    access_token: str,
) -> int:
    """Scan one user's inbox for replies. Returns # of replies recorded.

    The function itself never raises — Gmail can be flaky and the
    worker mustn't crash the whole tick because one user's token
    expired or their inbox is huge. We log + return 0 on error.
    """
    if not user.email_reply_tracking_enabled:
        return 0
    after_epoch = None
    if user.email_reply_last_checked_at:
        # On SQLite the timestamp comes back naive; ``.timestamp()`` would
        # then interpret it in local time and shift the Gmail ``after:``
        # window. Pin it to UTC when naive so the window is correct.
        last_checked = user.email_reply_last_checked_at
        if last_checked.tzinfo is None:
            last_checked = last_checked.replace(tzinfo=timezone.utc)
        after_epoch = int(last_checked.timestamp())
    try:
        stubs = await _list_recent_messages(
            access_token, after_epoch=after_epoch
        )
    except ReplyScanError as exc:
        logger.warning(
            "reply_tracker: list failed user_id=%s err=%s", user.id, exc
        )
        return 0

    new_replies = 0
    for stub in stubs:
        message_id = stub.get("id")
        if not message_id:
            continue
        try:
            headers = await _fetch_message_headers(
                access_token, message_id
            )
        except ReplyScanError as exc:
            logger.warning(
                "reply_tracker: get failed user_id=%s msg=%s err=%s",
                user.id,
                message_id,
                exc,
            )
            continue
        in_reply_to = headers.get("in-reply-to") or headers.get("references")
        if not in_reply_to:
            continue
        match = await _find_outbound_activity(
            session, user_id=user.id, rfc822_message_id=in_reply_to
        )
        if match is None:
            continue
        # Skip if we already recorded a reply for this exact reply
        # message_id. Two ticks may overlap before the watermark
        # advances. JSONB indexing differs across dialects (Postgres
        # has ``->>``, SQLite stores JSON as text), so we list and
        # filter in Python — the per-lead history is tiny.
        existing = (
            await session.execute(
                select(LeadActivity)
                .where(LeadActivity.lead_id == match.lead_id)
                .where(LeadActivity.kind == "email_replied")
            )
        ).scalars().all()
        if any(
            (a.payload or {}).get("reply_message_id") == message_id
            for a in existing
        ):
            continue

        lead = await session.get(Lead, match.lead_id)

        # Pull the full reply body once (matching above only needed headers)
        # and run it through the AI classifier. Both steps degrade to a safe
        # default so a flaky Gmail fetch or missing API key never drops the
        # reply — we just fall back to the old header-only behaviour.
        classification = dict(_NEUTRAL_CLASSIFICATION)
        sender_email = _address_from_header(headers.get("from"))
        try:
            full = await gmail.get_message(access_token, message_id)
        except Exception as exc:  # noqa: BLE001 - classification is best-effort
            logger.warning(
                "reply_tracker: body fetch failed user_id=%s msg=%s err=%s",
                user.id,
                message_id,
                exc,
            )
            full = None
        if full is not None:
            sender_email = full.get("from_email") or sender_email
            classification = await classify_reply(
                full.get("body_text") or full.get("snippet") or "",
                subject=full.get("subject"),
                lead_name=getattr(lead, "name", None),
            )

        route = routing_for(classification["category"])
        session.add(
            LeadActivity(
                lead_id=match.lead_id,
                user_id=user.id,
                kind="email_replied",
                payload={
                    "reply_message_id": message_id,
                    "reply_thread_id": headers.get("_thread_id"),
                    "from": headers.get("from"),
                    "matched_outbound_id": str(match.id),
                    "category": classification["category"],
                    "sentiment": classification["sentiment"],
                    "confidence": classification["confidence"],
                    "summary": classification["summary"],
                    "suggested_reply": classification["suggested_reply"],
                },
            )
        )

        # Route on the classification. Unsubscribe requests go straight onto
        # the do-not-contact list. Auto-replies are not genuine human replies,
        # so they never nudge the lead's status. Everything else follows the
        # routing table, but we still refuse to override a user-set terminal
        # status ("won"/"archived"/etc.) — only advance from "new"/"contacted",
        # or from "replied" when the verdict is a downgrade to "lost".
        if route["suppress"] and sender_email:
            await add_suppression(
                session,
                user_id=user.id,
                email=sender_email,
                reason="Replied asking to unsubscribe",
                source="reply",
            )
        target_status = route["lead_status"]
        if (
            lead is not None
            and not route["not_a_reply"]
            and target_status is not None
        ):
            if lead.lead_status in ("new", "contacted"):
                lead.lead_status = target_status
            elif lead.lead_status == "replied" and target_status == "lost":
                lead.lead_status = "lost"
        new_replies += 1

    await session.execute(
        update(User)
        .where(User.id == user.id)
        .values(email_reply_last_checked_at=datetime.now(timezone.utc))
    )
    await session.commit()
    return new_replies
