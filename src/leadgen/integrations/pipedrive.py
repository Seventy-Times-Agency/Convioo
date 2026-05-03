"""Pipedrive OAuth + person/deal upsert wrapper.

Mirrors the shape of ``integrations/hubspot.py`` so the route layer
can register both providers through the shared ``oauth_store``. Three
concerns: building the consent URL, exchanging / refreshing tokens,
and the upsert-person + create-deal calls used by the bulk export.

Pipedrive is per-customer-domain — every paying account lives at
``<companyname>.pipedrive.com`` and the OAuth response carries the
``api_domain`` we should hit for everything else (the central
``api.pipedrive.com`` only hosts auth).

Docs:
- https://developers.pipedrive.com/docs/api/v1/oauth
- https://developers.pipedrive.com/docs/api/v1/Persons
- https://developers.pipedrive.com/docs/api/v1/Deals
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

PIPEDRIVE_AUTH_URL = "https://oauth.pipedrive.com/oauth/authorize"
PIPEDRIVE_TOKEN_URL = "https://oauth.pipedrive.com/oauth/token"

# Coarse scope chosen because the v1 OAuth flow rejects unknown
# fine-grained scope strings — the public ``contacts:full`` /
# ``deals:full`` aren't available on legacy plans, while ``base``
# always works and covers everything we use.
PIPEDRIVE_SCOPES = ("base",)


class PipedriveError(RuntimeError):
    """Raised when Pipedrive's API rejects a request we cared about."""


@dataclass(slots=True)
class PipedriveTokenSet:
    access_token: str
    refresh_token: str | None
    expires_at: datetime
    scope: str | None
    api_domain: str | None
    account_email: str | None


def build_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
) -> str:
    """Construct the Pipedrive consent URL.

    Pipedrive doesn't take ``scope`` in the URL — scopes are baked
    into the marketplace app's OAuth config. ``state`` carries the
    Convioo user id so the callback knows whose tokens to save.
    """
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{PIPEDRIVE_AUTH_URL}?{urlencode(params)}"


def _parse_token_response(payload: dict) -> PipedriveTokenSet:
    expires_in = int(payload.get("expires_in") or 3600)
    api_domain: str | None = payload.get("api_domain")
    account_email = None
    user_block = payload.get("user")
    if isinstance(user_block, dict):
        account_email = user_block.get("email")
    return PipedriveTokenSet(
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token"),
        expires_at=datetime.now(timezone.utc)
        + timedelta(seconds=expires_in),
        scope=payload.get("scope") or " ".join(PIPEDRIVE_SCOPES),
        api_domain=api_domain,
        account_email=account_email,
    )


async def exchange_code_for_tokens(
    code: str,
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    timeout: float = 15.0,
) -> PipedriveTokenSet:
    if not (client_id and client_secret):
        raise PipedriveError(
            "pipedrive oauth client credentials are missing"
        )
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            PIPEDRIVE_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            auth=(client_id, client_secret),
        )
    if resp.status_code != 200:
        raise PipedriveError(
            f"token exchange returned {resp.status_code}: {resp.text[:300]}"
        )
    return _parse_token_response(resp.json())


async def refresh_access_token(
    refresh_token: str,
    *,
    client_id: str,
    client_secret: str,
    timeout: float = 15.0,
) -> PipedriveTokenSet:
    if not refresh_token:
        raise PipedriveError("missing refresh token")
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            PIPEDRIVE_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            auth=(client_id, client_secret),
        )
    if resp.status_code != 200:
        raise PipedriveError(
            f"token refresh returned {resp.status_code}: {resp.text[:300]}"
        )
    return _parse_token_response(resp.json())


@dataclass(slots=True)
class PipedrivePersonInput:
    name: str
    email: str | None
    phone: str | None
    org_name: str | None


@dataclass(slots=True)
class PipedrivePipeline:
    id: int
    name: str
    stages: list[PipedriveStage]


@dataclass(slots=True)
class PipedriveStage:
    id: int
    name: str
    pipeline_id: int
    order_nr: int


class PipedriveClient:
    """Async Pipedrive REST client scoped to one (token, api_domain).

    A semaphore caps in-flight calls at 10 to stay polite with
    Pipedrive's per-user rate limit (default 80 requests/2 seconds);
    that's headroom enough for tight ``asyncio.gather`` loops.
    """

    def __init__(
        self,
        access_token: str,
        api_domain: str,
        *,
        timeout: float = 15.0,
    ) -> None:
        if not access_token:
            raise PipedriveError("access_token is required")
        if not api_domain:
            raise PipedriveError("api_domain is required")
        self.access_token = access_token
        self.api_domain = api_domain.rstrip("/")
        self.timeout = timeout
        self._semaphore = asyncio.Semaphore(10)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> PipedriveClient:
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
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> httpx.Response:
        client = await self._http()
        async with self._semaphore:
            resp = await client.request(
                method,
                f"{self.api_domain}{path}",
                params=params,
                json=json_body,
            )
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After") or 1.0)
                await asyncio.sleep(min(retry_after, 5.0))
                resp = await client.request(
                    method,
                    f"{self.api_domain}{path}",
                    params=params,
                    json=json_body,
                )
        return resp

    async def list_pipelines(self) -> list[PipedrivePipeline]:
        """Return the user's pipelines + their stages.

        Two round-trips (pipelines, then stages) — Pipedrive doesn't
        offer a combined endpoint and we'd rather pay the latency than
        ship a second loop on the frontend.
        """
        pipelines_resp = await self._request("GET", "/api/v1/pipelines")
        if pipelines_resp.status_code != 200:
            raise PipedriveError(
                f"pipelines returned {pipelines_resp.status_code}: "
                f"{pipelines_resp.text[:200]}"
            )
        stages_resp = await self._request("GET", "/api/v1/stages")
        if stages_resp.status_code != 200:
            raise PipedriveError(
                f"stages returned {stages_resp.status_code}: "
                f"{stages_resp.text[:200]}"
            )
        stages_by_pipe: dict[int, list[PipedriveStage]] = {}
        for raw in stages_resp.json().get("data") or []:
            pipe_id = int(raw["pipeline_id"])
            stages_by_pipe.setdefault(pipe_id, []).append(
                PipedriveStage(
                    id=int(raw["id"]),
                    name=str(raw["name"]),
                    pipeline_id=pipe_id,
                    order_nr=int(raw.get("order_nr") or 0),
                )
            )
        out: list[PipedrivePipeline] = []
        for raw in pipelines_resp.json().get("data") or []:
            pipe_id = int(raw["id"])
            stages = sorted(
                stages_by_pipe.get(pipe_id, ()),
                key=lambda s: s.order_nr,
            )
            out.append(
                PipedrivePipeline(
                    id=pipe_id, name=str(raw["name"]), stages=stages
                )
            )
        return out

    async def find_person_by_email(self, email: str) -> str | None:
        if not email:
            return None
        resp = await self._request(
            "GET",
            "/api/v1/persons/search",
            params={"term": email, "fields": "email", "exact_match": "true"},
        )
        if resp.status_code != 200:
            raise PipedriveError(
                f"persons/search returned {resp.status_code}: "
                f"{resp.text[:200]}"
            )
        items = (resp.json().get("data") or {}).get("items") or []
        if not items:
            return None
        first = items[0].get("item") or {}
        pid = first.get("id")
        return str(pid) if pid is not None else None

    async def upsert_person(self, person: PipedrivePersonInput) -> str:
        """Search by email then update; otherwise create. Returns id."""
        existing_id = (
            await self.find_person_by_email(person.email)
            if person.email
            else None
        )
        body = _person_to_payload(person)
        if existing_id is not None:
            resp = await self._request(
                "PUT",
                f"/api/v1/persons/{existing_id}",
                json_body=body,
            )
            if resp.status_code >= 400:
                raise PipedriveError(
                    f"person update returned {resp.status_code}: "
                    f"{resp.text[:200]}"
                )
            return existing_id
        resp = await self._request(
            "POST", "/api/v1/persons", json_body=body
        )
        if resp.status_code >= 400:
            raise PipedriveError(
                f"person create returned {resp.status_code}: "
                f"{resp.text[:200]}"
            )
        new_id = (resp.json().get("data") or {}).get("id")
        if new_id is None:
            raise PipedriveError("person create response had no id")
        return str(new_id)

    async def create_deal(
        self,
        *,
        person_id: str,
        title: str,
        pipeline_id: int,
        stage_id: int,
    ) -> str:
        body = {
            "title": title[:255],
            "person_id": int(person_id),
            "pipeline_id": pipeline_id,
            "stage_id": stage_id,
        }
        resp = await self._request(
            "POST", "/api/v1/deals", json_body=body
        )
        if resp.status_code >= 400:
            raise PipedriveError(
                f"deal create returned {resp.status_code}: "
                f"{resp.text[:200]}"
            )
        deal_id = (resp.json().get("data") or {}).get("id")
        if deal_id is None:
            raise PipedriveError("deal create response had no id")
        return str(deal_id)


def _person_to_payload(person: PipedrivePersonInput) -> dict:
    """Render a person input into the JSON Pipedrive expects.

    Email and phone are list-shaped on the wire (Pipedrive supports
    multiple of each). ``org_name`` is set as a string — Pipedrive
    auto-creates an organisation when the string is unknown, which is
    what we want for a fresh export.
    """
    out: dict = {"name": person.name[:255]}
    if person.email:
        out["email"] = [{"value": person.email, "primary": True}]
    if person.phone:
        out["phone"] = [{"value": person.phone, "primary": True}]
    if person.org_name:
        out["org_name"] = person.org_name[:255]
    return out
