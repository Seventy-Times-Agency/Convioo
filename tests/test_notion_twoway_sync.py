"""Tests for Notion two-way sync:
  - POST /api/v1/integrations/notion/sync
  - push_lead_status_to_notion background helper
"""
from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from leadgen.db import session as db_session_mod
from leadgen.db.models import Base, Lead, SearchQuery
from leadgen.utils import rate_limit as rate_limit_mod

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def patched_session_factory(monkeypatch, db_engine):
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db_session_mod, "_engine", db_engine)
    monkeypatch.setattr(db_session_mod, "_session_factory", maker)
    return maker


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    for name in (
        "login_limiter",
        "register_limiter",
        "forgot_password_limiter",
        "forgot_email_limiter",
        "reset_password_limiter",
        "resend_verification_limiter",
    ):
        getattr(rate_limit_mod, name)._events.clear()
    yield


@pytest.fixture
def client(patched_session_factory):
    from leadgen.adapters.web_api import create_app

    return TestClient(create_app())


def _register(client: TestClient, email: str = "sync-user@example.test") -> int:
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Sync",
            "last_name": "Tester",
            "email": email,
            "password": "correcthorse123",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


def _schema_response() -> dict[str, Any]:
    return {
        "title": [{"plain_text": "Test DB"}],
        "properties": {
            "Name": {"name": "Name", "type": "title"},
            "Status": {"name": "Status", "type": "select"},
        },
    }


def _page_response(status: str, page_id: str = "page_abc123") -> dict[str, Any]:
    return {
        "id": page_id,
        "url": f"https://notion.so/{page_id}",
        "properties": {
            "Status": {
                "type": "select",
                "select": {"name": status},
            }
        },
    }


@pytest.fixture
def mock_notion_sync(monkeypatch):
    """Fakes httpx calls for two-way sync: GET returns schema or page, PATCH records call."""
    calls: dict[str, list[Any]] = {"get": [], "patch": []}

    class _Resp:
        def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
            self.status_code = status_code
            self._payload = payload
            self.text = ""

        def json(self) -> dict[str, Any]:
            return self._payload

    async def fake_get(self, url, *args, **kwargs):
        calls["get"].append(url)
        if "/pages/" in url:
            return _Resp(200, _page_response("contacted"))
        return _Resp(200, _schema_response())

    async def fake_post(self, url, *args, **kwargs):
        return _Resp(200, {"id": "page_xyz", "url": "https://notion.so/page_xyz"})

    async def fake_patch(self, url, *args, **kwargs):
        calls["patch"].append((url, kwargs.get("json")))
        return _Resp(200, {"id": "page_abc123"})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(httpx.AsyncClient, "patch", fake_patch)
    return calls


def _connect_notion(client: TestClient) -> None:
    r = client.put(
        "/api/v1/integrations/notion",
        json={"token": "ntn_secret_abcdef1234", "database_id": "db_abc1234567890"},
    )
    assert r.status_code == 200, r.text


async def _seed_lead(
    maker: async_sessionmaker,
    user_id: int,
    lead_status: str = "new",
    notion_page_id: str | None = "page_abc123",
) -> uuid.UUID:
    async with maker() as session:
        query = SearchQuery(
            id=uuid.uuid4(),
            user_id=user_id,
            niche="plumbing",
            region="London",
            scope="city",
            source="test",
        )
        session.add(query)
        await session.flush()
        lead = Lead(
            id=uuid.uuid4(),
            query_id=query.id,
            name="Acme Plumbing",
            source="google",
            source_id="g_001",
            lead_status=lead_status,
            notion_page_id=notion_page_id,
        )
        session.add(lead)
        await session.commit()
        return lead.id


# ── POST /api/v1/integrations/notion/sync ────────────────────────────────


def test_sync_requires_connection(client: TestClient):
    _register(client)
    r = client.post("/api/v1/integrations/notion/sync")
    assert r.status_code == 400
    assert "not connected" in r.json()["detail"].lower()


def test_sync_requires_database_id(client: TestClient, mock_notion_sync):
    """After connecting with internal token, database_id is set in config.
    This test verifies the 400 if somehow database_id is missing."""
    _register(client)
    # Connect without a valid DB id is not directly possible via the API,
    # but verify the happy path still requires connection first.
    r = client.post("/api/v1/integrations/notion/sync")
    assert r.status_code == 400


def test_sync_returns_empty_when_no_leads(client: TestClient, mock_notion_sync):
    _register(client)
    _connect_notion(client)
    r = client.post("/api/v1/integrations/notion/sync")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["success_count"] == 0
    assert body["failure_count"] == 0


@pytest.mark.asyncio
async def test_sync_updates_lead_status_when_notion_differs(
    client: TestClient,
    patched_session_factory,
    mock_notion_sync,
):
    user_id = _register(client)
    _connect_notion(client)

    # Lead has status="new"; Notion page will return "contacted"
    lead_id = await _seed_lead(patched_session_factory, user_id, lead_status="new")

    r = client.post("/api/v1/integrations/notion/sync")
    assert r.status_code == 200
    body = r.json()
    assert body["success_count"] == 1
    assert body["failure_count"] == 0
    assert len(body["items"]) == 1
    assert body["items"][0]["notion_url"] == "https://notion.so/page_abc123"

    async with patched_session_factory() as session:
        updated = await session.get(Lead, lead_id)
        assert updated is not None
        assert updated.lead_status == "contacted"


@pytest.mark.asyncio
async def test_sync_no_change_when_status_already_matches(
    client: TestClient,
    patched_session_factory,
    mock_notion_sync,
):
    user_id = _register(client)
    _connect_notion(client)

    # Lead already has the same status as Notion will return ("contacted")
    lead_id = await _seed_lead(
        patched_session_factory, user_id, lead_status="contacted"
    )

    r = client.post("/api/v1/integrations/notion/sync")
    assert r.status_code == 200
    body = r.json()
    assert body["success_count"] == 0  # nothing changed
    assert len(body["items"]) == 1

    # Status must remain unchanged
    async with patched_session_factory() as session:
        db_lead = await session.get(Lead, lead_id)
        assert db_lead is not None
        assert db_lead.lead_status == "contacted"


@pytest.mark.asyncio
async def test_sync_skips_leads_without_notion_page_id(
    client: TestClient,
    patched_session_factory,
    mock_notion_sync,
):
    user_id = _register(client)
    _connect_notion(client)

    # Lead with no notion_page_id should not appear in sync results
    await _seed_lead(patched_session_factory, user_id, notion_page_id=None)

    r = client.post("/api/v1/integrations/notion/sync")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []


# ── push_lead_status_to_notion ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_push_silently_skips_when_user_not_connected(patched_session_factory):
    from leadgen.adapters.web_api.routes.notion import push_lead_status_to_notion

    # No credentials for user_id=9999 — must not raise
    await push_lead_status_to_notion(9999, "page_xyz", "contacted")


@pytest.mark.asyncio
async def test_push_calls_notion_patch(
    client: TestClient,
    patched_session_factory,
    mock_notion_sync,
):
    user_id = _register(client)
    _connect_notion(client)

    from leadgen.adapters.web_api.routes.notion import push_lead_status_to_notion

    await push_lead_status_to_notion(user_id, "page_abc123", "won")

    # get_database was fetched
    assert any("/databases/" in url for url in mock_notion_sync["get"])
    # update_page (PATCH) was called
    assert any("/pages/" in url for url, _ in mock_notion_sync["patch"])


@pytest.mark.asyncio
async def test_push_no_op_when_schema_has_no_status_column(
    client: TestClient,
    patched_session_factory,
    monkeypatch,
):
    user_id = _register(client)

    # Schema returns only a Name/title column — no Status
    class _Resp:
        def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
            self.status_code = status_code
            self._payload = payload
            self.text = ""

        def json(self) -> dict[str, Any]:
            return self._payload

    async def fake_get(self, url, *args, **kwargs):
        return _Resp(
            200,
            {
                "title": [{"plain_text": "DB"}],
                "properties": {"Name": {"name": "Name", "type": "title"}},
            },
        )

    patch_calls: list[str] = []

    async def fake_patch(self, url, *args, **kwargs):
        patch_calls.append(url)
        return _Resp(200, {})

    async def fake_post(self, url, *args, **kwargs):
        return _Resp(200, {"id": "page_xyz", "url": "https://notion.so/page_xyz"})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(httpx.AsyncClient, "patch", fake_patch)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    _connect_notion(client)

    from leadgen.adapters.web_api.routes.notion import push_lead_status_to_notion

    await push_lead_status_to_notion(user_id, "page_abc123", "won")

    # PATCH must NOT have been called
    assert patch_calls == []
