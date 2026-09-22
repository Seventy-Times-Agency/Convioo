"""Demo mode: one-click login without registration, no email
verification, mock parser, and the guarantee that a hosted deploy
with real keys never exposes any of it."""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.config import get_settings
from leadgen.db import session as db_session_mod
from leadgen.db.models import Base, Funnel, Lead, Team, User
from leadgen.utils import rate_limit as rate_limit_mod


@pytest_asyncio.fixture
async def db_engine():
    from sqlalchemy.pool import StaticPool

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
    maker = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr(db_session_mod, "_engine", db_engine)
    monkeypatch.setattr(db_session_mod, "_session_factory", maker)
    return maker


@pytest.fixture
def demo_on(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("DEMO_MODE", raising=False)
    get_settings.cache_clear()


@pytest.fixture
def demo_off(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "0")
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("DEMO_MODE", raising=False)
    get_settings.cache_clear()


def _client() -> TestClient:
    from leadgen.adapters.web_api import create_app

    return TestClient(create_app())


# ── flag resolution ────────────────────────────────────────────────────


def test_demo_auto_resolves_by_environment(monkeypatch):
    # zero-config: sqlite + no Google key → demo on
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    get_settings.cache_clear()
    assert get_settings().demo_active is True

    # a hosted deploy with Postgres + a real key → demo off
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://user:pass@localhost/convloo"
    )
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "real-key")
    get_settings.cache_clear()
    assert get_settings().demo_active is False

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    get_settings.cache_clear()


# ── the demo entry point ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_demo_login_provisions_everything(
    patched_session_factory, demo_on
):
    client = _client()
    assert client.get("/api/v1/auth/demo").json() == {"enabled": True}

    r = client.post("/api/v1/auth/demo?role=sales")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == "sales@demo.local"
    assert body["email_verified"] is True

    # The session cookie works straight away — no verification step.
    teams = client.get("/api/v1/teams").json()
    assert teams and teams[0]["role"] == "sales"

    async with patched_session_factory() as session:
        users = (await session.execute(select(User))).scalars().all()
        assert len(users) == 4  # owner/admin/manager/sales
        assert (await session.execute(select(Team))).scalars().all()
        funnels = (await session.execute(select(Funnel))).scalars().all()
        assert funnels[0].goal_name == "Платный аудит"
        leads = (await session.execute(select(Lead))).scalars().all()
        assert len(leads) == 10
        # шесть закреплены за селзом → очередь «Работы» не пустая
        assert sum(1 for lead in leads if lead.owner_user_id) == 6

    # Re-entering is idempotent — no duplicate team/leads.
    assert client.post("/api/v1/auth/demo?role=owner").status_code == 200
    async with patched_session_factory() as session:
        assert len((await session.execute(select(Lead))).scalars().all()) == 10


@pytest.mark.asyncio
async def test_demo_login_role_validation(patched_session_factory, demo_on):
    client = _client()
    assert client.post("/api/v1/auth/demo?role=hacker").status_code == 400


@pytest.mark.asyncio
async def test_demo_off_hides_the_endpoint(patched_session_factory, demo_off):
    client = _client()
    assert client.get("/api/v1/auth/demo").json() == {"enabled": False}
    assert client.post("/api/v1/auth/demo?role=owner").status_code == 404


@pytest.mark.asyncio
async def test_registration_skips_verification_only_in_demo(
    patched_session_factory, demo_on
):
    rate_limit_mod.register_limiter._events.clear()
    client = _client()
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Демо",
            "last_name": "Юзер",
            "email": "fresh@demo.local",
            "password": "correcthorse123",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["email_verified"] is True


# ── mock parser ────────────────────────────────────────────────────────


def test_mock_collector_shape():
    from leadgen.collectors.mock import demo_leads

    leads = demo_leads("барбершопы", "Тампа, Флорида", 12)
    assert len(leads) == 12
    # отсортированы по скору — как отдал бы настоящий скоринг
    scores = [x.raw["demo"]["score"] for x in leads]
    assert scores == sorted(scores, reverse=True)
    for lead in leads:
        assert lead.name and lead.phone and lead.address
        demo = lead.raw["demo"]
        assert demo["summary"] and demo["advice"]
        assert demo["strengths"] and demo["weaknesses"]
        assert demo["business_language"] in (None, "ru", "uk")
    # ниша попадает в вывеску
    assert any("Барбершоп" in x.name for x in leads)
    # латиница приводится к единственному числу
    assert any(
        "Bakery" in x.name for x in demo_leads("bakeries", "Miami", 6)
    )
    # часть лидов без сайта — есть что показать в фильтрах
    assert any(x.website is None for x in leads)


@pytest.mark.asyncio
async def test_demo_enrichment_applies_mock_analysis(
    patched_session_factory, demo_on
):
    """Demo enrichment copies the mock analysis onto leads and never
    touches Google/Anthropic (collector is None)."""
    import uuid

    from leadgen.db.models import SearchQuery
    from leadgen.pipeline.enrichment import enrich_leads

    async with patched_session_factory() as session:
        sq = SearchQuery(
            id=uuid.uuid4(),
            user_id=1,
            niche="барбершопы",
            region="Тампа",
            status="done",
            source="web",
        )
        session.add(sq)
        await session.flush()
        lead = Lead(
            id=uuid.uuid4(),
            query_id=sq.id,
            name="Demo Barbershop",
            source="google_places",
            source_id="demo-x",
            lead_status="new",
            raw={
                "demo": {
                    "score": 88,
                    "business_language": "uk",
                    "owner": "Тарас Ш.",
                    "summary": "выжимка",
                    "advice": "заход",
                    "strengths": ["плюс"],
                    "weaknesses": ["минус"],
                    "tags": ["RU/UA"],
                }
            },
        )
        session.add(lead)
        await session.commit()
        lead_id = lead.id

        out = await enrich_leads([lead], None, "барбершопы", "Тампа")
        assert out and out[0]["score_ai"] == 88

    async with patched_session_factory() as session:
        stored = await session.get(Lead, lead_id)
        assert stored.enriched is True
        assert stored.score_ai == 88
        assert stored.business_language == "uk"
        assert stored.advice == "заход"
        assert stored.website_meta["contact_person"]["name"] == "Тарас Ш."
