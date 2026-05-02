"""Lead tags: CRUD + assignment + lead-response join."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
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


def _register(client: TestClient, email: str = "tagger@example.test") -> int:
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Tag",
            "last_name": "Owner",
            "email": email,
            "password": "correcthorse123",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


async def _seed_lead(maker, *, user_id: int) -> uuid.UUID:
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
            name="Roofers Inc",
            source="google_places",
            source_id="place-tag-1",
        )
        session.add(lead)
        await session.commit()
        return lead.id


@pytest.mark.asyncio
async def test_full_tag_lifecycle(client: TestClient, patched_session_factory):
    user_id = _register(client)
    lead_id = await _seed_lead(patched_session_factory, user_id=user_id)

    # Empty palette to start.
    r = client.get("/api/v1/tags")
    assert r.status_code == 200
    assert r.json() == {"items": []}

    # Create two tags.
    r = client.post("/api/v1/tags", json={"name": "Hot lead", "color": "red"})
    assert r.status_code == 200, r.text
    hot_tag = r.json()
    assert hot_tag["color"] == "red"

    r = client.post("/api/v1/tags", json={"name": "Decision-maker", "color": "blue"})
    assert r.status_code == 200
    dm_tag = r.json()

    # Duplicate name → 409.
    r = client.post("/api/v1/tags", json={"name": "Hot lead"})
    assert r.status_code == 409

    # List should now show both.
    r = client.get("/api/v1/tags")
    assert {t["name"] for t in r.json()["items"]} == {"Hot lead", "Decision-maker"}

    # Assign one tag to the lead.
    r = client.put(
        f"/api/v1/leads/{lead_id}/tags",
        json={"tag_ids": [hot_tag["id"]]},
    )
    assert r.status_code == 200
    assert [t["id"] for t in r.json()["items"]] == [hot_tag["id"]]

    # Lead listing now carries the chip.
    r = client.get("/api/v1/leads", params={"user_id": user_id})
    body = r.json()
    target = next(item for item in body["leads"] if item["id"] == str(lead_id))
    assert [t["id"] for t in target["user_tags"]] == [hot_tag["id"]]

    # Replace with both tags.
    r = client.put(
        f"/api/v1/leads/{lead_id}/tags",
        json={"tag_ids": [hot_tag["id"], dm_tag["id"]]},
    )
    assert r.status_code == 200
    assert {t["id"] for t in r.json()["items"]} == {hot_tag["id"], dm_tag["id"]}

    # tag_id filter on the listing endpoint.
    r = client.get(
        "/api/v1/leads",
        params={"user_id": user_id, "tag_id": dm_tag["id"]},
    )
    assert r.status_code == 200
    matched_ids = [item["id"] for item in r.json()["leads"]]
    assert str(lead_id) in matched_ids

    # Filter by an unrelated tag id → empty.
    r = client.get(
        "/api/v1/leads",
        params={"user_id": user_id, "tag_id": str(uuid.uuid4())},
    )
    assert r.status_code == 200
    assert r.json()["leads"] == []

    # Rename + recolor.
    r = client.patch(
        f"/api/v1/tags/{hot_tag['id']}",
        json={"name": "Very hot", "color": "orange"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Very hot"
    assert r.json()["color"] == "orange"

    # Detach all tags.
    r = client.put(f"/api/v1/leads/{lead_id}/tags", json={"tag_ids": []})
    assert r.status_code == 200
    assert r.json() == {"items": []}

    # Delete a tag.
    r = client.delete(f"/api/v1/tags/{dm_tag['id']}")
    assert r.status_code == 200
    r = client.get("/api/v1/tags")
    assert {t["name"] for t in r.json()["items"]} == {"Very hot"}


@pytest.mark.asyncio
async def test_tag_endpoints_require_auth(client: TestClient):
    r = client.get("/api/v1/tags")
    assert r.status_code == 401
    r = client.post("/api/v1/tags", json={"name": "x"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_assign_rejects_other_users_tag(
    client: TestClient, patched_session_factory
):
    """A user can't attach someone else's personal tag to their lead."""
    # User A creates a personal tag.
    _register(client, email="alice@example.test")
    r = client.post("/api/v1/tags", json={"name": "Alice tag", "color": "violet"})
    alice_tag = r.json()

    # User B logs in (clear cookie first by registering — register
    # replaces the cookie).
    _register(client, email="bob@example.test")
    bob_user_id = client.get("/api/v1/auth/me").json()["user_id"]
    lead_id = await _seed_lead(patched_session_factory, user_id=bob_user_id)

    r = client.put(
        f"/api/v1/leads/{lead_id}/tags",
        json={"tag_ids": [alice_tag["id"]]},
    )
    assert r.status_code == 403
