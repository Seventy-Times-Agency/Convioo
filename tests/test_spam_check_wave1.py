"""Wave-1 spam pre-flight: heuristic scorer + the composer endpoint."""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.core.services.spam_check import check_spam
from leadgen.db import session as db_session_mod
from leadgen.db.models import Base
from leadgen.utils import rate_limit as rate_limit_mod


def test_clean_email_is_ok():
    v = check_spam(
        "Вопрос по клиентам из Санни-Айлс",
        (
            "Добрый день, Ирина!\n\nЗаметил, что у вашего салона 243 отзыва "
            "на 4.8, но сайта нет — новые клиенты вас просто не находят. "
            "Мы помогаем салонам в Майами настраивать поток записей.\n\n"
            "Удобно созвониться на этой неделе на 15 минут?\n\nДенис"
        ),
    )
    assert v.verdict == "ok", v.issues


def test_spammy_email_flags():
    v = check_spam(
        "FREE MONEY — ACT NOW!!!",
        (
            "CLICK HERE to get 100% FREE cash bonus!!! "
            "Limited time GUARANTEED offer! Buy now: https://bit.ly/x "
            "http://a.example http://b.example"
        ),
    )
    assert v.verdict == "spammy"
    joined = " ".join(v.issues)
    assert "trigger_words" in joined
    assert "shortener" in joined


def test_risky_middle_ground():
    v = check_spam(
        "Скидка 90% только сегодня!",
        (
            "Здравствуйте! Только сегодня скидка на аудит — успей записаться! "
            "Подробности на сайте."
        ),
    )
    assert v.verdict in ("risky", "spammy")
    assert v.score >= 3


# ── endpoint ───────────────────────────────────────────────────────────


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
async def test_spam_check_endpoint(patched_session_factory):
    from leadgen.adapters.web_api import create_app

    client = TestClient(create_app())
    rate_limit_mod.register_limiter._events.clear()
    r = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Spam",
            "last_name": "Check",
            "email": "spam-check@example.test",
            "password": "correcthorse123",
        },
    )
    assert r.status_code == 200

    # Unauthenticated → 401.
    anon = TestClient(create_app())
    r = anon.post(
        "/api/v1/deliverability/spam-check",
        json={"subject": "x", "body": "y"},
    )
    assert r.status_code == 401

    r = client.post(
        "/api/v1/deliverability/spam-check",
        json={
            "subject": "FREE MONEY — ACT NOW!!!",
            "body": "CLICK HERE!!! 100% free guaranteed https://bit.ly/x",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["verdict"] in ("risky", "spammy")
    assert data["score"] > 0
    assert data["issues"]
