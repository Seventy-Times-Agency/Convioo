"""``/api/v1/inbox/*`` — unified Inbox (Wave 3).

Reads the locally-synced ``email_messages`` (populated by the worker's
``cron_inbox_sync`` and the manual ``POST /inbox/sync``), groups them
into threads, and lets the user reply in-thread through whichever
mailbox they connected.

All queries are scoped to ``current_user.id``; a thread route 404s
unless at least one message in that thread belongs to the caller.

The connection / ``needs_reconnect`` state surfaces here (rather than on
the per-provider OAuth status endpoints) so the Inbox page has a single
source of truth — the existing ``/oauth/{provider}`` status endpoints
already return ``scope`` and are left untouched.

XSS note: ``body_html`` is raw provider HTML returned verbatim. The
frontend is responsible for sandboxing it; we always include
``body_text`` so the UI can prefer the safe plain-text rendering.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.core.services.inbox_sync import (
    has_read_scope,
    sync_inbox_for_user,
)
from leadgen.core.services.oauth_store import (
    OAuthStoreError,
    ensure_fresh_token,
    get_credential,
)
from leadgen.db.models import (
    EmailMessage,
    Lead,
    LeadActivity,
    OAuthCredential,
    User,
)
from leadgen.db.session import session_factory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/inbox", tags=["inbox"])

_MAILBOX_PROVIDERS = ("gmail", "outlook")


class ReplyBody(BaseModel):
    body: str
    subject: str | None = None


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


async def _mailbox_cred(
    session: AsyncSession, user_id: int
) -> OAuthCredential | None:
    for provider in _MAILBOX_PROVIDERS:
        cred = await get_credential(
            session, user_id=user_id, provider=provider
        )
        if cred is not None:
            return cred
    return None


@router.get("/threads")
async def list_threads(
    unread: bool | None = None,
    lead_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
) -> dict:
    """List the caller's email threads, newest activity first."""
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    async with session_factory() as session:
        cred = await _mailbox_cred(session, current_user.id)
        connected = cred is not None
        provider = cred.provider if cred is not None else None
        needs_reconnect = connected and not await has_read_scope(cred)

        q = select(EmailMessage).where(
            EmailMessage.user_id == current_user.id
        )
        if lead_id:
            try:
                import uuid

                q = q.where(EmailMessage.lead_id == uuid.UUID(lead_id))
            except ValueError as exc:
                raise HTTPException(
                    status_code=400, detail="invalid lead_id"
                ) from exc
        rows = (await session.execute(q)).scalars().all()

        # Group in Python — thread counts are tiny per user and this
        # keeps the dialect-specific aggregate SQL out of the path.
        groups: dict[tuple[str, str], dict] = {}
        for m in rows:
            key = (m.provider, m.provider_thread_id)
            g = groups.get(key)
            if g is None:
                g = {
                    "thread_id": m.provider_thread_id,
                    "provider": m.provider,
                    "subject": m.subject,
                    "counterpart_email": None,
                    "lead_id": None,
                    "last_message_at": None,
                    "_last_dt": None,
                    "snippet": None,
                    "unread_count": 0,
                    "message_count": 0,
                }
                groups[key] = g
            g["message_count"] += 1
            if m.direction == "inbound" and not m.is_read:
                g["unread_count"] += 1
            if m.lead_id is not None and g["lead_id"] is None:
                g["lead_id"] = str(m.lead_id)
            # Counterpart = the non-account address on this message.
            counterpart = (
                m.to_email if m.direction == "outbound" else m.from_email
            )
            if counterpart and g["counterpart_email"] is None:
                g["counterpart_email"] = counterpart
            dt = m.message_sent_at
            if dt is not None and (
                g["_last_dt"] is None or dt > g["_last_dt"]
            ):
                g["_last_dt"] = dt
                g["last_message_at"] = _iso(dt)
                g["subject"] = m.subject
                g["snippet"] = m.snippet

        threads = list(groups.values())
        if unread is True:
            threads = [t for t in threads if t["unread_count"] > 0]
        elif unread is False:
            threads = [t for t in threads if t["unread_count"] == 0]

        # Newest activity first; threads with no timestamp sink to the end.
        threads.sort(
            key=lambda t: (
                t["_last_dt"] is not None,
                t["_last_dt"] or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )

        # Resolve lead names for the page slice only.
        page = threads[offset : offset + limit]
        lead_ids = {
            t["lead_id"] for t in page if t["lead_id"] is not None
        }
        names: dict[str, str] = {}
        if lead_ids:
            import uuid

            uid_set = {uuid.UUID(x) for x in lead_ids}
            name_rows = (
                await session.execute(
                    select(Lead.id, Lead.name).where(Lead.id.in_(uid_set))
                )
            ).all()
            names = {str(i): n for i, n in name_rows}

        out_threads = []
        for t in page:
            out_threads.append(
                {
                    "thread_id": t["thread_id"],
                    "provider": t["provider"],
                    "subject": t["subject"],
                    "counterpart_email": t["counterpart_email"],
                    "lead_id": t["lead_id"],
                    "lead_name": names.get(t["lead_id"])
                    if t["lead_id"]
                    else None,
                    "last_message_at": t["last_message_at"],
                    "snippet": t["snippet"],
                    "unread_count": t["unread_count"],
                    "message_count": t["message_count"],
                }
            )

    return {
        "connected": connected,
        "needs_reconnect": needs_reconnect,
        "provider": provider,
        "threads": out_threads,
    }


@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return one thread's messages (oldest first); mark inbound read."""
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(EmailMessage)
                .where(EmailMessage.user_id == current_user.id)
                .where(EmailMessage.provider_thread_id == thread_id)
                .order_by(EmailMessage.message_sent_at.asc())
            )
        ).scalars().all()
        if not rows:
            raise HTTPException(status_code=404, detail="thread not found")

        # Side effect: mark this thread's inbound messages read.
        await session.execute(
            update(EmailMessage)
            .where(EmailMessage.user_id == current_user.id)
            .where(EmailMessage.provider_thread_id == thread_id)
            .where(EmailMessage.direction == "inbound")
            .where(EmailMessage.is_read.is_(False))
            .values(is_read=True)
        )
        await session.commit()

        subject = next(
            (m.subject for m in rows if m.subject), None
        )
        lead_id = next(
            (str(m.lead_id) for m in rows if m.lead_id is not None), None
        )
        messages = [
            {
                "id": str(m.id),
                "direction": m.direction,
                "from_email": m.from_email,
                "to_email": m.to_email,
                "subject": m.subject,
                "body_text": m.body_text,
                "body_html": m.body_html,
                "sent_at": _iso(m.message_sent_at),
                "is_read": True if m.direction == "inbound" else m.is_read,
            }
            for m in rows
        ]

    return {
        "thread_id": thread_id,
        "subject": subject,
        "lead_id": lead_id,
        "messages": messages,
    }


@router.post("/threads/{thread_id}/reply")
async def reply_to_thread(
    thread_id: str,
    body: ReplyBody,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Send an in-thread reply to the counterpart via the connected provider."""
    if not (body.body or "").strip():
        raise HTTPException(status_code=400, detail="empty reply body")

    async with session_factory() as session:
        rows = (
            await session.execute(
                select(EmailMessage)
                .where(EmailMessage.user_id == current_user.id)
                .where(EmailMessage.provider_thread_id == thread_id)
                .order_by(EmailMessage.message_sent_at.asc())
            )
        ).scalars().all()
        if not rows:
            raise HTTPException(status_code=404, detail="thread not found")

        provider = rows[0].provider
        account_email = next(
            (m.account_email for m in rows if m.account_email), None
        )
        # Latest inbound message anchors the reply (threading + recipient).
        inbound = [m for m in rows if m.direction == "inbound"]
        anchor = inbound[-1] if inbound else rows[-1]
        recipient = (
            anchor.from_email
            if anchor.direction == "inbound"
            else anchor.to_email
        )
        if not recipient:
            raise HTTPException(
                status_code=400,
                detail="cannot determine reply recipient",
            )

        subject = body.subject or rows[-1].subject or ""
        if subject and not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        try:
            fresh = await ensure_fresh_token(
                session, user_id=current_user.id, provider=provider
            )
        except OAuthStoreError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc)
            ) from exc

        from_addr = (
            fresh.account_email or account_email or current_user.email or ""
        )

        message_id: str | None = None
        sent_thread_id: str = thread_id

        if provider == "gmail":
            from leadgen.integrations.gmail import (
                GmailError,
                build_raw_message,
                send_message,
            )

            anchor_headers = anchor.headers or {}
            rfc_msg_id = anchor_headers.get("Message-ID") or None
            references = (
                anchor_headers.get("References") or ""
            ).strip()
            if rfc_msg_id:
                references = (
                    f"{references} {rfc_msg_id}".strip()
                    if references
                    else rfc_msg_id
                )
            raw = build_raw_message(
                from_addr=from_addr,
                to_addr=recipient,
                subject=subject,
                body=body.body,
                in_reply_to=rfc_msg_id,
                references=references or None,
            )
            try:
                resp = await send_message(
                    access_token=fresh.access_token,
                    raw_message=raw,
                    thread_id=thread_id,
                )
            except GmailError as exc:
                raise HTTPException(
                    status_code=502, detail=f"gmail send failed: {exc}"
                ) from exc
            message_id = resp.get("id")
            sent_thread_id = resp.get("threadId") or thread_id
        else:  # outlook
            from leadgen.integrations.outlook import (
                OutlookError,
                reply_message,
            )

            try:
                await reply_message(
                    access_token=fresh.access_token,
                    message_id=anchor.provider_message_id,
                    comment=body.body,
                )
            except OutlookError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"outlook reply failed: {exc}",
                ) from exc
            message_id = None

        # Best-effort: store the outbound message locally so the thread
        # shows the reply immediately, and log a lead activity.
        lead_id = next(
            (m.lead_id for m in rows if m.lead_id is not None), None
        )
        now = datetime.now(timezone.utc)
        try:
            session.add(
                EmailMessage(
                    user_id=current_user.id,
                    provider=provider,
                    account_email=from_addr or None,
                    provider_thread_id=sent_thread_id,
                    provider_message_id=message_id
                    or f"local-{now.timestamp()}",
                    lead_id=lead_id,
                    direction="outbound",
                    from_email=from_addr or None,
                    to_email=recipient,
                    subject=subject or None,
                    snippet=body.body[:512],
                    body_text=body.body,
                    body_html=None,
                    message_sent_at=now,
                    is_read=True,
                    headers=None,
                )
            )
            if lead_id is not None:
                session.add(
                    LeadActivity(
                        lead_id=lead_id,
                        user_id=current_user.id,
                        kind="email_sent",
                        payload={
                            "to": recipient,
                            "subject": (subject or "")[:255],
                            "body": body.body[:4000],
                            "provider": provider,
                            "via": "inbox_reply",
                            "message_id": message_id,
                        },
                    )
                )
            await session.commit()
        except Exception:  # noqa: BLE001
            await session.rollback()
            logger.warning(
                "inbox reply: failed to persist outbound row thread=%s",
                thread_id,
                exc_info=True,
            )

    return {"ok": True, "message_id": message_id}


@router.post("/sync")
async def manual_sync(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Manual refresh — pull recent mailbox messages for the caller."""
    async with session_factory() as session:
        result = await sync_inbox_for_user(session, current_user.id)
    return {
        "synced": result.synced,
        "needs_reconnect": result.needs_reconnect,
    }
