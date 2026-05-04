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
OUTLOOK_SCOPES = (
    "Mail.Send",
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
    timeout: float = 15.0,
) -> dict[str, str]:
    """POST a message via Microsoft Graph ``users/me/sendMail``.

    Graph wraps the message in a small envelope and saves the sent
    item to the user's Sent folder by default. We don't ask Graph to
    return the message ID because ``sendMail`` returns 202 with no
    body; the caller uses the request itself as the activity record.
    """
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
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
