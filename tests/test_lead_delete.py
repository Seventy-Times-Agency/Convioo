"""DELETE /api/v1/leads/{id} integration test.

Stands up an in-memory SQLite engine, registers a user (which mints
a session cookie), seeds a SearchQuery + Lead, then walks through
both delete modes.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.db import session as db_session_mod
from leadgen.db.models import (
    Base,
    Lead,
    SearchQuery,
    User,
    UserSeenLead,
)
from leadgen.utils import rate_limit as rate_limit_mod


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
def client(patched_session_factory):
    from leadgen.adapters.web_api import create_app

    return TestClient(create_app())


def _register(client: TestClient) -> int:
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Sam",
            "last_name": "Owner",
            "email": "owner@example.test",
            "password": "correcthorse123",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


async def _seed_lead(
    maker, *, user_id: int, source_id: str = "place-A", phone: str | None = "+14155550100",
    website: str | None = "https://www.acme.com",
) -> uuid.UUID:
    async with maker() as session:
        query = SearchQuery(
            id=uuid.uuid4(),
            user_id=user_id,
            niche="roofing",
            region="NYC",
            status="done",
            source="web",
        )
        session.add(query)
        await session.flush()
        lead = Lead(
            id=uuid.uuid4(),
            query_id=query.id,
            name="Acme Roofing",
            source="google_places",
            source_id=source_id,
            phone=phone,
            website=website,
        )
        session.add(lead)
        await session.commit()
        return lead.id


@pytest.mark.asyncio
async def test_soft_delete_hides_lead_from_list(
    client: TestClient, patched_session_factory
) -> None:
    user_id = _register(client)
    lead_id = await _seed_lead(patched_session_factory, user_id=user_id)

    # Lead visible before deletion.
    r = client.get("/api/v1/leads", params={"user_id": user_id})
    assert r.status_code == 200
    assert any(item["id"] == str(lead_id) for item in r.json()["leads"])

    r = client.delete(f"/api/v1/leads/{lead_id}")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "forever": False}

    # Lead hidden afterwards.
    r = client.get("/api/v1/leads", params={"user_id": user_id})
    assert r.status_code == 200
    assert all(item["id"] != str(lead_id) for item in r.json()["leads"])

    # Row still exists with deleted_at populated, blacklist NOT set.
    async with patched_session_factory() as session:
        lead = await session.get(Lead, lead_id)
        assert lead is not None
        assert lead.deleted_at is not None
        assert lead.blacklisted is False
        # No UserSeenLead row should have been written for the soft-only path.
        seen = (
            await session.execute(
                select(UserSeenLead).where(UserSeenLead.user_id == user_id)
            )
        ).scalar_one_or_none()
        assert seen is None


@pytest.mark.asyncio
async def test_delete_forever_blacklists_and_writes_seen_lead(
    client: TestClient, patched_session_factory
) -> None:
    user_id = _register(client)
    lead_id = await _seed_lead(
        patched_session_factory,
        user_id=user_id,
        source_id="place-B",
        phone="+1 (415) 555-0101",
        website="https://shop.example.test/abc",
    )

    r = client.delete(f"/api/v1/leads/{lead_id}", params={"forever": "true"})
    assert r.status_code == 200, r.text
    assert r.json()["forever"] is True

    async with patched_session_factory() as session:
        lead = await session.get(Lead, lead_id)
        assert lead is not None
        assert lead.deleted_at is not None
        assert lead.blacklisted is True
        seen = (
            await session.execute(
                select(UserSeenLead)
                .where(UserSeenLead.user_id == user_id)
                .where(UserSeenLead.source == "google_places")
                .where(UserSeenLead.source_id == "place-B")
            )
        ).scalar_one()
        # Phone normalised, domain extracted.
        assert seen.phone_e164 == "+14155550101"
        assert seen.domain_root == "shop.example.test"


@pytest.mark.asyncio
async def test_delete_requires_authentication(
    client: TestClient, patched_session_factory
) -> None:
    # Seed a lead without registering anyone first.
    async with patched_session_factory() as session:
        user = User(id=-12345, queries_limit=5, email="other@example.test")
        session.add(user)
        await session.commit()
    lead_id = await _seed_lead(patched_session_factory, user_id=-12345)
    # No cookie attached → 401.
    r = client.delete(f"/api/v1/leads/{lead_id}")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_delete_rejects_other_users_lead(
    client: TestClient, patched_session_factory
) -> None:
    # Owner of the lead is some other user; the signed-in user can't delete it.
    async with patched_session_factory() as session:
        owner = User(id=-99999, queries_limit=5, email="alice@example.test")
        session.add(owner)
        await session.commit()
    lead_id = await _seed_lead(patched_session_factory, user_id=-99999)

    _register(client)  # different user, takes the cookie

    r = client.delete(f"/api/v1/leads/{lead_id}")
    assert r.status_code == 403
