"""Per-team lead status palette: CRUD + seeding + lead-update validation."""

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
    LeadStatus,
    SearchQuery,
    Team,
    TeamMembership,
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
        "search_user_limiter",
        "search_team_limiter",
        "search_ip_limiter",
        "assistant_user_limiter",
        "assistant_team_limiter",
    ):
        getattr(rate_limit_mod, name)._events.clear()
    yield


@pytest.fixture
def client(patched_session_factory):
    from leadgen.adapters.web_api import create_app

    return TestClient(create_app())


def _register(client: TestClient, email: str = "owner@example.test") -> int:
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Pipe",
            "last_name": "Owner",
            "email": email,
            "password": "correcthorse123",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


async def _create_team(maker, owner_id: int) -> uuid.UUID:
    """Seed a team + membership directly in the DB (mirrors what
    POST /api/v1/teams does, but skips the route to keep the test
    surface small)."""
    async with maker() as session:
        team = Team(name="Pipeline test", plan="free")
        session.add(team)
        await session.flush()
        session.add(
            TeamMembership(team_id=team.id, user_id=owner_id, role="owner")
        )
        # Mirror what create_team does: seed the default palette so
        # the test exercises the same shape as the real endpoint.
        from leadgen.adapters.web_api.app import _seed_default_lead_statuses

        _seed_default_lead_statuses(session, team.id)
        await session.commit()
        return team.id


@pytest.mark.asyncio
async def test_seeded_palette_has_five_legacy_keys(
    client: TestClient, patched_session_factory
):
    owner_id = _register(client)
    team_id = await _create_team(patched_session_factory, owner_id)
    r = client.get(f"/api/v1/teams/{team_id}/statuses")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    keys = {i["key"] for i in items}
    assert keys == {"new", "contacted", "replied", "won", "archived"}
    # Terminal-status flag wired correctly.
    by_key = {i["key"]: i for i in items}
    assert by_key["won"]["is_terminal"] is True
    assert by_key["archived"]["is_terminal"] is True
    assert by_key["new"]["is_terminal"] is False


@pytest.mark.asyncio
async def test_create_update_reorder_delete(
    client: TestClient, patched_session_factory
):
    owner_id = _register(client)
    team_id = await _create_team(patched_session_factory, owner_id)

    # Create a custom status.
    r = client.post(
        f"/api/v1/teams/{team_id}/statuses",
        json={"key": "qualified", "label": "Квалифицирован", "color": "violet"},
    )
    assert r.status_code == 200, r.text
    qualified = r.json()
    assert qualified["color"] == "violet"
    assert qualified["order_index"] >= 5  # appended at end

    # Duplicate key → 409.
    r = client.post(
        f"/api/v1/teams/{team_id}/statuses",
        json={"key": "qualified", "label": "x"},
    )
    assert r.status_code == 409

    # Rename + recolor.
    r = client.patch(
        f"/api/v1/teams/{team_id}/statuses/{qualified['id']}",
        json={"label": "Hot lead", "color": "red"},
    )
    assert r.status_code == 200
    assert r.json()["label"] == "Hot lead"
    assert r.json()["color"] == "red"

    # Reorder: move 'qualified' to position 0.
    list_r = client.get(f"/api/v1/teams/{team_id}/statuses").json()["items"]
    ids = [i["id"] for i in list_r]
    new_order = [qualified["id"]] + [i for i in ids if i != qualified["id"]]
    r = client.post(
        f"/api/v1/teams/{team_id}/statuses/reorder",
        json={"ordered_ids": new_order},
    )
    assert r.status_code == 200
    assert r.json()["items"][0]["id"] == qualified["id"]

    # Delete a status that has no leads attached → 200.
    r = client.delete(
        f"/api/v1/teams/{team_id}/statuses/{qualified['id']}"
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_delete_refuses_if_lead_uses_status(
    client: TestClient, patched_session_factory
):
    owner_id = _register(client)
    team_id = await _create_team(patched_session_factory, owner_id)

    # Find the seeded "new" status row.
    async with patched_session_factory() as session:
        new_status = (
            await session.execute(
                select(LeadStatus)
                .where(LeadStatus.team_id == team_id)
                .where(LeadStatus.key == "new")
            )
        ).scalar_one()

        # Seed a search + lead in this team using the "new" status.
        sq = SearchQuery(
            id=uuid.uuid4(),
            user_id=owner_id,
            team_id=team_id,
            niche="x",
            region="y",
            status="done",
            source="web",
        )
        session.add(sq)
        await session.flush()
        session.add(
            Lead(
                id=uuid.uuid4(),
                query_id=sq.id,
                name="LiveLead",
                source="google_places",
                source_id="place-1",
                lead_status="new",
            )
        )
        await session.commit()

    r = client.delete(f"/api/v1/teams/{team_id}/statuses/{new_status.id}")
    assert r.status_code == 409
    assert "still use this status" in r.json()["detail"]


@pytest.mark.asyncio
async def test_lead_patch_accepts_custom_team_status(
    client: TestClient, patched_session_factory
):
    owner_id = _register(client)
    team_id = await _create_team(patched_session_factory, owner_id)

    # Add a custom status.
    r = client.post(
        f"/api/v1/teams/{team_id}/statuses",
        json={"key": "qualified", "label": "Q", "color": "blue"},
    )
    assert r.status_code == 200

    # Seed a team-mode lead.
    lead_id = uuid.uuid4()
    async with patched_session_factory() as session:
        sq = SearchQuery(
            id=uuid.uuid4(),
            user_id=owner_id,
            team_id=team_id,
            niche="x",
            region="y",
            status="done",
            source="web",
        )
        session.add(sq)
        await session.flush()
        session.add(
            Lead(
                id=lead_id,
                query_id=sq.id,
                name="L",
                source="google_places",
                source_id="p1",
                lead_status="new",
            )
        )
        await session.commit()

    # Patch with the custom key — accepted.
    r = client.patch(
        f"/api/v1/leads/{lead_id}",
        json={"lead_status": "qualified"},
    )
    assert r.status_code == 200
    assert r.json()["lead_status"] == "qualified"

    # Patch with a non-existent key — rejected.
    r = client.patch(
        f"/api/v1/leads/{lead_id}",
        json={"lead_status": "totally-fake"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_lead_patch_personal_mode_keeps_legacy_validation(
    client: TestClient, patched_session_factory
):
    owner_id = _register(client)

    # Seed a personal lead (no team).
    lead_id = uuid.uuid4()
    async with patched_session_factory() as session:
        sq = SearchQuery(
            id=uuid.uuid4(),
            user_id=owner_id,
            team_id=None,
            niche="x",
            region="y",
            status="done",
            source="web",
        )
        session.add(sq)
        await session.flush()
        session.add(
            Lead(
                id=lead_id,
                query_id=sq.id,
                name="L",
                source="google_places",
                source_id="p1",
                lead_status="new",
            )
        )
        await session.commit()

    # Legacy key — accepted.
    r = client.patch(
        f"/api/v1/leads/{lead_id}", json={"lead_status": "won"}
    )
    assert r.status_code == 200

    # Custom key — rejected (no team palette to look at).
    r = client.patch(
        f"/api/v1/leads/{lead_id}", json={"lead_status": "qualified"}
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_outsider_cannot_touch_team_palette(
    client: TestClient, patched_session_factory
):
    owner_id = _register(client, email="owner-team@example.test")
    team_id = await _create_team(patched_session_factory, owner_id)

    # Sign up as a different user.
    _register(client, email="outsider@example.test")

    r = client.get(f"/api/v1/teams/{team_id}/statuses")
    assert r.status_code == 403

    r = client.post(
        f"/api/v1/teams/{team_id}/statuses",
        json={"key": "x", "label": "X"},
    )
    assert r.status_code == 403
