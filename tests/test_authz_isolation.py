"""Authorization isolation: identity comes from the session, not params.

Regression tests for the P0 IDOR fixes (docs/AUDIT_2026-06-10.md):
user B must never be able to read or mutate user A's leads, searches
or templates by guessing ids or passing spoofed ``user_id`` /
``by_user_id`` parameters. Cross-user access answers 404 so resource
ids can't be probed for existence; missing auth answers 401.

Also covers ``assert_production_secrets`` — the fail-fast guard that
crashes a Railway deploy with empty AUTH_JWT_SECRET / FERNET_KEY.
"""

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
    Team,
    TeamMembership,
)
from leadgen.utils import rate_limit as rate_limit_mod


@pytest_asyncio.fixture
async def db_engine():
    # StaticPool keeps the in-memory DB on a single shared connection
    # so background tasks don't pull a schema-less connection from the
    # pool and pollute it.
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
        "invite_create_limiter",
        "sequence_create_limiter",
        "webhook_create_limiter",
        "webhook_test_limiter",
        "report_create_limiter",
    ):
        getattr(rate_limit_mod, name)._events.clear()
    yield


def _make_client(patched_session_factory) -> TestClient:
    from leadgen.adapters.web_api import create_app

    return TestClient(create_app())


@pytest.fixture
def client(patched_session_factory):
    return _make_client(patched_session_factory)


def _register(client: TestClient, email: str) -> int:
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Iso",
            "last_name": "Tester",
            "email": email,
            "password": "correcthorse123",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


async def _seed_personal_lead(
    maker, *, user_id: int
) -> tuple[uuid.UUID, uuid.UUID]:
    """Insert a personal (no-team) search + one lead owned by user_id."""
    async with maker() as session:
        sq = SearchQuery(
            id=uuid.uuid4(),
            user_id=user_id,
            team_id=None,
            niche="roofing",
            region="New York",
            status="done",
            source="web",
        )
        session.add(sq)
        await session.flush()
        lead = Lead(
            id=uuid.uuid4(),
            query_id=sq.id,
            name="Acme Roofing",
            source="google_places",
            source_id="place-iso-1",
            lead_status="new",
        )
        session.add(lead)
        await session.commit()
        return sq.id, lead.id


# ── Unauthenticated access ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unauthenticated_requests_get_401(
    client: TestClient, patched_session_factory
):
    r = client.get("/api/v1/leads")
    assert r.status_code == 401

    r = client.get("/api/v1/teams")
    assert r.status_code == 401

    r = client.patch(
        "/api/v1/leads/bulk",
        json={"lead_ids": [str(uuid.uuid4())], "lead_status": "won"},
    )
    assert r.status_code == 401

    r = client.get("/api/v1/searches")
    assert r.status_code == 401

    r = client.get("/api/v1/stats")
    assert r.status_code == 401


# ── Cross-user isolation: leads + searches ─────────────────────────────


@pytest.mark.asyncio
async def test_user_b_cannot_read_or_patch_user_a_lead_and_search(
    patched_session_factory,
):
    client_a = _make_client(patched_session_factory)
    client_b = _make_client(patched_session_factory)
    user_a = _register(client_a, "iso-a@example.test")
    _register(client_b, "iso-b@example.test")

    search_id, lead_id = await _seed_personal_lead(
        patched_session_factory, user_id=user_a
    )

    # Owner sees their own data.
    r = client_a.get(f"/api/v1/searches/{search_id}")
    assert r.status_code == 200, r.text
    r = client_a.get(f"/api/v1/searches/{search_id}/leads")
    assert r.status_code == 200
    assert len(r.json()) == 1
    r = client_a.patch(
        f"/api/v1/leads/{lead_id}", json={"lead_status": "contacted"}
    )
    assert r.status_code == 200, r.text

    # A stranger gets 404 — not 403 — so ids can't be probed.
    r = client_b.get(f"/api/v1/searches/{search_id}")
    assert r.status_code == 404
    r = client_b.get(f"/api/v1/searches/{search_id}/leads")
    assert r.status_code == 404
    r = client_b.get(f"/api/v1/searches/{search_id}/export.xlsx")
    assert r.status_code == 404
    r = client_b.patch(
        f"/api/v1/leads/{lead_id}", json={"lead_status": "won"}
    )
    assert r.status_code == 404
    r = client_b.put(
        f"/api/v1/leads/{lead_id}/mark", json={"color": "red"}
    )
    assert r.status_code == 404
    r = client_b.post(
        f"/api/v1/leads/{lead_id}/draft-email",
        json={"tone": "professional"},
    )
    assert r.status_code == 404

    # The patch from B above must not have landed.
    async with patched_session_factory() as session:
        lead = await session.get(Lead, lead_id)
        assert lead.lead_status == "contacted"


@pytest.mark.asyncio
async def test_leads_list_ignores_spoofed_user_id_param(
    patched_session_factory,
):
    client_a = _make_client(patched_session_factory)
    client_b = _make_client(patched_session_factory)
    user_a = _register(client_a, "iso-list-a@example.test")
    _register(client_b, "iso-list-b@example.test")
    await _seed_personal_lead(patched_session_factory, user_id=user_a)

    # A sees their lead.
    r = client_a.get("/api/v1/leads")
    assert r.status_code == 200
    assert r.json()["total"] == 1

    # B passing A's user_id as a query param gets their own (empty)
    # workspace — the legacy param is silently ignored.
    r = client_b.get("/api/v1/leads", params={"user_id": user_a})
    assert r.status_code == 200
    assert r.json()["total"] == 0
    assert r.json()["leads"] == []


@pytest.mark.asyncio
async def test_bulk_update_silently_drops_foreign_lead_ids(
    patched_session_factory,
):
    client_a = _make_client(patched_session_factory)
    client_b = _make_client(patched_session_factory)
    user_a = _register(client_a, "iso-bulk-a@example.test")
    _register(client_b, "iso-bulk-b@example.test")
    _search_id, lead_id = await _seed_personal_lead(
        patched_session_factory, user_id=user_a
    )

    # B sweeps A's lead id into a bulk status change → 0 rows touched.
    r = client_b.patch(
        "/api/v1/leads/bulk",
        json={"lead_ids": [str(lead_id)], "lead_status": "won"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 0
    async with patched_session_factory() as session:
        lead = await session.get(Lead, lead_id)
        assert lead.lead_status == "new"

    # The owner's own bulk update works.
    r = client_a.patch(
        "/api/v1/leads/bulk",
        json={"lead_ids": [str(lead_id)], "lead_status": "won"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 1
    async with patched_session_factory() as session:
        lead = await session.get(Lead, lead_id)
        assert lead.lead_status == "won"


# ── Cross-user isolation: templates ────────────────────────────────────


@pytest.mark.asyncio
async def test_user_b_cannot_touch_user_a_templates(
    patched_session_factory,
):
    client_a = _make_client(patched_session_factory)
    client_b = _make_client(patched_session_factory)
    _register(client_a, "iso-tpl-a@example.test")
    _register(client_b, "iso-tpl-b@example.test")

    r = client_a.post(
        "/api/v1/templates",
        json={"name": "Intro", "body": "Hello {{name}}"},
    )
    assert r.status_code == 200, r.text
    template_id = r.json()["id"]

    # B's library is empty; A's template is invisible to B.
    r = client_b.get("/api/v1/templates")
    assert r.status_code == 200
    assert r.json()["items"] == []

    r = client_b.patch(
        f"/api/v1/templates/{template_id}", json={"name": "Stolen"}
    )
    assert r.status_code == 404
    r = client_b.delete(f"/api/v1/templates/{template_id}")
    assert r.status_code == 404

    # Still intact for A.
    r = client_a.get("/api/v1/templates")
    assert [t["name"] for t in r.json()["items"]] == ["Intro"]

    # Unauthenticated template list → 401.
    fresh = _make_client(patched_session_factory)
    assert fresh.get("/api/v1/templates").status_code == 401


# ── Teams: members-summary is owner-only ───────────────────────────────


@pytest.mark.asyncio
async def test_members_summary_rejects_non_owner_member(
    patched_session_factory,
):
    client_owner = _make_client(patched_session_factory)
    client_member = _make_client(patched_session_factory)
    owner_id = _register(client_owner, "iso-team-owner@example.test")
    member_id = _register(client_member, "iso-team-member@example.test")

    async with patched_session_factory() as session:
        team = Team(name="Iso team", plan="free")
        session.add(team)
        await session.flush()
        session.add(
            TeamMembership(team_id=team.id, user_id=owner_id, role="owner")
        )
        session.add(
            TeamMembership(team_id=team.id, user_id=member_id, role="member")
        )
        await session.commit()
        team_id = team.id

    r = client_owner.get(f"/api/v1/teams/{team_id}/members-summary")
    assert r.status_code == 200, r.text
    assert {m["user_id"] for m in r.json()} == {owner_id, member_id}

    # Plain member → 403 (it is a real team they belong to, so the
    # team's existence isn't a secret to them).
    r = client_member.get(f"/api/v1/teams/{team_id}/members-summary")
    assert r.status_code == 403

    # Outsider spoofing the owner's id in the legacy query param still
    # bounces — identity comes from the session only.
    client_outsider = _make_client(patched_session_factory)
    _register(client_outsider, "iso-team-outsider@example.test")
    r = client_outsider.get(
        f"/api/v1/teams/{team_id}/members-summary",
        params={"user_id": owner_id},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_team_endpoints_ignore_spoofed_identity_params(
    patched_session_factory,
):
    client_owner = _make_client(patched_session_factory)
    client_outsider = _make_client(patched_session_factory)
    owner_id = _register(client_owner, "iso-spoof-owner@example.test")
    _register(client_outsider, "iso-spoof-out@example.test")

    r = client_owner.post("/api/v1/teams", json={"name": "Spoof team"})
    assert r.status_code == 200, r.text
    team_id = r.json()["id"]

    # Outsider PATCHes the team while claiming to be the owner via the
    # legacy by_user_id body field → ignored, 403.
    r = client_outsider.patch(
        f"/api/v1/teams/{team_id}",
        json={"by_user_id": owner_id, "name": "Hijacked"},
    )
    assert r.status_code == 403

    # Outsider can't list the owner's team via a spoofed user_id query
    # param — they only see their own (auto-created workspace) teams.
    r = client_outsider.get("/api/v1/teams", params={"user_id": owner_id})
    assert r.status_code == 200
    assert team_id not in {t["id"] for t in r.json()}

    # Invite creation with a spoofed by_user_id → 403 as well.
    r = client_outsider.post(
        f"/api/v1/teams/{team_id}/invites",
        json={"by_user_id": owner_id, "role": "member"},
    )
    assert r.status_code == 403


# ── Fail-fast production secrets ───────────────────────────────────────


def _settings_with(jwt: str, fernet: str):
    from leadgen.config import Settings

    return Settings(
        DATABASE_URL="postgresql://u:p@localhost:5432/x",
        AUTH_JWT_SECRET=jwt,
        FERNET_KEY=fernet,
    )


def test_assert_production_secrets_raises_on_railway_without_secrets(
    monkeypatch,
):
    from leadgen.config import assert_production_secrets

    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abc123")
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)

    with pytest.raises(RuntimeError) as exc:
        assert_production_secrets(_settings_with(jwt="", fernet=""))
    assert "AUTH_JWT_SECRET" in str(exc.value)
    assert "FERNET_KEY" in str(exc.value)

    # One missing secret is still fatal.
    with pytest.raises(RuntimeError) as exc:
        assert_production_secrets(
            _settings_with(jwt="super-secret", fernet="")
        )
    assert "FERNET_KEY" in str(exc.value)
    assert "AUTH_JWT_SECRET" not in str(exc.value)


def test_assert_production_secrets_ok_with_secrets_set(monkeypatch):
    from leadgen.config import assert_production_secrets

    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    assert_production_secrets(
        _settings_with(jwt="super-secret", fernet="f" * 44)
    )


def test_assert_production_secrets_noop_outside_railway(monkeypatch):
    from leadgen.config import assert_production_secrets

    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    # Empty secrets are fine locally / in CI.
    assert_production_secrets(_settings_with(jwt="", fernet=""))
