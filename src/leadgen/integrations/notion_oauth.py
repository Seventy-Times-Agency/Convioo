"""Notion public OAuth helpers (authorization code flow).

Notion docs:
- https://developers.notion.com/docs/authorization
- https://developers.notion.com/reference/create-a-token

The access token Notion issues never expires and has no refresh token.
We store it in ``user_integration_credentials`` (Fernet-encrypted) the
same way internal integration tokens are stored, so the rest of the
export pipeline is unaware of which auth method was used.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import logging
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

NOTION_AUTHORIZE_URL = "https://api.notion.com/v1/oauth/authorize"
NOTION_TOKEN_URL = "https://api.notion.com/v1/oauth/token"
NOTION_API_VERSION = "2022-06-28"

# How long an unredeemed authorize-state stays valid. The user has to
# click "Allow" inside Notion within this window or the callback will
# reject the state. Notion's own consent screen rarely takes more than
# a minute or two, so 15 min is a generous human-time budget.
STATE_TTL_SEC = 15 * 60


class NotionOAuthError(RuntimeError):
    """Raised when Notion's OAuth endpoints return an error."""


class StateValidationError(NotionOAuthError):
    """Raised when the OAuth ``state`` parameter is malformed, tampered
    with, or has expired. The caller should treat this as a 400."""


def issue_state(user_id: int, *, secret: str) -> str:
    """Mint a signed, time-stamped state token for the OAuth handshake.

    Format: ``"{user_id}:{nonce}:{ts}:{signature}"`` where ``signature``
    is a hex HMAC-SHA256 of ``"{user_id}:{nonce}:{ts}"`` keyed by the
    server-side ``secret``. The state is verified on the callback by
    ``verify_state``; we never store it server-side.

    Why signed-state instead of a DB-backed nonce table:
    1. Stateless — works across replicas without sticky sessions.
    2. The ``user_id`` is bound by the signature, so an attacker who
       crafts ``"{victim_id}:..."`` can't forge a callback that writes
       a Notion token under the victim's account (CVE-grade if missing).
    3. ``ts`` lets us reject stale states without any GC.
    """
    if not secret:
        # Refuse to mint a state when the signing key is empty —
        # otherwise verification trivially passes for any forgery.
        raise StateValidationError(
            "OAuth state secret is not configured (AUTH_JWT_SECRET)."
        )
    nonce = secrets.token_urlsafe(12)
    ts = str(int(time.time()))
    payload = f"{user_id}:{nonce}:{ts}"
    signature = hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"{payload}:{signature}"


def verify_state(state: str, *, secret: str, max_age_sec: int = STATE_TTL_SEC) -> int:
    """Return the ``user_id`` embedded in a valid state, or raise.

    Validates the HMAC signature with constant-time comparison and the
    timestamp window. Any malformed input, signature mismatch, or
    expiry raises ``StateValidationError`` so the caller can return a
    uniform 400.
    """
    if not secret:
        raise StateValidationError(
            "OAuth state secret is not configured (AUTH_JWT_SECRET)."
        )
    if not state:
        raise StateValidationError("missing state")
    parts = state.split(":")
    if len(parts) != 4:
        raise StateValidationError("malformed state")
    user_id_str, nonce, ts_str, signature = parts
    if not nonce:
        raise StateValidationError("malformed state")
    payload = f"{user_id_str}:{nonce}:{ts_str}"
    expected = hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise StateValidationError("state signature mismatch")
    try:
        user_id = int(user_id_str)
        ts = int(ts_str)
    except ValueError as exc:
        raise StateValidationError("state numeric fields") from exc
    age = int(time.time()) - ts
    if age < 0 or age > max_age_sec:
        raise StateValidationError("state expired")
    return user_id


@dataclass(slots=True)
class NotionOAuthToken:
    access_token: str
    workspace_id: str
    workspace_name: str | None
    workspace_icon: str | None
    owner_email: str | None


def build_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
) -> str:
    """Return the Notion consent URL the frontend redirects to."""
    params = {
        "client_id": client_id,
        "response_type": "code",
        "owner": "user",
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{NOTION_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code_for_token(
    code: str,
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    timeout: float = 15.0,
) -> NotionOAuthToken:
    """Exchange an authorization code for an access token.

    Notion uses HTTP Basic auth for the token endpoint (client_id +
    client_secret encoded as Base64) rather than passing credentials
    in the request body.
    """
    if not (client_id and client_secret):
        raise NotionOAuthError("notion oauth client credentials are missing")

    credentials = base64.b64encode(
        f"{client_id}:{client_secret}".encode()
    ).decode()

    async with httpx.AsyncClient(timeout=timeout) as http:
        resp = await http.post(
            NOTION_TOKEN_URL,
            headers={
                "Authorization": f"Basic {credentials}",
                "Notion-Version": NOTION_API_VERSION,
                "Content-Type": "application/json",
            },
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )

    if resp.status_code != 200:
        body = resp.text[:300]
        raise NotionOAuthError(
            f"Notion token exchange failed ({resp.status_code}): {body}"
        )

    data = resp.json()
    if "access_token" not in data:
        raise NotionOAuthError(f"unexpected token response: {data}")

    owner_email: str | None = None
    with contextlib.suppress(AttributeError, TypeError):
        owner_email = (
            data.get("owner", {})
            .get("user", {})
            .get("person", {})
            .get("email")
        )

    return NotionOAuthToken(
        access_token=data["access_token"],
        workspace_id=data.get("workspace_id", ""),
        workspace_name=data.get("workspace_name"),
        workspace_icon=data.get("workspace_icon"),
        owner_email=owner_email,
    )
