"""Wave-1 team roles: owner → admin → manager → sales.

Covers the four-role permission matrix, member CRUD (invite / change
role / remove with mandatory lead hand-over / ownership transfer) and
the server-side enforcement of the sales role: assigned leads only,
no prospecting, no exports, no money fields — checked at the API,
not just hidden in the UI.
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

from leadgen.core.services.team_permissions import (
    PERM_MANAGE_MEMBERS,
    PERM_RUN_SEARCH,
    PERM_VIEW_ANALYTICS,
    PERM_VIEW_MONEY,
    assignable_roles_for,
    has_permission,
    normalize_role,
)
from leadgen.db import session as db_session_mod
from leadgen.db.models import (
    Base,
    Lead,
    LeadActivity,
    SearchQuery,
    Team,
    TeamMembership,
)
from leadgen.utils import rate_limit as rate_limit_mod

# ── permission matrix (pure unit) ──────────────────────────────────────


def test_legacy_roles_normalise():
    assert normalize_role("member") == "manager"
    assert normalize_role("viewer") == "sales"
    assert normalize_role("Owner ") == "owner"
    assert normalize_role("garbage") == "sales"
    assert normalize_role(None) == "sales"


def test_matrix_shape():
    # Prospecting: manager+ only.
    assert has_permission("owner", PERM_RUN_SEARCH)
    assert has_permission("admin", PERM_RUN_SEARCH)
    assert has_permission("manager", PERM_RUN_SEARCH)
    assert not has_permission("sales", PERM_RUN_SEARCH)
    # Money: sales never sees it.
    assert has_permission("manager", PERM_VIEW_MONEY)
    assert not has_permission("sales", PERM_VIEW_MONEY)
    # Member management: admin+, not manager.
    assert has_permission("admin", PERM_MANAGE_MEMBERS)
    assert not has_permission("manager", PERM_MANAGE_MEMBERS)
    # Analytics: manager+.
    assert has_permission("manager", PERM_VIEW_ANALYTICS)
    assert not has_permission("sales", PERM_VIEW_ANALYTICS)


def test_assignable_roles():
    assert assignable_roles_for("owner") == ("admin", "manager", "sales")
    assert assignable_roles_for("admin") == ("manager", "sales")
    assert assignable_roles_for("manager") == ()
    assert assignable_roles_for("sales") == ()


# ── API harness ────────────────────────────────────────────────────────


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


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    for name in (
        "login_limiter",
        "register_limiter",
        "search_user_limiter",
        "search_team_limiter",
        "search_ip_limiter",
        "invite_create_limiter",
    ):
        getattr(rate_limit_mod, name)._events.clear()
    yield


def _make_client(patched_session_factory) -> TestClient:
    from leadgen.adapters.web_api import create_app

    return TestClient(create_app())


def _register(client: TestClient, email: str) -> int:
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Role",
            "last_name": "Tester",
            "email": email,
            "password": "correcthorse123",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


@pytest_asyncio.fixture
async def crew(patched_session_factory):
    """A team with one user per role + a seeded team lead.

    Returns a dict with clients, user ids, team id, and the ids of a
    team search + two leads (one assigned to the sales rep, one not).
    """
    maker = patched_session_factory
    clients = {
        role: _make_client(maker)
        for role in ("owner", "admin", "manager", "sales", "sales2")
    }
    ids = {}
    for role, c in clients.items():
        # The register endpoint is rate-limited to 3/hour per IP and
        # the TestClient always presents the same IP — clear between
        # signups so seeding five users doesn't trip it.
        rate_limit_mod.register_limiter._events.clear()
        ids[role] = _register(c, f"crew-{role}@example.test")
    team_id = uuid.uuid4()
    async with maker() as session:
        # Verify everyone's email so the search endpoint's verification
        # gate doesn't mask the role checks under test.
        from datetime import datetime, timezone

        from leadgen.db.models import User

        for uid in ids.values():
            u = await session.get(User, uid)
            u.email_verified_at = datetime.now(timezone.utc)
        session.add(Team(id=team_id, name="Dept", plan="free"))
        for role in ("owner", "admin", "manager", "sales"):
            session.add(
                TeamMembership(
                    team_id=team_id, user_id=ids[role], role=role
                )
            )
        session.add(
            TeamMembership(
                team_id=team_id, user_id=ids["sales2"], role="sales"
            )
        )
        sq = SearchQuery(
            id=uuid.uuid4(),
            user_id=ids["manager"],
            team_id=team_id,
            niche="roofing",
            region="Miami",
            status="done",
            source="web",
        )
        session.add(sq)
        await session.flush()
        assigned = Lead(
            id=uuid.uuid4(),
            query_id=sq.id,
            name="Assigned Roofing",
            source="google_places",
            source_id="place-assigned",
            lead_status="new",
            owner_user_id=ids["sales"],
            deal_value=1500.0,
        )
        other = Lead(
            id=uuid.uuid4(),
            query_id=sq.id,
            name="Unassigned Roofing",
            source="google_places",
            source_id="place-other",
            lead_status="new",
            deal_value=900.0,
        )
        session.add_all([assigned, other])
        await session.commit()
        return {
            "clients": clients,
            "ids": ids,
            "team_id": team_id,
            "search_id": sq.id,
            "assigned_lead": assigned.id,
            "other_lead": other.id,
        }


# ── member CRUD ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_cannot_invite_admin_owner_can(crew):
    team_id = crew["team_id"]
    r = crew["clients"]["admin"].post(
        f"/api/v1/teams/{team_id}/invites",
        json={"role": "admin", "ttl_seconds": 600},
    )
    assert r.status_code == 403
    r = crew["clients"]["owner"].post(
        f"/api/v1/teams/{team_id}/invites",
        json={"role": "admin", "ttl_seconds": 600},
    )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "admin"
    # Manager has no invite rights at all.
    r = crew["clients"]["manager"].post(
        f"/api/v1/teams/{team_id}/invites",
        json={"role": "sales", "ttl_seconds": 600},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_role_change_rules(crew):
    team_id = crew["team_id"]
    ids = crew["ids"]
    # Admin re-roles a sales rep to manager — allowed.
    r = crew["clients"]["admin"].patch(
        f"/api/v1/teams/{team_id}/members/{ids['sales2']}",
        json={"role": "manager"},
    )
    assert r.status_code == 200, r.text
    # Admin tries to mint another admin — denied.
    r = crew["clients"]["admin"].patch(
        f"/api/v1/teams/{team_id}/members/{ids['manager']}",
        json={"role": "admin"},
    )
    assert r.status_code == 403
    # Admin tries to touch the owner's seat — denied.
    r = crew["clients"]["admin"].patch(
        f"/api/v1/teams/{team_id}/members/{ids['owner']}",
        json={"role": "sales"},
    )
    assert r.status_code == 403
    # Owner promotes manager to admin — allowed.
    r = crew["clients"]["owner"].patch(
        f"/api/v1/teams/{team_id}/members/{ids['manager']}",
        json={"role": "admin"},
    )
    assert r.status_code == 200, r.text
    # Nobody assigns "owner" via PATCH — that's the transfer flow.
    r = crew["clients"]["owner"].patch(
        f"/api/v1/teams/{team_id}/members/{ids['admin']}",
        json={"role": "owner"},
    )
    assert r.status_code == 403
    # Owner can't demote themselves.
    r = crew["clients"]["owner"].patch(
        f"/api/v1/teams/{team_id}/members/{ids['owner']}",
        json={"role": "admin"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_transfer_ownership(crew, patched_session_factory):
    team_id = crew["team_id"]
    ids = crew["ids"]
    # Non-owner can't transfer.
    r = crew["clients"]["admin"].post(
        f"/api/v1/teams/{team_id}/transfer-ownership",
        json={"new_owner_user_id": ids["manager"]},
    )
    assert r.status_code == 403
    # Owner hands the seat to the admin.
    r = crew["clients"]["owner"].post(
        f"/api/v1/teams/{team_id}/transfer-ownership",
        json={"new_owner_user_id": ids["admin"]},
    )
    assert r.status_code == 200, r.text
    async with patched_session_factory() as session:
        rows = (
            await session.execute(
                select(TeamMembership).where(
                    TeamMembership.team_id == team_id
                )
            )
        ).scalars().all()
        by_user = {m.user_id: m.role for m in rows}
    assert by_user[ids["admin"]] == "owner"
    assert by_user[ids["owner"]] == "admin"


@pytest.mark.asyncio
async def test_remove_member_requires_lead_transfer(
    crew, patched_session_factory
):
    team_id = crew["team_id"]
    ids = crew["ids"]
    # Sales rep has one assigned lead → removal without transfer_to
    # is a 409 with the count in the message.
    r = crew["clients"]["owner"].delete(
        f"/api/v1/teams/{team_id}/members/{ids['sales']}"
    )
    assert r.status_code == 409
    assert "1 lead(s)" in r.json()["detail"]
    # transfer_to must be a member and not the leaver.
    r = crew["clients"]["owner"].delete(
        f"/api/v1/teams/{team_id}/members/{ids['sales']}",
        params={"transfer_to": ids["sales"]},
    )
    assert r.status_code == 400
    r = crew["clients"]["owner"].delete(
        f"/api/v1/teams/{team_id}/members/{ids['sales']}",
        params={"transfer_to": 999999},
    )
    assert r.status_code == 400
    # Proper hand-over: lead moves, membership gone, activity written.
    r = crew["clients"]["owner"].delete(
        f"/api/v1/teams/{team_id}/members/{ids['sales']}",
        params={"transfer_to": ids["sales2"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["transferred_leads"] == 1
    async with patched_session_factory() as session:
        lead = await session.get(Lead, crew["assigned_lead"])
        assert lead.owner_user_id == ids["sales2"]
        ms = (
            await session.execute(
                select(TeamMembership)
                .where(TeamMembership.team_id == team_id)
                .where(TeamMembership.user_id == ids["sales"])
            )
        ).scalar_one_or_none()
        assert ms is None
        act = (
            await session.execute(
                select(LeadActivity)
                .where(LeadActivity.lead_id == crew["assigned_lead"])
                .where(LeadActivity.kind == "assigned")
            )
        ).scalars().all()
        assert len(act) == 1
        assert act[0].payload["reason"] == "member_removed"


@pytest.mark.asyncio
async def test_remove_member_guards(crew):
    team_id = crew["team_id"]
    ids = crew["ids"]
    # The owner seat can't be removed.
    r = crew["clients"]["owner"].delete(
        f"/api/v1/teams/{team_id}/members/{ids['owner']}"
    )
    assert r.status_code == 400
    # Manager (no member management) can't remove a sales rep.
    r = crew["clients"]["manager"].delete(
        f"/api/v1/teams/{team_id}/members/{ids['sales2']}"
    )
    assert r.status_code == 403
    # Admin can't remove another admin (seed a second one first).
    r = crew["clients"]["owner"].patch(
        f"/api/v1/teams/{team_id}/members/{ids['manager']}",
        json={"role": "admin"},
    )
    assert r.status_code == 200
    r = crew["clients"]["admin"].delete(
        f"/api/v1/teams/{team_id}/members/{ids['manager']}"
    )
    assert r.status_code == 403
    # A non-owner may leave on their own (no assigned leads).
    r = crew["clients"]["sales2"].delete(
        f"/api/v1/teams/{team_id}/members/{ids['sales2']}"
    )
    assert r.status_code == 200, r.text


# ── sales scoping ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sales_cannot_launch_team_search(crew):
    r = crew["clients"]["sales"].post(
        "/api/v1/searches",
        json={
            "niche": "plumbing",
            "region": "Austin",
            "team_id": str(crew["team_id"]),
        },
    )
    assert r.status_code == 403
    assert "role" in r.json()["detail"]


@pytest.mark.asyncio
async def test_sales_lead_list_scoped_and_money_masked(crew):
    r = crew["clients"]["sales"].get(
        "/api/v1/leads", params={"team_id": str(crew["team_id"])}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    names = {lead["name"] for lead in body["leads"]}
    assert names == {"Assigned Roofing"}
    assert body["leads"][0]["deal_value"] is None
    # Manager sees the base through the member view (their own
    # searches by default) with money intact.
    r = crew["clients"]["manager"].get(
        "/api/v1/leads", params={"team_id": str(crew["team_id"])}
    )
    assert r.status_code == 200
    by_name = {
        lead["name"]: lead for lead in r.json()["leads"]
    }
    assert by_name["Assigned Roofing"]["deal_value"] == 1500.0


@pytest.mark.asyncio
async def test_sales_cannot_read_unassigned_lead(crew):
    r = crew["clients"]["sales"].get(
        f"/api/v1/leads/{crew['other_lead']}"
    )
    assert r.status_code == 404
    # The assigned one is fine — with money hidden.
    r = crew["clients"]["sales"].get(
        f"/api/v1/leads/{crew['assigned_lead']}"
    )
    assert r.status_code == 200
    assert r.json()["deal_value"] is None


@pytest.mark.asyncio
async def test_sales_update_rules(crew):
    lead_id = crew["assigned_lead"]
    # Status update on an assigned lead is the rep's daily work.
    r = crew["clients"]["sales"].patch(
        f"/api/v1/leads/{lead_id}", json={"lead_status": "contacted"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["deal_value"] is None
    # Money / assignment moves are manager+ calls.
    r = crew["clients"]["sales"].patch(
        f"/api/v1/leads/{lead_id}", json={"deal_value": 5000}
    )
    assert r.status_code == 403
    r = crew["clients"]["sales"].patch(
        f"/api/v1/leads/{lead_id}",
        json={"owner_user_id": crew["ids"]["sales2"]},
    )
    assert r.status_code == 403
    # Unassigned lead can't be touched at all.
    r = crew["clients"]["sales"].patch(
        f"/api/v1/leads/{crew['other_lead']}",
        json={"lead_status": "contacted"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_sales_cannot_delete_or_export(crew):
    r = crew["clients"]["sales"].delete(
        f"/api/v1/leads/{crew['assigned_lead']}"
    )
    assert r.status_code == 403
    r = crew["clients"]["sales"].get(
        "/api/v1/leads/export.csv",
        params={"team_id": str(crew["team_id"])},
    )
    assert r.status_code == 403
    # Manager exports fine.
    r = crew["clients"]["manager"].get(
        "/api/v1/leads/export.csv",
        params={"team_id": str(crew["team_id"])},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_sales_cannot_manage_statuses_manager_can(crew):
    team_id = crew["team_id"]
    r = crew["clients"]["sales"].post(
        f"/api/v1/teams/{team_id}/statuses",
        json={"key": "callback", "label": "Callback"},
    )
    assert r.status_code == 403
    r = crew["clients"]["manager"].post(
        f"/api/v1/teams/{team_id}/statuses",
        json={"key": "callback", "label": "Callback"},
    )
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_manager_sees_analytics_and_summary(crew):
    team_id = crew["team_id"]
    r = crew["clients"]["manager"].get(
        f"/api/v1/teams/{team_id}/analytics"
    )
    assert r.status_code == 200, r.text
    r = crew["clients"]["manager"].get(
        f"/api/v1/teams/{team_id}/members-summary"
    )
    assert r.status_code == 200, r.text
    r = crew["clients"]["sales"].get(
        f"/api/v1/teams/{team_id}/members-summary"
    )
    assert r.status_code == 403
