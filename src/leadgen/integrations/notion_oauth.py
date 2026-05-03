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
import logging
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

NOTION_AUTHORIZE_URL = "https://api.notion.com/v1/oauth/authorize"
NOTION_TOKEN_URL = "https://api.notion.com/v1/oauth/token"
NOTION_API_VERSION = "2022-06-28"


class NotionOAuthError(RuntimeError):
    """Raised when Notion's OAuth endpoints return an error."""


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
    try:
        owner_email = (
            data.get("owner", {})
            .get("user", {})
            .get("person", {})
            .get("email")
        )
    except (AttributeError, TypeError):
        pass

    return NotionOAuthToken(
        access_token=data["access_token"],
        workspace_id=data.get("workspace_id", ""),
        workspace_name=data.get("workspace_name"),
        workspace_icon=data.get("workspace_icon"),
        owner_email=owner_email,
    )
