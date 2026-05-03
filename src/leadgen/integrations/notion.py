"""Thin Notion API wrapper for the lead-export flow.

Two ways to obtain a token live side by side:

1. *Internal integration token* — user pastes a token from
   notion.so/my-integrations and shares a database with the
   integration manually. Original MVP path.
2. *Public OAuth* — user clicks "Connect Notion", picks a
   workspace + databases on Notion's UI, we receive a long-lived
   workspace bot token via the standard ``oauth/token`` exchange.
   Notion does NOT issue refresh tokens; the access token is good
   until the user revokes it from their workspace settings.

Both paths land in the same ``UserIntegrationCredential`` row so
downstream code (``export-to-notion`` etc.) doesn't care how the
token arrived.

Docs:
- https://developers.notion.com/docs/authorization
- https://developers.notion.com/reference/post-page
- https://developers.notion.com/reference/property-value-object
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_API_VERSION = "2022-06-28"
NOTION_AUTH_URL = "https://api.notion.com/v1/oauth/authorize"
NOTION_TOKEN_URL = "https://api.notion.com/v1/oauth/token"


@dataclass(slots=True)
class NotionOAuthTokens:
    """What Notion's ``/oauth/token`` returns. No refresh token.

    ``bot_id`` identifies the integration install; ``workspace_id`` and
    ``workspace_name`` describe where the integration was authorised.
    ``owner`` is the raw user/workspace block — handy for surfacing the
    connected account email when present.
    """

    access_token: str
    bot_id: str | None
    workspace_id: str | None
    workspace_name: str | None
    workspace_icon: str | None
    owner: dict[str, Any] | None


def build_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
) -> str:
    """Construct the Notion consent URL the SPA redirects to.

    ``owner=user`` makes Notion ask for an installation onto a
    specific workspace under the signed-in user instead of treating
    it as a public-link install.
    """
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "owner": "user",
        "state": state,
    }
    return f"{NOTION_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(
    code: str,
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    timeout: float = 15.0,
) -> NotionOAuthTokens:
    """Trade an auth-code for a workspace bot token.

    Notion uses HTTP Basic auth (client_id:client_secret) on the
    token endpoint, not POST-body credentials.
    """
    if not (client_id and client_secret):
        raise NotionError("notion oauth client credentials are missing")
    basic = base64.b64encode(
        f"{client_id}:{client_secret}".encode()
    ).decode("ascii")
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            NOTION_TOKEN_URL,
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/json",
                "Notion-Version": NOTION_API_VERSION,
            },
        )
    if resp.status_code != 200:
        raise NotionError(
            f"oauth token exchange returned {resp.status_code}: "
            f"{resp.text[:300]}"
        )
    payload = resp.json()
    return NotionOAuthTokens(
        access_token=payload["access_token"],
        bot_id=payload.get("bot_id"),
        workspace_id=payload.get("workspace_id"),
        workspace_name=payload.get("workspace_name"),
        workspace_icon=payload.get("workspace_icon"),
        owner=payload.get("owner"),
    )


class NotionError(RuntimeError):
    """Raised when Notion's API rejects a request we cared about."""


@dataclass(slots=True)
class NotionExportRow:
    """Subset of Lead fields we know how to push to Notion.

    We map onto common Notion property types — Title, URL, Number,
    Phone, Rich text, Multi-select. The actual mapping at runtime is
    schema-aware (we read the database's properties first), so a
    missing column on the user's side just gets skipped instead of
    400-ing the whole batch.
    """

    name: str
    score: int | None = None
    status: str | None = None
    rating: float | None = None
    reviews: int | None = None
    phone: str | None = None
    website: str | None = None
    address: str | None = None
    category: str | None = None
    notes: str | None = None
    niche: str | None = None
    region: str | None = None
    tags: tuple[str, ...] = ()


_PROPERTY_FALLBACKS: dict[str, tuple[str, ...]] = {
    # Lower-cased acceptable names per logical column. We pick the
    # first one that exists in the user's database schema.
    "name": ("name", "lead", "company", "название", "лид"),
    "score": ("score", "ai score", "скор", "оценка"),
    "status": ("status", "stage", "статус"),
    "rating": ("rating", "stars", "рейтинг"),
    "reviews": ("reviews", "reviews count", "отзывы"),
    "phone": ("phone", "телефон"),
    "website": ("website", "url", "сайт"),
    "address": ("address", "адрес"),
    "category": ("category", "категория"),
    "notes": ("notes", "comment", "заметки"),
    "niche": ("niche", "ниша"),
    "region": ("region", "city", "регион", "город"),
    "tags": ("tags", "labels", "теги"),
}


class NotionClient:
    """Async Notion REST client scoped to a single integration token."""

    def __init__(
        self,
        token: str,
        *,
        timeout: float = 15.0,
    ) -> None:
        if not token:
            raise NotionError("token is required")
        self.token = token
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> NotionClient:
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": NOTION_API_VERSION,
                "Content-Type": "application/json",
            },
        )
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Notion-Version": NOTION_API_VERSION,
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def get_database(self, database_id: str) -> dict[str, Any]:
        """Fetch the database schema so we can map fields to columns."""
        client = await self._http()
        resp = await client.get(f"{NOTION_API_BASE}/databases/{database_id}")
        if resp.status_code != 200:
            raise NotionError(
                f"Notion get_database returned {resp.status_code}: "
                f"{resp.text[:200]}"
            )
        return resp.json()

    async def list_databases(
        self, *, page_size: int = 50
    ) -> list[dict[str, Any]]:
        """List databases the integration has been granted access to.

        After OAuth install Notion only surfaces objects the user
        explicitly ticked during consent; the search endpoint then
        scopes results to that subset, which is exactly the picker we
        want to render.
        """
        client = await self._http()
        resp = await client.post(
            f"{NOTION_API_BASE}/search",
            json={
                "filter": {"value": "database", "property": "object"},
                "page_size": max(1, min(int(page_size), 100)),
            },
        )
        if resp.status_code != 200:
            raise NotionError(
                f"Notion search returned {resp.status_code}: "
                f"{resp.text[:200]}"
            )
        return list(resp.json().get("results") or [])

    async def create_page(
        self, *, database_id: str, properties: dict[str, Any]
    ) -> dict[str, Any]:
        client = await self._http()
        payload = {
            "parent": {"database_id": database_id},
            "properties": properties,
        }
        resp = await client.post(f"{NOTION_API_BASE}/pages", json=payload)
        if resp.status_code >= 400:
            raise NotionError(
                f"Notion create_page returned {resp.status_code}: "
                f"{resp.text[:200]}"
            )
        return resp.json()


def resolve_property_map(
    schema: dict[str, Any],
) -> dict[str, tuple[str, str]]:
    """Map our logical column names → ``(notion_name, notion_type)``.

    ``schema`` is the response from ``get_database``. We only return
    entries we can actually write to — required title is mandatory,
    everything else is optional.
    """
    db_properties = schema.get("properties") or {}
    by_name_lower: dict[str, tuple[str, str]] = {
        str(name).strip().lower(): (str(name), prop.get("type") or "")
        for name, prop in db_properties.items()
    }
    out: dict[str, tuple[str, str]] = {}
    for logical, candidates in _PROPERTY_FALLBACKS.items():
        for cand in candidates:
            if cand.lower() in by_name_lower:
                out[logical] = by_name_lower[cand.lower()]
                break
    # Always make sure SOME title column exists — Notion requires one.
    if "name" not in out:
        for actual_name, prop_type in by_name_lower.values():
            if prop_type == "title":
                out["name"] = (actual_name, prop_type)
                break
    return out


def row_to_properties(
    row: NotionExportRow, mapping: dict[str, tuple[str, str]]
) -> dict[str, Any]:
    """Build the Notion ``properties`` payload for one lead row.

    Each ``(logical_field, notion_type)`` decides the property-value
    shape — Notion is strict about this, sending a number to a
    rich_text column 400s the request. We silently drop fields that
    don't have a target column and types we don't support so a quirky
    user schema doesn't take the whole export down.
    """
    props: dict[str, Any] = {}
    for logical, (notion_name, notion_type) in mapping.items():
        value = _logical_value(row, logical)
        if value is None or value == "":
            continue
        encoded = _encode_value(value, notion_type)
        if encoded is not None:
            props[notion_name] = encoded
    return props


def _logical_value(row: NotionExportRow, logical: str) -> Any:
    if logical == "tags":
        return list(row.tags)
    return getattr(row, logical, None)


def _encode_value(value: Any, notion_type: str) -> dict[str, Any] | None:
    if notion_type == "title":
        return {"title": [{"text": {"content": _short_text(value)}}]}
    if notion_type == "rich_text":
        return {
            "rich_text": [{"text": {"content": _short_text(value, 2000)}}]
        }
    if notion_type == "number":
        try:
            return {"number": float(value)}
        except (TypeError, ValueError):
            return None
    if notion_type == "select":
        if not value:
            return None
        return {"select": {"name": _short_text(value, 100)}}
    if notion_type == "multi_select":
        items = value if isinstance(value, (list, tuple)) else [value]
        cleaned = [
            {"name": _short_text(v, 100)} for v in items if str(v).strip()
        ]
        return {"multi_select": cleaned} if cleaned else None
    if notion_type == "url":
        text = str(value).strip()
        return {"url": text} if text else None
    if notion_type == "phone_number":
        text = str(value).strip()
        return {"phone_number": text} if text else None
    if notion_type == "email":
        text = str(value).strip()
        return {"email": text} if text else None
    return None


def _short_text(value: Any, limit: int = 200) -> str:
    text = str(value).strip()
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text
