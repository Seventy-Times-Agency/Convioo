"""Gmail OAuth + send-as-user wrapper.

A thin alternative to ``google-auth`` + ``google-api-python-client`` —
those pull ~30 transitive deps for two HTTP calls. We hit the OAuth
token endpoint and ``users.messages.send`` directly via httpx.

Docs:
- https://developers.google.com/identity/protocols/oauth2/web-server
- https://developers.google.com/gmail/api/reference/rest/v1/users.messages/send
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

# Single OAuth scope — we only ever need to send mail on the user's
# behalf, never read or modify their inbox. Asking for less than the
# user already granted is fine; asking for more silently fails on
# subsequent requests, so be conservative.
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
# Read scope for the unified Inbox (list/get threads + messages). It is
# also what the reply-tracker needs to list messages — the old send-only
# grant could not read at all. Existing users must reconnect once to add
# this scope; the integrations status surfaces that.
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_USERINFO_SCOPE = "https://www.googleapis.com/auth/userinfo.email"

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
GMAIL_LIST_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
GMAIL_GET_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/{id}"


class GmailError(RuntimeError):
    """Raised when a Gmail / OAuth call fails or returns malformed JSON."""


@dataclass(slots=True)
class TokenSet:
    """Result of a code-exchange or refresh."""

    access_token: str
    refresh_token: str | None
    expires_at: datetime
    scope: str | None


def build_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    scopes: tuple[str, ...] = (
        GMAIL_SEND_SCOPE,
        GMAIL_READONLY_SCOPE,
        GMAIL_USERINFO_SCOPE,
    ),
) -> str:
    """Construct the consent-screen URL the SPA redirects the user to.

    ``access_type=offline`` and ``prompt=consent`` together force Google
    to issue a refresh token even when the user has previously
    authorized us — without these, refresh tokens are returned only
    on the very first authorization, which breaks anyone who
    reconnects after a token rotation.
    """
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(
    code: str,
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    timeout: float = 15.0,
) -> TokenSet:
    """Exchange an auth code for an access + refresh token pair."""
    if not (client_id and client_secret):
        raise GmailError("google oauth client credentials are missing")
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if resp.status_code != 200:
        raise GmailError(
            f"token exchange returned {resp.status_code}: {resp.text[:300]}"
        )
    payload = resp.json()
    expires_in = int(payload.get("expires_in") or 3600)
    return TokenSet(
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token"),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        scope=payload.get("scope"),
    )


async def refresh_access_token(
    refresh_token: str,
    *,
    client_id: str,
    client_secret: str,
    timeout: float = 15.0,
) -> TokenSet:
    """Use a long-lived refresh token to mint a fresh access token."""
    if not refresh_token:
        raise GmailError("missing refresh token")
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
            },
        )
    if resp.status_code != 200:
        raise GmailError(
            f"token refresh returned {resp.status_code}: {resp.text[:300]}"
        )
    payload = resp.json()
    expires_in = int(payload.get("expires_in") or 3600)
    return TokenSet(
        access_token=payload["access_token"],
        # Google does not re-issue the refresh token on a refresh call;
        # the caller keeps the existing one.
        refresh_token=None,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        scope=payload.get("scope"),
    )


async def fetch_account_email(
    access_token: str, *, timeout: float = 15.0
) -> str | None:
    """Look up the user's authoritative Gmail address.

    The ``access_token`` from the consent flow doesn't carry the
    address; this is the one extra round-trip we need so the UI can
    show "Connected as [email protected]".
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        return None
    try:
        return resp.json().get("email")
    except ValueError:
        return None


def build_raw_message(
    *,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
    html_body: str | None = None,
    in_reply_to: str | None = None,
    references: str | None = None,
) -> str:
    """Encode an email as Gmail expects (urlsafe-base64 RFC 5322).

    When *html_body* is provided the message is multipart/alternative
    with both a plain-text and an HTML part.

    ``in_reply_to`` / ``references`` (keyword-only, default ``None``)
    set the RFC 5322 threading headers so a reply lands in the same
    conversation client-side — pair them with the ``threadId`` passed
    to :func:`send_message`. Existing callers that omit them are
    unaffected.
    """
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    msg.set_content(body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    # Gmail rejects messages whose raw field carries '=' padding —
    # strip it the way the documentation example does.
    return raw.rstrip("=")


async def send_message(
    *,
    access_token: str,
    raw_message: str,
    thread_id: str | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """POST a pre-encoded message to ``users.messages.send``.

    When ``thread_id`` is given Gmail appends the message to that
    conversation server-side (it still needs the In-Reply-To header,
    baked into ``raw_message``, to thread correctly in other clients).
    """
    payload: dict[str, Any] = {"raw": raw_message}
    if thread_id:
        payload["threadId"] = thread_id
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            GMAIL_SEND_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
    if resp.status_code >= 400:
        raise GmailError(
            f"gmail send returned {resp.status_code}: {resp.text[:300]}"
        )
    try:
        return resp.json()
    except ValueError as exc:
        raise GmailError("gmail send returned non-JSON") from exc


# ── Inbox read helpers ─────────────────────────────────────────────────


def _parse_address(raw: str | None) -> str | None:
    """Pull the bare ``a@b`` out of a ``Name <a@b>`` header value."""
    if not raw:
        return None
    from email.utils import parseaddr

    addr = parseaddr(raw)[1]
    return addr or None


def _parse_date(raw: str | None) -> datetime | None:
    """Parse an RFC 2822 ``Date`` header into an aware UTC datetime."""
    if not raw:
        return None
    from email.utils import parsedate_to_datetime

    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _decode_b64url(data: str | None) -> str:
    """Decode a Gmail urlsafe-base64 part body to text, lenient on pad."""
    if not data:
        return ""
    padded = data + "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode(
            "utf-8", errors="replace"
        )
    except (ValueError, UnicodeDecodeError):
        return ""


def _strip_html(html: str) -> str:
    """Crude tag strip so an HTML-only message still yields some text."""
    import re

    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _walk_parts(payload: dict[str, Any]) -> tuple[str, str]:
    """Return ``(text_plain, text_html)`` collected from a Gmail payload."""
    text_plain = ""
    text_html = ""

    def _visit(part: dict[str, Any]) -> None:
        nonlocal text_plain, text_html
        mime = (part.get("mimeType") or "").lower()
        body = part.get("body") or {}
        data = body.get("data")
        if mime == "text/plain" and data and not text_plain:
            text_plain = _decode_b64url(data)
        elif mime == "text/html" and data and not text_html:
            text_html = _decode_b64url(data)
        for child in part.get("parts") or []:
            _visit(child)

    _visit(payload)
    return text_plain, text_html


async def list_message_ids(
    access_token: str,
    *,
    after_epoch: int | None = None,
    max_results: int = 100,
    timeout: float = 15.0,
) -> list[str]:
    """Return recent Gmail message ids (newest first).

    ``after_epoch`` scopes the query to "since" via the Gmail ``q``
    operator so a fresh sync doesn't walk the whole inbox.
    """
    params: dict[str, str] = {"maxResults": str(max_results)}
    if after_epoch:
        params["q"] = f"after:{after_epoch}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(
            GMAIL_LIST_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
    if resp.status_code != 200:
        raise GmailError(
            f"gmail list returned {resp.status_code}: {resp.text[:200]}"
        )
    out: list[str] = []
    for stub in resp.json().get("messages") or []:
        mid = stub.get("id")
        if mid:
            out.append(mid)
    return out


async def get_message(
    access_token: str,
    msg_id: str,
    *,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Fetch + parse a single Gmail message into the unified shape.

    Returns a dict with ``provider_message_id``, ``thread_id``,
    ``from_email``, ``to_email``, ``subject``, ``snippet``,
    ``body_text``, ``body_html``, ``message_sent_at`` (aware datetime),
    ``headers`` (Message-ID / In-Reply-To / References) and
    ``direction`` ("outbound" when the SENT label is present).
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(
            GMAIL_GET_URL.format(id=msg_id),
            headers={"Authorization": f"Bearer {access_token}"},
            params={"format": "full"},
        )
    if resp.status_code != 200:
        raise GmailError(
            f"gmail get returned {resp.status_code}: {resp.text[:200]}"
        )
    payload = resp.json()
    msg_payload = payload.get("payload") or {}
    raw_headers = {
        (h.get("name") or "").lower(): h.get("value") or ""
        for h in msg_payload.get("headers") or []
    }
    text_plain, text_html = _walk_parts(msg_payload)
    if not text_plain and text_html:
        text_plain = _strip_html(text_html)
    label_ids = payload.get("labelIds") or []
    direction = "outbound" if "SENT" in label_ids else "inbound"
    return {
        "provider_message_id": payload.get("id") or msg_id,
        "thread_id": payload.get("threadId") or "",
        "from_email": _parse_address(raw_headers.get("from")),
        "to_email": _parse_address(raw_headers.get("to")),
        "subject": raw_headers.get("subject") or None,
        "snippet": payload.get("snippet") or None,
        "body_text": text_plain or None,
        "body_html": text_html or None,
        "message_sent_at": _parse_date(raw_headers.get("date")),
        "headers": {
            "Message-ID": raw_headers.get("message-id") or "",
            "In-Reply-To": raw_headers.get("in-reply-to") or "",
            "References": raw_headers.get("references") or "",
        },
        "direction": direction,
        "is_read": "UNREAD" not in label_ids,
    }
