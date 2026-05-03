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
GMAIL_USERINFO_SCOPE = "https://www.googleapis.com/auth/userinfo.email"

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


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
    scopes: tuple[str, ...] = (GMAIL_SEND_SCOPE, GMAIL_USERINFO_SCOPE),
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
) -> str:
    """Encode a plain-text email as Gmail expects (urlsafe-base64 RFC 5322)."""
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    # Gmail rejects messages whose raw field carries '=' padding —
    # strip it the way the documentation example does.
    return raw.rstrip("=")


async def send_message(
    *,
    access_token: str,
    raw_message: str,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """POST a pre-encoded message to ``users.messages.send``."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            GMAIL_SEND_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={"raw": raw_message},
        )
    if resp.status_code >= 400:
        raise GmailError(
            f"gmail send returned {resp.status_code}: {resp.text[:300]}"
        )
    try:
        return resp.json()
    except ValueError as exc:
        raise GmailError("gmail send returned non-JSON") from exc
