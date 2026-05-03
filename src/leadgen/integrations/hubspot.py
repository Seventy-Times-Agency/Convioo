"""HubSpot OAuth + CRM contact wrapper.

Mirrors the shape of ``integrations/gmail.py`` so the route layer
can register both providers through the shared ``oauth_store``.
Three concerns live in this module: building the consent URL,
exchanging / refreshing tokens, and the upsert-contact call used by
the bulk export endpoint.

Docs:
- https://developers.hubspot.com/docs/api/oauth-quickstart-guide
- https://developers.hubspot.com/docs/api/crm/contacts
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

# HubSpot's smallest scope set that lets us search by email and create
# contacts. Asking for more silently fails portals on the free tier.
HUBSPOT_SCOPES = (
    "crm.objects.contacts.write",
    "crm.objects.contacts.read",
)

HUBSPOT_AUTH_URL = "https://app.hubspot.com/oauth/authorize"
HUBSPOT_TOKEN_URL = "https://api.hubapi.com/oauth/v1/token"
HUBSPOT_API_BASE = "https://api.hubapi.com"


class HubspotError(RuntimeError):
    """Raised when HubSpot's API rejects a request we cared about."""


@dataclass(slots=True)
class HubspotTokenSet:
    access_token: str
    refresh_token: str | None
    expires_at: datetime
    scope: str | None
    portal_id: int | None


def build_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    scopes: tuple[str, ...] = HUBSPOT_SCOPES,
) -> str:
    """Construct the HubSpot consent URL the SPA redirects to."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "state": state,
    }
    return f"{HUBSPOT_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(
    code: str,
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    timeout: float = 15.0,
) -> HubspotTokenSet:
    if not (client_id and client_secret):
        raise HubspotError("hubspot oauth client credentials are missing")
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            HUBSPOT_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )
    if resp.status_code != 200:
        raise HubspotError(
            f"token exchange returned {resp.status_code}: {resp.text[:300]}"
        )
    payload = resp.json()
    expires_in = int(payload.get("expires_in") or 1800)
    return HubspotTokenSet(
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token"),
        expires_at=datetime.now(timezone.utc)
        + timedelta(seconds=expires_in),
        scope=payload.get("scope") or " ".join(HUBSPOT_SCOPES),
        portal_id=_extract_portal_id(payload),
    )


async def refresh_access_token(
    refresh_token: str,
    *,
    client_id: str,
    client_secret: str,
    timeout: float = 15.0,
) -> HubspotTokenSet:
    if not refresh_token:
        raise HubspotError("missing refresh token")
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            HUBSPOT_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
            },
        )
    if resp.status_code != 200:
        raise HubspotError(
            f"token refresh returned {resp.status_code}: {resp.text[:300]}"
        )
    payload = resp.json()
    expires_in = int(payload.get("expires_in") or 1800)
    return HubspotTokenSet(
        access_token=payload["access_token"],
        # HubSpot DOES re-issue a refresh token on every refresh call;
        # caller persists whatever we return.
        refresh_token=payload.get("refresh_token"),
        expires_at=datetime.now(timezone.utc)
        + timedelta(seconds=expires_in),
        scope=payload.get("scope"),
        portal_id=_extract_portal_id(payload),
    )


async def fetch_token_info(
    access_token: str, *, timeout: float = 10.0
) -> dict:
    """Look up portal id + user email from a fresh access token."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(
            f"{HUBSPOT_API_BASE}/oauth/v1/access-tokens/{access_token}"
        )
    if resp.status_code != 200:
        raise HubspotError(
            f"token info returned {resp.status_code}: {resp.text[:200]}"
        )
    return resp.json()


def _extract_portal_id(payload: dict) -> int | None:
    raw = payload.get("hub_id") or payload.get("portal_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class HubspotContactInput:
    """Logical lead row mapped to HubSpot's contact properties."""

    email: str | None
    firstname: str | None
    lastname: str | None
    phone: str | None
    company: str | None
    website: str | None
    city: str | None
    convioo_score: float | None = None
    convioo_status: str | None = None


class HubspotClient:
    """Async HubSpot REST client scoped to a single access token.

    Concurrency is rate-limit-aware: a semaphore caps in-flight calls
    at 10/sec so even tight ``asyncio.gather`` loops play nicely with
    the public-app daily quota. ``Retry-After`` on a 429 is honoured
    once before bubbling up.
    """

    def __init__(self, access_token: str, *, timeout: float = 15.0) -> None:
        if not access_token:
            raise HubspotError("access_token is required")
        self.access_token = access_token
        self.timeout = timeout
        self._semaphore = asyncio.Semaphore(10)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> HubspotClient:
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
        )
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
    ) -> httpx.Response:
        client = await self._http()
        async with self._semaphore:
            resp = await client.request(
                method, f"{HUBSPOT_API_BASE}{path}", json=json_body
            )
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After") or 1.0)
                await asyncio.sleep(min(retry_after, 5.0))
                resp = await client.request(
                    method, f"{HUBSPOT_API_BASE}{path}", json=json_body
                )
        return resp

    async def find_contact_by_email(self, email: str) -> str | None:
        """Search HubSpot for an existing contact with this email."""
        if not email:
            return None
        body = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "email",
                            "operator": "EQ",
                            "value": email,
                        }
                    ]
                }
            ],
            "properties": ["email"],
            "limit": 1,
        }
        resp = await self._request(
            "POST", "/crm/v3/objects/contacts/search", json_body=body
        )
        if resp.status_code != 200:
            raise HubspotError(
                f"search returned {resp.status_code}: {resp.text[:200]}"
            )
        results = resp.json().get("results") or []
        if not results:
            return None
        return str(results[0].get("id"))

    async def upsert_contact(
        self, contact: HubspotContactInput
    ) -> str:
        """Search-by-email then update; otherwise create. Returns id."""
        properties = _contact_to_properties(contact)
        if not properties:
            raise HubspotError("contact has no writable properties")
        existing_id: str | None = None
        if contact.email:
            existing_id = await self.find_contact_by_email(contact.email)
        if existing_id is not None:
            resp = await self._request(
                "PATCH",
                f"/crm/v3/objects/contacts/{existing_id}",
                json_body={"properties": properties},
            )
            if resp.status_code >= 400:
                raise HubspotError(
                    f"update returned {resp.status_code}: "
                    f"{resp.text[:200]}"
                )
            return existing_id
        resp = await self._request(
            "POST",
            "/crm/v3/objects/contacts",
            json_body={"properties": properties},
        )
        if resp.status_code >= 400:
            raise HubspotError(
                f"create returned {resp.status_code}: {resp.text[:200]}"
            )
        return str(resp.json().get("id"))


def _contact_to_properties(contact: HubspotContactInput) -> dict[str, str]:
    """Render a contact into the ``properties`` dict HubSpot expects.

    Empty / None fields are dropped so PATCH calls don't blank out
    columns the user already filled inside HubSpot. Score is rendered
    as a string because HubSpot's REST contract is string-typed even
    for numeric custom properties.
    """
    out: dict[str, str] = {}
    for key, value in [
        ("email", contact.email),
        ("firstname", contact.firstname),
        ("lastname", contact.lastname),
        ("phone", contact.phone),
        ("company", contact.company),
        ("website", contact.website),
        ("city", contact.city),
        ("convioo_status", contact.convioo_status),
    ]:
        text = (str(value).strip() if value else "")
        if text:
            out[key] = text
    if contact.convioo_score is not None:
        out["convioo_score"] = f"{contact.convioo_score:g}"
    return out


def split_full_name(name: str | None) -> tuple[str | None, str | None]:
    """Split a single ``contact_name`` field into firstname / lastname.

    Cheap heuristic — HubSpot keeps both columns regardless of how the
    user enters the name, so we'd rather have the first word land in
    ``firstname`` than nothing at all. Single-token inputs go to
    firstname only.
    """
    if not name:
        return None, None
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return None, None
    if len(parts) == 1:
        return parts[0], None
    return parts[0], " ".join(parts[1:])
