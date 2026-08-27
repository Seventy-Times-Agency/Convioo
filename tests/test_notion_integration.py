"""Notion integration: secrets vault round-trip + property mapping +
   API endpoints (with Notion HTTP calls mocked)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.core.services.secrets_vault import decrypt, encrypt, mask_token
from leadgen.db import session as db_session_mod
from leadgen.db.models import Base
from leadgen.integrations.notion import (
    NotionExportRow,
    resolve_property_map,
    row_to_properties,
)
from leadgen.utils import rate_limit as rate_limit_mod

# ── Vault ────────────────────────────────────────────────────────────────


def test_encrypt_decrypt_round_trip() -> None:
    plaintext = "secret_ntn_abcdef1234"
    cipher = encrypt(plaintext)
    assert cipher != plaintext
    assert decrypt(cipher) == plaintext


def test_decrypt_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        decrypt("not-actually-fernet-output")


def test_mask_token_redacts_safely() -> None:
    assert mask_token(None) == "(none)"
    assert mask_token("ntn_supersecret_xyz")[:3] == "ntn"
    assert mask_token("ntn_supersecret_xyz").endswith("xyz")
    assert "supersecret" not in mask_token("ntn_supersecret_xyz")
    # Short tokens turn into bare asterisks (no leak).
    assert mask_token("short") == "*****"


# ── Notion property mapping ──────────────────────────────────────────────


def _schema(props: dict[str, str]) -> dict[str, Any]:
    """Build a fake Notion database schema with the given (name → type) map."""
    return {
        "object": "database",
        "properties": {
            name: {"id": "abc", "name": name, "type": kind}
            for name, kind in props.items()
        },
    }


def test_resolve_property_map_finds_canonical_columns() -> None:
    schema = _schema(
        {
            "Name": "title",
            "Score": "number",
            "Status": "select",
            "Phone": "phone_number",
            "Website": "url",
            "Tags": "multi_select",
        }
    )
    mapping = resolve_property_map(schema)
    assert mapping["name"] == ("Name", "title")
    assert mapping["score"] == ("Score", "number")
    assert mapping["status"] == ("Status", "select")
    assert mapping["phone"] == ("Phone", "phone_number")
    assert mapping["website"] == ("Website", "url")
    assert mapping["tags"] == ("Tags", "multi_select")


def test_resolve_property_map_falls_back_to_russian_names() -> None:
    schema = _schema({"Название": "title", "Скор": "number"})
    mapping = resolve_property_map(schema)
    assert mapping["name"] == ("Название", "title")
    assert mapping["score"] == ("Скор", "number")


def test_resolve_property_map_finds_any_title_when_label_missing() -> None:
    schema = _schema({"Whatever": "title"})
    mapping = resolve_property_map(schema)
    assert mapping["name"] == ("Whatever", "title")


def test_row_to_properties_emits_correct_value_shapes() -> None:
    schema = _schema(
        {
            "Name": "title",
            "Score": "number",
            "Status": "select",
            "Phone": "phone_number",
            "Website": "url",
            "Tags": "multi_select",
            "Notes": "rich_text",
        }
    )
    mapping = resolve_property_map(schema)
    row = NotionExportRow(
        name="Acme",
        score=82,
        status="contacted",
        phone="+15551112222",
        website="https://acme.example",
        tags=("hot", "decision-maker"),
        notes="Met at trade show",
    )
    props = row_to_properties(row, mapping)
    assert props["Name"]["title"][0]["text"]["content"] == "Acme"
    assert props["Score"] == {"number": 82.0}
    assert props["Status"] == {"select": {"name": "contacted"}}
    assert props["Phone"] == {"phone_number": "+15551112222"}
    assert props["Website"] == {"url": "https://acme.example"}
    assert {opt["name"] for opt in props["Tags"]["multi_select"]} == {
        "hot",
        "decision-maker",
    }
    assert props["Notes"]["rich_text"][0]["text"]["content"] == "Met at trade show"


def test_row_to_properties_skips_empty_fields() -> None:
    schema = _schema({"Name": "title", "Phone": "phone_number"})
    mapping = resolve_property_map(schema)
    row = NotionExportRow(name="Acme", phone=None)
    props = row_to_properties(row, mapping)
    assert "Phone" not in props
    assert "Name" in props


def test_row_to_properties_drops_unsupported_types() -> None:
    schema = _schema({"Name": "title", "Created": "date"})
    mapping = resolve_property_map(schema)
    # ``date`` isn't in our type-encoder switch — it should be silently
    # dropped instead of generating a malformed payload that 400s the
    # whole batch.
    assert "created" not in mapping or mapping.get("created") is None
    row = NotionExportRow(name="Acme")
    props = row_to_properties(row, mapping)
    assert "Created" not in props


# ── Notion API endpoints (Notion HTTP mocked) ────────────────────────────


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
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
def mock_notion(monkeypatch):
    """Replace httpx.AsyncClient.get/post with deterministic fakes."""
    calls: dict[str, list[Any]] = {"get": [], "post": []}

    class _Resp:
        def __init__(self, status_code: int, payload: dict[str, Any]):
            self.status_code = status_code
            self._payload = payload
            self.text = ""

        def json(self) -> dict[str, Any]:
            return self._payload

    async def fake_get(self, url, *args, **kwargs):
        calls["get"].append(url)
        return _Resp(
            200,
            {
                "title": [{"plain_text": "My Workspace"}],
                "properties": {
                    "Name": {"name": "Name", "type": "title"},
                    "Score": {"name": "Score", "type": "number"},
                    "Phone": {"name": "Phone", "type": "phone_number"},
                },
            },
        )

    async def fake_post(self, url, *args, **kwargs):
        calls["post"].append((url, kwargs.get("json")))
        return _Resp(
            200,
            {
                "id": "page_xyz",
                "url": "https://www.notion.so/page_xyz",
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return calls


@pytest.fixture
def client(patched_session_factory):
    from leadgen.adapters.web_api import create_app

    return TestClient(create_app())


def _register(client: TestClient) -> int:
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Notion",
            "last_name": "User",
            "email": "notion-user@example.test",
            "password": "correcthorse123",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


def test_notion_status_returns_disconnected_initially(
    client: TestClient,
):
    _register(client)
    r = client.get("/api/v1/integrations/notion")
    assert r.status_code == 200
    body = r.json()
    assert body["connected"] is False
    assert body["token_preview"] is None


def test_connect_disconnect_round_trip(
    client: TestClient,
    mock_notion,
):
    _register(client)
    r = client.put(
        "/api/v1/integrations/notion",
        json={
            "token": "ntn_secret_abcdef1234",
            "database_id": "db_database_id_2222222222",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["connected"] is True
    assert body["workspace_name"] == "My Workspace"
    assert body["token_preview"].startswith("ntn")

    r = client.get("/api/v1/integrations/notion")
    body = r.json()
    assert body["connected"] is True
    assert body["database_id"] == "db_database_id_2222222222"

    r = client.delete("/api/v1/integrations/notion")
    assert r.status_code == 200

    r = client.get("/api/v1/integrations/notion")
    assert r.json()["connected"] is False


def test_export_to_notion_requires_connection(client: TestClient):
    _register(client)
    import uuid as _uuid

    r = client.post(
        "/api/v1/leads/export-to-notion",
        json={"lead_ids": [str(_uuid.uuid4())]},
    )
    assert r.status_code == 400
    assert "not connected" in r.json()["detail"].lower()
