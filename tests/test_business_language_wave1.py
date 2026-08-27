"""Wave-1 business-language engine + the База filter."""

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

from leadgen.core.services.business_language import (
    classify_business_language,
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

# ── engine units ───────────────────────────────────────────────────────


def test_keyword_is_exact():
    v = classify_business_language(
        website_text="Наш салон — говорим по-русски, welcome!"
    )
    assert (v.language, v.confidence) == ("ru", "exact")

    v = classify_business_language(
        website_text="Ласкаво просимо! Розмовляємо українською щодня."
    )
    assert (v.language, v.confidence) == ("uk", "exact")


def test_specific_characters():
    # Ukrainian-only letters (і, ї, є) → uk.
    v = classify_business_language(
        reviews_texts=["Дуже смачні вареники, привітні працівники, ціни чудові"]
    )
    assert v.language == "uk"
    assert v.confidence in ("exact", "likely")

    # Russian-only letters (ы, э, ё) → ru.
    v = classify_business_language(
        reviews_texts=["Очень вкусные пельмени, цены отличные, всё быстро"]
    )
    assert v.language == "ru"


def test_generic_cyrillic_defaults_ru_likely():
    v = classify_business_language(
        website_text="Салон красоти та манікюр для всіх"[:0]
        + "Салон красоты маникюр педикюр стрижка окрашивание"
    )
    assert v.language == "ru"
    assert v.confidence == "likely"


def test_translit_names_and_socials():
    v = classify_business_language(owner_names=["Iryna Kovalenko"])
    assert (v.language, v.confidence) == ("uk", "likely")

    v = classify_business_language(owner_names=["Sergey Ivanov"])
    assert (v.language, v.confidence) == ("ru", "likely")

    v = classify_business_language(
        social_links={"vk": "https://vk.com/somebiz"}
    )
    assert (v.language, v.confidence) == ("ru", "likely")


def test_no_signal_is_none():
    v = classify_business_language(
        website_text="Family bakery serving fresh bread since 1995.",
        owner_names=["John Smith"],
    )
    assert (v.language, v.confidence) == (None, None)


# ── API filter ─────────────────────────────────────────────────────────


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


@pytest.mark.asyncio
async def test_base_filter_by_language(patched_session_factory):
    from leadgen.adapters.web_api import create_app

    rate_limit_mod.register_limiter._events.clear()
    client = TestClient(create_app())
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Lang",
            "last_name": "Mgr",
            "email": "lang-mgr@example.test",
            "password": "correcthorse123",
        },
    )
    user_id = r.json()["user_id"]
    team_id = uuid.uuid4()
    async with patched_session_factory() as session:
        session.add(Team(id=team_id, name="Dept"))
        session.add(
            TeamMembership(team_id=team_id, user_id=user_id, role="manager")
        )
        sq = SearchQuery(
            id=uuid.uuid4(),
            user_id=user_id,
            team_id=team_id,
            niche="x",
            region="y",
            status="done",
            source="web",
        )
        session.add(sq)
        await session.flush()
        for i, lang in enumerate(["ru", "uk", None]):
            session.add(
                Lead(
                    id=uuid.uuid4(),
                    query_id=sq.id,
                    name=f"L{i}-{lang}",
                    source="google_places",
                    source_id=f"bl-{i}",
                    lead_status="new",
                    business_language=lang,
                    business_language_confidence=(
                        "likely" if lang else None
                    ),
                )
            )
        await session.commit()

    base = {"team_id": str(team_id)}
    r = client.get("/api/v1/leads", params=base)
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 3

    r = client.get(
        "/api/v1/leads", params={**base, "business_language": "ru"}
    )
    names = [lead["name"] for lead in r.json()["leads"]]
    assert names == ["L0-ru"]
    assert r.json()["leads"][0]["business_language"] == "ru"

    # Пресет RU+UA — обе метки разом.
    r = client.get(
        "/api/v1/leads", params={**base, "business_language": "ru+uk"}
    )
    assert r.json()["total"] == 2
