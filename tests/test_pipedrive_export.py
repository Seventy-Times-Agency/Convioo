"""Pipedrive lead export: stage-mode 503 + happy path with mocks."""

from __future__ import annotations

import uuid
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
    UserIntegrationCredential,
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
async def test_authorize_503_without_keys(
    patched_session_factory, monkeypatch
):
    monkeypatch.setenv("PIPEDRIVE_OAUTH_CLIENT_ID", "")
    monkeypatch.setenv("PIPEDRIVE_OAUTH_CLIENT_SECRET", "")
    get_settings.cache_clear()

    user = User(id=1, email="u@example.com", first_name="U")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    r = _client_for(user).get("/api/v1/integrations/pipedrive/authorize")
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_export_503_without_keys(
    patched_session_factory, monkeypatch
):
    monkeypatch.setenv("PIPEDRIVE_OAUTH_CLIENT_ID", "")
    monkeypatch.setenv("PIPEDRIVE_OAUTH_CLIENT_SECRET", "")
    get_settings.cache_clear()

    user = User(id=1, email="u@example.com", first_name="U")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    r = _client_for(user).post(
        "/api/v1/leads/export-to-pipedrive",
        json={"lead_ids": [str(uuid.uuid4())]},
    )
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_export_requires_pipeline_config(
    patched_session_factory, monkeypatch
):
    """Without a pipeline/stage selection in config, export 400s."""
    monkeypatch.setenv("PIPEDRIVE_OAUTH_CLIENT_ID", "client")
    monkeypatch.setenv("PIPEDRIVE_OAUTH_CLIENT_SECRET", "secret")
    get_settings.cache_clear()

    user = User(id=10, email="u10@example.com", first_name="U")
    cred = OAuthCredential(
        user_id=10,
        provider="pipedrive",
        access_token_ciphertext=vault_mod.encrypt("dummy_access"),
        refresh_token_ciphertext=vault_mod.encrypt("dummy_refresh"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scope="base api_domain:https://acme.pipedrive.com",
    )
    async with patched_session_factory() as s:
        s.add(user)
        s.add(cred)
        await s.commit()

    r = _client_for(user).post(
        "/api/v1/leads/export-to-pipedrive",
        json={"lead_ids": [str(uuid.uuid4())]},
    )
    assert r.status_code == 400
    assert "pipeline" in r.json()["detail"]


@pytest.mark.asyncio
async def test_export_happy_path(
    patched_session_factory, monkeypatch
):
    monkeypatch.setenv("PIPEDRIVE_OAUTH_CLIENT_ID", "client")
    monkeypatch.setenv("PIPEDRIVE_OAUTH_CLIENT_SECRET", "secret")
    get_settings.cache_clear()

    user = User(id=20, email="u@example.com", first_name="U")
    query = SearchQuery(
        id=uuid.uuid4(),
        user_id=20,
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
            phone=f"+4917000000{i}",
            website_meta={"emails": [f"info{i}@example.com"]},
            lead_status="new",
        )
        for i in range(2)
    ]
    cred = OAuthCredential(
        user_id=20,
        provider="pipedrive",
        access_token_ciphertext=vault_mod.encrypt("dummy_access"),
        refresh_token_ciphertext=vault_mod.encrypt("dummy_refresh"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scope="base api_domain:https://acme.pipedrive.com",
    )
    cfg = UserIntegrationCredential(
        user_id=20,
        provider="pipedrive",
        token_ciphertext=vault_mod.encrypt("pipedrive-config"),
        config={"default_pipeline_id": 1, "default_stage_id": 5},
    )
    async with patched_session_factory() as s:
        s.add(user)
        s.add(query)
        for lead in leads:
            s.add(lead)
        s.add(cred)
        s.add(cfg)
        await s.commit()

    from leadgen.integrations import pipedrive as pd_mod

    class _StubClient:
        def __init__(self, _token: str, _domain: str, **_kw) -> None:
            self.persons = 0
            self.deals = 0

        async def __aenter__(self) -> _StubClient:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        async def upsert_person(
            self, _person: pd_mod.PipedrivePersonInput
        ) -> str:
            self.persons += 1
            return f"person-{self.persons}"

        async def create_deal(
            self,
            *,
            person_id: str,
            title: str,
            pipeline_id: int,
            stage_id: int,
        ) -> str:
            self.deals += 1
            assert pipeline_id == 1
            assert stage_id == 5
            return f"deal-{self.deals}"

    monkeypatch.setattr(pd_mod, "PipedriveClient", _StubClient)

    r = _client_for(user).post(
        "/api/v1/leads/export-to-pipedrive",
        json={"lead_ids": [str(lead.id) for lead in leads]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success_count"] == 2
    assert body["failure_count"] == 0


def test_person_to_payload_drops_blanks():
    from leadgen.integrations.pipedrive import (
        PipedrivePersonInput,
        _person_to_payload,
    )

    out = _person_to_payload(
        PipedrivePersonInput(
            name="Alice Cooper",
            email=None,
            phone=None,
            org_name=None,
        )
    )
    assert out == {"name": "Alice Cooper"}

    out = _person_to_payload(
        PipedrivePersonInput(
            name="Bob",
            email="b@example.com",
            phone="+4917000000",
            org_name="Acme",
        )
    )
    assert out["email"][0]["value"] == "b@example.com"
    assert out["email"][0]["primary"] is True
    assert out["phone"][0]["value"] == "+4917000000"
    assert out["org_name"] == "Acme"


def test_build_authorize_url_includes_state():
    from leadgen.integrations.pipedrive import build_authorize_url

    url = build_authorize_url(
        client_id="cid",
        redirect_uri="https://convioo.com/cb",
        state="42:abc",
    )
    assert "client_id=cid" in url
    assert "state=42%3Aabc" in url
    assert url.startswith("https://oauth.pipedrive.com/oauth/authorize?")
