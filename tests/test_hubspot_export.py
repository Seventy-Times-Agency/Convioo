"""HubSpot lead export: stage-mode 503 + happy path with mocked client."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.adapters.web_api import auth as auth_mod
from leadgen.config import get_settings
from leadgen.core.services import secrets_vault as vault_mod
from leadgen.db import session as db_session_mod
from leadgen.db.models import (
    Base,
    Lead,
    OAuthCredential,
    SearchQuery,
    User,
)


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def patched_session_factory(monkeypatch, db_engine):
    maker = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr(db_session_mod, "_engine", db_engine)
    monkeypatch.setattr(db_session_mod, "_session_factory", maker)
    return maker


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _force_dev_fernet(monkeypatch):
    """Stable Fernet key so encrypt/decrypt work in unit tests."""
    monkeypatch.setenv(
        "FERNET_KEY", "M-32NFm-O9XIY4_2g7lGv2j0a5kxgQwvvnCC5dB97V8="
    )
    vault_mod._fernet.cache_clear()
    yield
    vault_mod._fernet.cache_clear()


def _client_for(user: User) -> TestClient:
    from leadgen.adapters.web_api.app import create_app

    async def _fake() -> User:
        return user

    app = create_app()
    app.dependency_overrides[auth_mod.get_current_user] = _fake
    return TestClient(app)


@pytest.mark.asyncio
async def test_authorize_returns_503_without_keys(
    patched_session_factory, monkeypatch
):
    monkeypatch.setenv("HUBSPOT_OAUTH_CLIENT_ID", "")
    monkeypatch.setenv("HUBSPOT_OAUTH_CLIENT_SECRET", "")
    get_settings.cache_clear()

    user = User(id=1, email="u@example.com", first_name="U")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    r = _client_for(user).get("/api/v1/integrations/hubspot/authorize")
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_export_503_without_keys(
    patched_session_factory, monkeypatch
):
    monkeypatch.setenv("HUBSPOT_OAUTH_CLIENT_ID", "")
    monkeypatch.setenv("HUBSPOT_OAUTH_CLIENT_SECRET", "")
    get_settings.cache_clear()

    user = User(id=1, email="u@example.com", first_name="U")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    r = _client_for(user).post(
        "/api/v1/leads/export-to-hubspot",
        json={"lead_ids": [str(uuid.uuid4())]},
    )
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_export_happy_path_with_mock(
    patched_session_factory, monkeypatch
):
    monkeypatch.setenv("HUBSPOT_OAUTH_CLIENT_ID", "client")
    monkeypatch.setenv("HUBSPOT_OAUTH_CLIENT_SECRET", "secret")
    get_settings.cache_clear()

    user = User(id=10, email="u10@example.com", first_name="U")
    query = SearchQuery(
        id=uuid.uuid4(),
        user_id=10,
        niche="Coffee",
        region="Berlin",
        scope="city",
        status="done",
        source="web",
    )
    leads = [
        Lead(
            id=uuid.uuid4(),
            query_id=query.id,
            name=f"Co {i}",
            source="google",
            source_id=f"g{i}",
            score_ai=80.0,
            lead_status="new",
            phone=f"+49170000000{i}",
            website="https://example.com",
            website_meta={"emails": [f"info{i}@example.com"]},
        )
        for i in range(3)
    ]
    cred = OAuthCredential(
        user_id=10,
        provider="hubspot",
        access_token_ciphertext=vault_mod.encrypt("dummy_access"),
        refresh_token_ciphertext=vault_mod.encrypt("dummy_refresh"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scope="crm.objects.contacts.write portal:42",
    )
    async with patched_session_factory() as s:
        s.add(user)
        s.add(query)
        for lead in leads:
            s.add(lead)
        s.add(cred)
        await s.commit()

    # Mock HubspotClient so no real network calls happen.
    from leadgen.integrations import hubspot as hubspot_mod

    class _StubClient:
        def __init__(self, _token: str, **_kw) -> None:
            self.calls = 0

        async def __aenter__(self) -> _StubClient:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        async def upsert_contact(
            self, contact: hubspot_mod.HubspotContactInput
        ) -> str:
            self.calls += 1
            if contact.email and "1" in contact.email:
                # one row fails so we exercise the per-lead error path
                raise hubspot_mod.HubspotError("simulated 400")
            return f"contact-{self.calls}"

    monkeypatch.setattr(hubspot_mod, "HubspotClient", _StubClient)

    r = _client_for(user).post(
        "/api/v1/leads/export-to-hubspot",
        json={"lead_ids": [str(lead.id) for lead in leads]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success_count"] == 2
    assert body["failure_count"] == 1
    errors = [it["error"] for it in body["items"] if it["error"]]
    assert any("simulated 400" in e for e in errors)


@pytest.mark.asyncio
async def test_export_lead_without_email_inlines_error(
    patched_session_factory, monkeypatch
):
    monkeypatch.setenv("HUBSPOT_OAUTH_CLIENT_ID", "client")
    monkeypatch.setenv("HUBSPOT_OAUTH_CLIENT_SECRET", "secret")
    get_settings.cache_clear()

    user = User(id=20, email="u20@example.com", first_name="U")
    query = SearchQuery(
        id=uuid.uuid4(),
        user_id=20,
        niche="Coffee",
        region="Berlin",
        scope="city",
        status="done",
        source="web",
    )
    lead = Lead(
        id=uuid.uuid4(),
        query_id=query.id,
        name="Bare Co",
        source="google",
        source_id="g_bare",
        lead_status="new",
        # explicitly no website_meta / phone-derived email
    )
    cred = OAuthCredential(
        user_id=20,
        provider="hubspot",
        access_token_ciphertext=vault_mod.encrypt("dummy_access"),
        refresh_token_ciphertext=vault_mod.encrypt("dummy_refresh"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scope="crm.objects.contacts.write",
    )
    async with patched_session_factory() as s:
        s.add(user)
        s.add(query)
        s.add(lead)
        s.add(cred)
        await s.commit()

    from leadgen.integrations import hubspot as hubspot_mod

    class _UnusedClient:
        def __init__(self, *_a, **_kw) -> None: ...
        async def __aenter__(self) -> _UnusedClient:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        async def upsert_contact(self, *_a, **_kw) -> str:
            raise AssertionError("should not be called")

    monkeypatch.setattr(hubspot_mod, "HubspotClient", _UnusedClient)

    r = _client_for(user).post(
        "/api/v1/leads/export-to-hubspot",
        json={"lead_ids": [str(lead.id)]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success_count"] == 0
    assert body["failure_count"] == 1
    assert "no email" in body["items"][0]["error"]


def test_split_full_name_handles_edge_cases():
    from leadgen.integrations.hubspot import split_full_name

    assert split_full_name(None) == (None, None)
    assert split_full_name("  ") == (None, None)
    assert split_full_name("Alice") == ("Alice", None)
    assert split_full_name("Alice Cooper") == ("Alice", "Cooper")
    assert split_full_name("Jean-Luc von  Habsburg") == (
        "Jean-Luc",
        "von Habsburg",
    )


def test_contact_to_properties_drops_blanks():
    from leadgen.integrations.hubspot import (
        HubspotContactInput,
        _contact_to_properties,
    )

    contact = HubspotContactInput(
        email="x@example.com",
        firstname="X",
        lastname="",
        phone=None,
        company=None,
        website="https://example.com",
        city=None,
        convioo_score=87.5,
        convioo_status="new",
    )
    props = _contact_to_properties(contact)
    assert props["email"] == "x@example.com"
    assert props["firstname"] == "X"
    assert "lastname" not in props
    assert "phone" not in props
    assert props["website"] == "https://example.com"
    assert props["convioo_score"] == "87.5"
    assert props["convioo_status"] == "new"


# Helper required by the test fixtures above — the actual import lives
# inside the production handlers via a deferred import so we don't
# trigger it at module load time.
@asynccontextmanager
async def _noop():
    yield None
