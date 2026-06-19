"""Outlook / Microsoft Graph OAuth + send-as-user wrapper.

Mirrors :mod:`leadgen.integrations.gmail` so the rest of the platform
(``oauth_store`` token refresh, the ``/leads/{id}/send-email`` route
handler, the reply-tracker worker tick) treats both providers
interchangeably. The OAuth dance is the standard Microsoft v2 flow on
the ``common`` tenant — works for personal accounts (outlook.com,
hotmail) and work accounts (Microsoft 365). Send is the Graph
``/me/sendMail`` endpoint.

Docs:
- https://learn.microsoft.com/graph/auth-v2-user
- https://learn.microsoft.com/graph/api/user-sendmail
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

# We ask only for ``Mail.Send`` (compose + send) plus ``offline_access``
# so Microsoft issues a refresh token. ``User.Read`` lets us grab the
# authoritative mailbox address for the "Connected as ..." UI.
# ``Mail.Read`` powers the unified Inbox (list/get messages + threads).
# Existing users connected with the send-only grant must reconnect once
# to add it; the integrations status surfaces that.
OUTLOOK_SCOPES = (
    "Mail.Send",
    "Mail.Read",
    "User.Read",
    "offline_access",
)

OUTLOOK_AUTH_URL = (
    "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
)
OUTLOOK_TOKEN_URL = (
    "https://login.microsoftonline.com/common/oauth2/v2.0/token"
)
OUTLOOK_USERINFO_URL = "https://graph.microsoft.com/v1.0/me"
OUTLOOK_SEND_URL = "https://graph.microsoft.com/v1.0/me/sendMail"
OUTLOOK_MESSAGES_URL = "https://graph.microsoft.com/v1.0/me/messages"
OUTLOOK_REPLY_URL = (
    "https://graph.microsoft.com/v1.0/me/messages/{id}/reply"
)


class OutlookError(RuntimeError):
    """Raised when Microsoft Graph / OAuth returns an error or bad JSON."""


@dataclass(slots=True)
class TokenSet:
    access_token: str
    refresh_token: str | None
    expires_at: datetime
    scope: str | None


def build_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    scopes: tuple[str, ...] = OUTLOOK_SCOPES,
) -> str:
    """Construct the v2 consent URL the SPA redirects the user to."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "response_mode": "query",
        "scope": " ".join(scopes),
        "state": state,
        # ``prompt=consent`` mirrors the Gmail flag — guarantees a
        # refresh token even when the user previously consented.
        "prompt": "consent",
    }
    return f"{OUTLOOK_AUTH_URL}?{urlencode(params)}"


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
        raise OutlookError("microsoft oauth client credentials are missing")
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            OUTLOOK_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "scope": " ".join(OUTLOOK_SCOPES),
            },
        )
    if resp.status_code != 200:
        raise OutlookError(
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
        raise OutlookError("missing refresh token")
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            OUTLOOK_TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "scope": " ".join(OUTLOOK_SCOPES),
            },
        )
    if resp.status_code != 200:
        raise OutlookError(
            f"token refresh returned {resp.status_code}: {resp.text[:300]}"
        )
    payload = resp.json()
    expires_in = int(payload.get("expires_in") or 3600)
    # Microsoft DOES rotate refresh tokens on each refresh — the new
    # one supersedes the old. Keep both, the caller decides.
    return TokenSet(
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token"),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        scope=payload.get("scope"),
    )


async def fetch_account_email(
    access_token: str, *, timeout: float = 15.0
) -> str | None:
    """Look up the user's authoritative Outlook / mailbox address."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(
            OUTLOOK_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        return None
    try:
        body = resp.json()
    except ValueError:
        return None
    return body.get("mail") or body.get("userPrincipalName")


async def send_message(
    *,
    access_token: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
    html_body: str | None = None,
    timeout: float = 15.0,
) -> dict[str, str]:
    """POST a message via Microsoft Graph ``users/me/sendMail``.

    Graph wraps the message in a small envelope and saves the sent
    item to the user's Sent folder by default. We don't ask Graph to
    return the message ID because ``sendMail`` returns 202 with no
    body; the caller uses the request itself as the activity record.
    When *html_body* is provided the message is sent as HTML.
    """
    content_type = "HTML" if html_body else "Text"
    content = html_body if html_body else body
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": content_type, "content": content},
            "toRecipients": [
                {"emailAddress": {"address": to_addr}},
            ],
        },
        "saveToSentItems": True,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            OUTLOOK_SEND_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
    if resp.status_code >= 400:
        raise OutlookError(
            f"outlook send returned {resp.status_code}: {resp.text[:300]}"
        )
    # Graph returns 202 + empty body on success.
    return {"from": from_addr, "to": to_addr, "subject": subject}


# ── Inbox read helpers ─────────────────────────────────────────────────


def _parse_graph_datetime(raw: str | None) -> datetime | None:
    """Parse a Graph ISO-8601 timestamp into an aware UTC datetime."""
    if not raw:
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _strip_html(html: str) -> str:
    """Crude tag strip so an HTML-only Graph message still yields text."""
    import re

    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_message(raw: dict, *, account_email: str | None) -> dict:
    """Normalize one Graph ``message`` resource into the unified shape.

    ``direction`` is "outbound" when the sender address matches the
    connected mailbox, else "inbound".
    """
    sender = (
        (raw.get("from") or raw.get("sender") or {}).get("emailAddress") or {}
    )
    from_email = (sender.get("address") or "").strip() or None
    to_recipients = raw.get("toRecipients") or []
    to_email: str | None = None
    if to_recipients:
        first = (to_recipients[0].get("emailAddress") or {}).get("address")
        to_email = (first or "").strip() or None

    body = raw.get("body") or {}
    content = body.get("content") or ""
    content_type = (body.get("contentType") or "").lower()
    if content_type == "html":
        body_html: str | None = content or None
        body_text: str | None = (
            _strip_html(content) if content else None
        ) or (raw.get("bodyPreview") or None)
    else:
        body_html = None
        body_text = content or (raw.get("bodyPreview") or None)

    direction = "inbound"
    if (
        account_email
        and from_email
        and from_email.lower() == account_email.lower()
    ):
        direction = "outbound"

    return {
        "provider_message_id": raw.get("id") or "",
        "thread_id": raw.get("conversationId") or "",
        "from_email": from_email,
        "to_email": to_email,
        "subject": raw.get("subject") or None,
        "snippet": raw.get("bodyPreview") or None,
        "body_text": body_text,
        "body_html": body_html,
        "message_sent_at": _parse_graph_datetime(
            raw.get("sentDateTime") or raw.get("receivedDateTime")
        ),
        "headers": {
            "Message-ID": raw.get("internetMessageId") or "",
            "In-Reply-To": "",
            "References": "",
        },
        "direction": direction,
        "is_read": bool(raw.get("isRead")),
    }


async def list_messages(
    access_token: str,
    *,
    since: datetime | None = None,
    account_email: str | None = None,
    top: int = 100,
    timeout: float = 20.0,
) -> list[dict]:
    """List recent Graph messages, newest first, parsed into the shape.

    ``since`` adds a ``$filter`` on ``receivedDateTime ge`` so a fresh
    sync stays bounded. Bad individual messages are skipped, not fatal.
    """
    params: dict[str, str] = {
        "$top": str(top),
        "$orderby": "receivedDateTime desc",
        "$select": (
            "id,conversationId,internetMessageId,from,sender,toRecipients,"
            "subject,bodyPreview,body,sentDateTime,receivedDateTime,isRead"
        ),
    }
    if since is not None:
        stamp = since.astimezone(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        params["$filter"] = f"receivedDateTime ge {stamp}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(
            OUTLOOK_MESSAGES_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
    if resp.status_code != 200:
        raise OutlookError(
            f"outlook list returned {resp.status_code}: {resp.text[:200]}"
        )
    out: list[dict] = []
    for raw in resp.json().get("value") or []:
        try:
            out.append(parse_message(raw, account_email=account_email))
        except Exception as exc:  # noqa: BLE001
            logger.warning("outlook: skipping bad message err=%s", exc)
            continue
    return out


async def reply_message(
    *,
    access_token: str,
    message_id: str,
    comment: str,
    timeout: float = 20.0,
) -> None:
    """Reply in-thread via Graph ``/messages/{id}/reply``.

    Graph composes a reply to the original message and threads it
    automatically (sets In-Reply-To / References for us). Returns 202
    with no body on success.
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            OUTLOOK_REPLY_URL.format(id=message_id),
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={"comment": comment},
        )
    if resp.status_code >= 400:
        raise OutlookError(
            f"outlook reply returned {resp.status_code}: {resp.text[:300]}"
        )
