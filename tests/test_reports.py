"""Wave 4 — white-label client reports: stats, branding, share links."""

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

from leadgen.db import session as db_session_mod
from leadgen.db.models import (
    Base,
    ClientReport,
    Lead,
    LeadActivity,
    SearchQuery,
    Team,
    TeamMembership,
)
from leadgen.utils import rate_limit as rate_limit_mod

# 1x1 transparent PNG, base64 — a valid tiny logo for the happy path.
_TINY_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


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


@pytest.fixture
def client(patched_session_factory):
    from leadgen.adapters.web_api import create_app

    return TestClient(create_app())


def _register(client: TestClient, email: str = "owner@example.test") -> int:
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Report",
            "last_name": "Owner",
            "email": email,
            "password": "correcthorse123",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


async def _seed_team(maker, owner_id: int, role: str = "owner") -> uuid.UUID:
    async with maker() as session:
        team = Team(name="Agency", plan="free")
        session.add(team)
        await session.flush()
        session.add(
            TeamMembership(team_id=team.id, user_id=owner_id, role=role)
        )
        await session.commit()
        return team.id


async def _seed_search_with_leads(
    maker,
    owner_id: int,
    team_id: uuid.UUID | None,
) -> uuid.UUID:
    """Seed a search with a spread of leads: hot/cold, with/without
    email + phone, plus one reply activity."""
    async with maker() as session:
        sq = SearchQuery(
            id=uuid.uuid4(),
            user_id=owner_id,
            team_id=team_id,
            niche="roofers",
            region="New York",
            status="done",
            source="web",
            leads_count=3,
            analysis_summary={"insights": "Lots of stale websites."},
        )
        session.add(sq)
        await session.flush()

        hot = Lead(
            id=uuid.uuid4(),
            query_id=sq.id,
            name="Hot Co",
            source="google_places",
            source_id="p1",
            score_ai=88.0,
            contact_email="hot@hot.test",
            email_status="valid",
            phone="+12125551111",
            lead_status="new",
        )
        warm = Lead(
            id=uuid.uuid4(),
            query_id=sq.id,
            name="Warm Co",
            source="google_places",
            source_id="p2",
            score_ai=60.0,
            email_status="risky",
            phone=None,
            website_meta={"emails": ["warm@warm.test"]},
            lead_status="contacted",
        )
        cold = Lead(
            id=uuid.uuid4(),
            query_id=sq.id,
            name="Cold Co",
            source="google_places",
            source_id="p3",
            score_ai=20.0,
            phone="+12125553333",
            lead_status="new",
        )
        session.add_all([hot, warm, cold])
        await session.flush()

        # One reply on the hot lead.
        session.add(
            LeadActivity(
                lead_id=hot.id,
                user_id=owner_id,
                team_id=team_id,
                kind="email_replied",
            )
        )
        await session.commit()
        return sq.id


# ── build_report_stats ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_report_stats_counts(patched_session_factory):
    from leadgen.core.services.report_builder import build_report_stats

    owner_id = _register_direct()
    async with patched_session_factory() as session:
        session.add(_fake_user(owner_id))
        await session.commit()
    team_id = await _seed_team(patched_session_factory, owner_id)
    search_id = await _seed_search_with_leads(
        patched_session_factory, owner_id, team_id
    )

    async with patched_session_factory() as session:
        search = await session.get(SearchQuery, search_id)
        stats = await build_report_stats(session, search)

    assert stats["total_leads"] == 3
    assert stats["hot_leads"] == 1
    # Hot has contact_email, Warm has a website_meta email → 2.
    assert stats["leads_with_email"] == 2
    assert stats["leads_with_valid_email"] == 1
    assert stats["leads_with_phone"] == 2
    assert stats["replied"] == 1
    assert stats["avg_score"] == pytest.approx(56.0, abs=0.1)
    assert stats["insights"] == "Lots of stale websites."
    assert stats["niche"] == "roofers"
    assert stats["region"] == "New York"
    assert len(stats["top_leads"]) == 3
    # Ordered by score desc.
    assert stats["top_leads"][0]["name"] == "Hot Co"


@pytest.mark.asyncio
async def test_build_report_stats_empty_is_null_safe(patched_session_factory):
    from leadgen.core.services.report_builder import build_report_stats

    owner_id = _register_direct()
    async with patched_session_factory() as session:
        session.add(_fake_user(owner_id))
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
        await session.commit()
        search_id = sq.id

    async with patched_session_factory() as session:
        search = await session.get(SearchQuery, search_id)
        stats = await build_report_stats(session, search)

    assert stats["total_leads"] == 0
    assert stats["hot_leads"] == 0
    assert stats["leads_with_email"] == 0
    assert stats["replied"] == 0
    assert stats["avg_score"] is None
    assert stats["top_leads"] == []
    assert stats["insights"] is None


# ── Branding PATCH/GET ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_branding_owner_set_and_get(client, patched_session_factory):
    owner_id = _register(client)
    team_id = await _seed_team(patched_session_factory, owner_id)

    r = client.patch(
        f"/api/v1/teams/{team_id}/branding",
        json={
            "brand_name": "Acme Agency",
            "brand_color": "#10B981",
            "brand_logo": _TINY_PNG,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["brand_name"] == "Acme Agency"
    assert data["brand_color"] == "#10B981"
    assert data["brand_logo"] == _TINY_PNG

    r = client.get(f"/api/v1/teams/{team_id}/branding")
    assert r.status_code == 200
    assert r.json()["brand_name"] == "Acme Agency"

    # Null clears a field, absent key untouched.
    r = client.patch(
        f"/api/v1/teams/{team_id}/branding",
        json={"brand_logo": None},
    )
    assert r.status_code == 200
    assert r.json()["brand_logo"] is None
    assert r.json()["brand_name"] == "Acme Agency"


@pytest.mark.asyncio
async def test_branding_non_owner_forbidden(client, patched_session_factory):
    owner_id = _register(client, email="owner-b@example.test")
    team_id = await _seed_team(patched_session_factory, owner_id)

    # A plain member can read but not write.
    member_id = _register(client, email="member-b@example.test")
    async with patched_session_factory() as session:
        session.add(
            TeamMembership(team_id=team_id, user_id=member_id, role="member")
        )
        await session.commit()

    r = client.get(f"/api/v1/teams/{team_id}/branding")
    assert r.status_code == 200

    r = client.patch(
        f"/api/v1/teams/{team_id}/branding",
        json={"brand_name": "Nope"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_branding_validation(client, patched_session_factory):
    owner_id = _register(client, email="owner-v@example.test")
    team_id = await _seed_team(patched_session_factory, owner_id)

    # Bad colour.
    r = client.patch(
        f"/api/v1/teams/{team_id}/branding",
        json={"brand_color": "red"},
    )
    assert r.status_code == 400

    # Bad data-url.
    r = client.patch(
        f"/api/v1/teams/{team_id}/branding",
        json={"brand_logo": "https://example.test/logo.png"},
    )
    assert r.status_code == 400

    # Oversized logo (>200 KB decoded).
    import base64

    big = base64.b64encode(b"x" * (200 * 1024 + 10)).decode()
    r = client.patch(
        f"/api/v1/teams/{team_id}/branding",
        json={"brand_logo": f"data:image/png;base64,{big}"},
    )
    assert r.status_code == 413


# ── Report create / list / revoke ───────────────────────────────────────


@pytest.mark.asyncio
async def test_report_create_list_revoke(client, patched_session_factory):
    owner_id = _register(client, email="owner-r@example.test")
    team_id = await _seed_team(patched_session_factory, owner_id)
    search_id = await _seed_search_with_leads(
        patched_session_factory, owner_id, team_id
    )

    r = client.post(
        f"/api/v1/searches/{search_id}/report",
        json={"title": "Q2 prospects", "expires_in_days": 7},
    )
    assert r.status_code == 200, r.text
    created = r.json()
    token = created["token"]
    assert created["share_path"] == f"/report/{token}"
    assert created["expires_at"] is not None

    r = client.get("/api/v1/reports")
    assert r.status_code == 200
    items = r.json()["reports"]
    assert len(items) == 1
    assert items[0]["token"] == token
    assert items[0]["title"] == "Q2 prospects"
    assert items[0]["revoked"] is False

    report_id = items[0]["report_id"]
    r = client.delete(f"/api/v1/reports/{report_id}")
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r = client.get("/api/v1/reports")
    assert r.json()["reports"][0]["revoked"] is True


# ── Public JSON + PDF ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_public_report_json_and_pdf(client, patched_session_factory):
    owner_id = _register(client, email="owner-p@example.test")
    team_id = await _seed_team(patched_session_factory, owner_id)
    client.patch(
        f"/api/v1/teams/{team_id}/branding",
        json={"brand_name": "Acme", "brand_color": "#10B981"},
    )
    search_id = await _seed_search_with_leads(
        patched_session_factory, owner_id, team_id
    )
    token = client.post(
        f"/api/v1/searches/{search_id}/report", json={"title": "Public"}
    ).json()["token"]

    # JSON — no auth: use a fresh client without the session cookie.
    from leadgen.adapters.web_api import create_app

    anon = TestClient(create_app())
    r = anon.get(f"/api/v1/reports/public/{token}")
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["brand_name"] == "Acme"
    assert payload["title"] == "Public"
    assert payload["stats"]["total_leads"] == 3
    assert payload["stats"]["hot_leads"] == 1
    # No internal ids / emails leaked at the top level.
    assert "team_id" not in payload
    assert "created_by_user_id" not in payload

    # PDF — no auth.
    r = anon.get(f"/api/v1/reports/public/{token}/download.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_public_report_404_rules(client, patched_session_factory):
    from leadgen.adapters.web_api import create_app

    anon = TestClient(create_app())

    # Unknown token.
    r = anon.get("/api/v1/reports/public/does-not-exist")
    assert r.status_code == 404

    owner_id = _register(client, email="owner-x@example.test")
    team_id = await _seed_team(patched_session_factory, owner_id)
    search_id = await _seed_search_with_leads(
        patched_session_factory, owner_id, team_id
    )
    token = client.post(
        f"/api/v1/searches/{search_id}/report", json={}
    ).json()["token"]

    # Revoked → 404.
    async with patched_session_factory() as session:
        from sqlalchemy import select as _select

        report = (
            await session.execute(
                _select(ClientReport).where(ClientReport.token == token)
            )
        ).scalar_one()
        report.revoked = True
        await session.commit()
    r = anon.get(f"/api/v1/reports/public/{token}")
    assert r.status_code == 404

    # Expired → 404.
    token2 = client.post(
        f"/api/v1/searches/{search_id}/report", json={}
    ).json()["token"]
    async with patched_session_factory() as session:
        from sqlalchemy import select as _select

        report = (
            await session.execute(
                _select(ClientReport).where(ClientReport.token == token2)
            )
        ).scalar_one()
        report.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        await session.commit()
    r = anon.get(f"/api/v1/reports/public/{token2}")
    assert r.status_code == 404
    r = anon.get(f"/api/v1/reports/public/{token2}/download.pdf")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_public_report_no_cross_team_leak(client, patched_session_factory):
    """A report's public JSON must surface only its own search's stats,
    never another team's data."""
    owner_a = _register(client, email="owner-a1@example.test")
    team_a = await _seed_team(patched_session_factory, owner_a)
    search_a = await _seed_search_with_leads(
        patched_session_factory, owner_a, team_a
    )

    # A second team with its own (larger) search.
    owner_b = _register(client, email="owner-b1@example.test")
    team_b = await _seed_team(patched_session_factory, owner_b)
    async with patched_session_factory() as session:
        sq = SearchQuery(
            id=uuid.uuid4(),
            user_id=owner_b,
            team_id=team_b,
            niche="other",
            region="LA",
            status="done",
            source="web",
        )
        session.add(sq)
        await session.flush()
        for i in range(10):
            session.add(
                Lead(
                    id=uuid.uuid4(),
                    query_id=sq.id,
                    name=f"B{i}",
                    source="google_places",
                    source_id=f"b{i}",
                    score_ai=90.0,
                    lead_status="new",
                )
            )
        await session.commit()

    # owner_a is logged in last via _register; re-login as owner_a so the
    # report POST is authorised by the search's owner.
    client.post(
        "/api/v1/auth/login",
        json={"email": "owner-a1@example.test", "password": "correcthorse123"},
    )
    token = client.post(
        f"/api/v1/searches/{search_a}/report", json={}
    ).json()["token"]

    from leadgen.adapters.web_api import create_app

    anon = TestClient(create_app())
    payload = anon.get(f"/api/v1/reports/public/{token}").json()
    # Team A's search had 3 leads — never team B's 10.
    assert payload["stats"]["total_leads"] == 3
    names = {ld["name"] for ld in payload["stats"]["top_leads"]}
    assert not any(n.startswith("B") for n in names)


# ── Small helpers for the service-level tests ───────────────────────────


def _register_direct() -> int:
    """A stable fake user id for the service-only tests (no HTTP)."""
    return 4242


def _fake_user(user_id: int):
    from leadgen.db.models import User

    return User(
        id=user_id,
        email=f"svc-{user_id}@example.test",
        password_hash="x",
    )
