"""Per-search source override (T6).

Black-box test of the SearchCreate normalisation: bad / unknown
source names are dropped, the canonical empty list is normalised
to NULL, and good values round-trip into the SearchQuery row.
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

from leadgen.adapters.web_api import auth as auth_mod
from leadgen.db import session as db_session_mod
from leadgen.db.models import Base, SearchQuery, User
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


def _client_for(user: User, *, no_redis: bool = True) -> TestClient:
    from leadgen.adapters.web_api.app import create_app

    async def _fake() -> User:
        return user

    app = create_app()
    app.dependency_overrides[auth_mod.get_current_user] = _fake
    return TestClient(app)


@pytest.mark.asyncio
async def test_enabled_sources_persisted_on_search_query(
    patched_session_factory, monkeypatch
) -> None:
    user = User(
        id=1,
        email="u@example.com",
        email_verified_at=__import__(
            "datetime"
        ).datetime(2026, 1, 1, tzinfo=__import__("datetime").timezone.utc),
        onboarded_at=__import__(
            "datetime"
        ).datetime(2026, 1, 1, tzinfo=__import__("datetime").timezone.utc),
    )
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    # Stub out the inline runner so creating a search doesn't try to
    # call Anthropic / Google.
    async def _noop_inline(query_id, profile=None):
        return None

    import leadgen.adapters.web_api.app as app_mod

    monkeypatch.setattr(app_mod, "_run_web_search_inline", _noop_inline)

    client = _client_for(user)
    resp = client.post(
        "/api/v1/searches",
        json={
            "user_id": 1,
            "niche": "roofing",
            "region": "New York",
            "scope": "city",
            # Mix valid + invalid + duplicate values; expect the
            # server to filter and de-dupe before persisting.
            "enabled_sources": ["google", "yelp", "GOOGLE", "junk"],
        },
    )
    assert resp.status_code == 200, resp.text
    query_id = uuid.UUID(resp.json()["id"])

    async with patched_session_factory() as s:
        row = await s.get(SearchQuery, query_id)
        assert row is not None
        # Sorted, lowercased, de-duplicated, junk dropped.
        assert row.enabled_sources == ["google", "yelp"]


@pytest.mark.asyncio
async def test_enabled_sources_empty_list_normalises_to_null(
    patched_session_factory, monkeypatch
) -> None:
    """An empty subset means the user wants no sources at all — silly,
    so we treat it as 'no override' (NULL) and let env defaults run."""
    import datetime as _dt

    user = User(
        id=2,
        email="u2@example.com",
        email_verified_at=_dt.datetime(
            2026, 1, 1, tzinfo=_dt.timezone.utc
        ),
        onboarded_at=_dt.datetime(
            2026, 1, 1, tzinfo=_dt.timezone.utc
        ),
    )
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    async def _noop(query_id, profile=None):
        return None

    import leadgen.adapters.web_api.app as app_mod

    monkeypatch.setattr(app_mod, "_run_web_search_inline", _noop)

    client = _client_for(user)
    resp = client.post(
        "/api/v1/searches",
        json={
            "user_id": 2,
            "niche": "roofing",
            "region": "New York",
            "scope": "city",
            "enabled_sources": ["junk_only"],
        },
    )
    assert resp.status_code == 200, resp.text
    query_id = uuid.UUID(resp.json()["id"])

    async with patched_session_factory() as s:
        row = await s.get(SearchQuery, query_id)
        assert row is not None
        assert row.enabled_sources is None


@pytest.mark.asyncio
async def test_enabled_sources_omitted_means_null(
    patched_session_factory, monkeypatch
) -> None:
    import datetime as _dt

    user = User(
        id=3,
        email="u3@example.com",
        email_verified_at=_dt.datetime(
            2026, 1, 1, tzinfo=_dt.timezone.utc
        ),
        onboarded_at=_dt.datetime(
            2026, 1, 1, tzinfo=_dt.timezone.utc
        ),
    )
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    async def _noop(query_id, profile=None):
        return None

    import leadgen.adapters.web_api.app as app_mod

    monkeypatch.setattr(app_mod, "_run_web_search_inline", _noop)

    client = _client_for(user)
    resp = client.post(
        "/api/v1/searches",
        json={
            "user_id": 3,
            "niche": "roofing",
            "region": "New York",
            "scope": "city",
        },
    )
    assert resp.status_code == 200, resp.text
    query_id = uuid.UUID(resp.json()["id"])

    async with patched_session_factory() as s:
        row = await s.get(SearchQuery, query_id)
        assert row is not None
        assert row.enabled_sources is None
