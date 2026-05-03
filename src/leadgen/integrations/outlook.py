"""Outlook (Microsoft Graph) OAuth + send-as-user wrapper.

Mirrors the gmail.py contract so the web API routes and worker code
can call either provider through the same interface.

Docs:
- https://learn.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-auth-code-flow
- https://learn.microsoft.com/en-us/graph/api/user-sendmail
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

OUTLOOK_SEND_SCOPE = "https://graph.microsoft.com/Mail.Send"
OUTLOOK_READ_SCOPE = "https://graph.microsoft.com/Mail.Read"
OUTLOOK_USERINFO_SCOPE = "openid email profile offline_access"

MS_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MS_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
MS_GRAPH_ME_URL = "https://graph.microsoft.com/v1.0/me"
MS_GRAPH_SEND_URL = "https://graph.microsoft.com/v1.0/me/sendMail"
MS_GRAPH_MESSAGES_URL = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"


class OutlookError(RuntimeError):
    """Raised when a Microsoft Graph / OAuth call fails."""


@dataclass(slots=True)
class OutlookTokenSet:
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
        OUTLOOK_SEND_SCOPE,
        OUTLOOK_READ_SCOPE,
        OUTLOOK_USERINFO_SCOPE,
    ),
) -> str:
    """Construct the Microsoft consent-screen URL."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "state": state,
        "response_mode": "query",
    }
    return f"{MS_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(
    code: str,
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    timeout: float = 15.0,
) -> OutlookTokenSet:
    """Exchange an auth code for an access + refresh token pair."""
    if not (client_id and client_secret):
        raise OutlookError("outlook oauth client credentials are missing")
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            MS_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if resp.status_code != 200:
        raise OutlookError(
            f"token exchange returned {resp.status_code}: {resp.text[:300]}"
        )
    payload = resp.json()
    expires_in = int(payload.get("expires_in") or 3600)
    return OutlookTokenSet(
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
    redirect_uri: str = "",
    timeout: float = 15.0,
) -> OutlookTokenSet:
    """Use a refresh token to mint a fresh access token."""
    if not refresh_token:
        raise OutlookError("missing refresh token")
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            MS_TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
            },
        )
    if resp.status_code != 200:
        raise OutlookError(
            f"token refresh returned {resp.status_code}: {resp.text[:300]}"
        )
    payload = resp.json()
    expires_in = int(payload.get("expires_in") or 3600)
    return OutlookTokenSet(
        access_token=payload["access_token"],
        # MS does re-issue a new refresh token on refresh — keep it.
        refresh_token=payload.get("refresh_token"),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        scope=payload.get("scope"),
    )


async def fetch_account_email(
    access_token: str, *, timeout: float = 15.0
) -> str | None:
    """Look up the user's authoritative mailbox address from /me."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(
            MS_GRAPH_ME_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        return None
    try:
        data = resp.json()
        return data.get("mail") or data.get("userPrincipalName")
    except ValueError:
        return None


async def send_message(
    *,
    access_token: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Send an email via Microsoft Graph ``/me/sendMail``.

    Returns an empty dict on success (Graph returns 202 No Content).
    """
    payload = {
        "message": {
            "subject": subject,
            "from": {"emailAddress": {"address": from_addr}},
            "toRecipients": [{"emailAddress": {"address": to_addr}}],
            "body": {"contentType": "Text", "content": body},
        },
        "saveToSentItems": True,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            MS_GRAPH_SEND_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
    if resp.status_code not in (200, 202):
        raise OutlookError(
            f"graph sendMail returned {resp.status_code}: {resp.text[:300]}"
        )
    # Graph returns 202 with no body on success.
    return {}


async def list_inbox_messages(
    access_token: str,
    *,
    since: datetime | None = None,
    max_results: int = 50,
    timeout: float = 15.0,
) -> list[dict[str, Any]]:
    """List recent inbox messages with internetMessageHeaders.

    Returns an empty list on 403 (scope too narrow) so callers degrade
    gracefully when the user only granted Mail.Send.
    """
    params: dict[str, Any] = {
        "$top": max_results,
        "$select": "id,internetMessageId,internetMessageHeaders,receivedDateTime",
        "$orderby": "receivedDateTime desc",
    }
    if since is not None:
        params["$filter"] = (
            f"receivedDateTime ge {since.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        )
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(
            MS_GRAPH_MESSAGES_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
    if resp.status_code == 403:
        logger.debug("outlook.list_inbox_messages: 403 (scope too narrow)")
        return []
    if resp.status_code != 200:
        raise OutlookError(
            f"graph messages returned {resp.status_code}: {resp.text[:200]}"
        )
    try:
        return resp.json().get("value") or []
    except ValueError as exc:
        raise OutlookError("graph messages returned non-JSON") from exc
