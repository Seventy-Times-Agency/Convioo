"""Language-consistency feature tests.

Pins the contract that user-visible AI/system text follows the user's
UI language (``users.language_code``):

* ``language_directive`` is always forceful — non-empty for every
  locale, with None / unknown treated as ru (the frontend default).
* Cold-email drafting accepts a per-email language override and bakes
  an explicit "write the email in <language>" instruction into the
  prompt; the heuristic fallback is localised too.
* The daily digest renders per-user language variants with distinct
  subjects.
* ``PATCH /api/v1/users/me`` persists ``language_code`` and rejects
  unsupported codes.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.adapters.web_api import auth as auth_mod
from leadgen.analysis.ai_analyzer import AIAnalyzer
from leadgen.analysis.prompts.system import language_directive
from leadgen.core.services.digest import (
    DigestSummary,
    digest_subject,
    render_digest_email,
)
from leadgen.db import session as db_session_mod
from leadgen.db.models import Base, User

# ── language_directive ─────────────────────────────────────────────


@pytest.mark.parametrize(
    ("code", "expected_language"),
    [
        ("ru", "Russian"),
        ("uk", "Ukrainian"),
        ("en", "English"),
    ],
)
def test_language_directive_forceful_for_all_locales(
    code: str, expected_language: str
) -> None:
    directive = language_directive({"language_code": code})
    assert directive
    assert "CRITICAL" in directive
    assert expected_language in directive


def test_language_directive_defaults_to_russian() -> None:
    # None profile, missing key and unknown codes all pin Russian —
    # mirrors the frontend default locale.
    for profile in (None, {}, {"language_code": None}, {"language_code": "de"}):
        directive = language_directive(profile)
        assert directive
        assert "Russian" in directive


# ── cold-email language override ───────────────────────────────────


class _FakeMessages:
    def __init__(self, reply_text: str) -> None:
        self.calls: list[dict[str, Any]] = []
        self._reply_text = reply_text

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(text=self._reply_text)],
            usage=None,
        )


def _system_text(call: dict[str, Any]) -> str:
    system = call["system"]
    if isinstance(system, list):
        return "".join(block.get("text", "") for block in system)
    return system or ""


@pytest.mark.anyio
async def test_email_prompt_carries_language_override() -> None:
    analyzer = AIAnalyzer(api_key="")
    fake = _FakeMessages('{"subject": "Hello", "body": "Hi there"}')
    analyzer.client = SimpleNamespace(messages=fake)

    result = await analyzer.generate_cold_email(
        {"name": "Acme Roofing"},
        user_profile={"language_code": "ru", "profession": "SEO"},
        tone="professional",
        language="en",
    )

    assert result["subject"] == "Hello"
    assert len(fake.calls) == 1
    system = _system_text(fake.calls[0])
    # The explicit override (en) must win over the UI language (ru).
    assert "write the email (subject and" in system.lower()
    assert "English" in system
    user_msg = fake.calls[0]["messages"][0]["content"]
    assert "English" in user_msg


@pytest.mark.anyio
async def test_email_prompt_falls_back_to_ui_language() -> None:
    analyzer = AIAnalyzer(api_key="")
    fake = _FakeMessages('{"subject": "Тема", "body": "Текст"}')
    analyzer.client = SimpleNamespace(messages=fake)

    await analyzer.generate_cold_email(
        {"name": "Acme"},
        user_profile={"language_code": "uk"},
    )

    system = _system_text(fake.calls[0])
    assert "Ukrainian" in system


@pytest.mark.anyio
async def test_heuristic_email_is_localised() -> None:
    analyzer = AIAnalyzer(api_key="")  # no client → heuristic path
    lead = {"name": "Acme"}

    en = await analyzer.generate_cold_email(lead, language="en")
    uk = await analyzer.generate_cold_email(lead, language="uk")
    ru = await analyzer.generate_cold_email(lead, language="ru")

    assert en["subject"] == "Acme — a quick observation"
    assert uk["subject"] == "Acme — коротке спостереження"
    assert ru["subject"] == "Acme — короткое наблюдение"


# ── daily digest localisation ──────────────────────────────────────


def test_digest_subject_varies_by_language() -> None:
    ru = digest_subject("ru")
    uk = digest_subject("uk")
    en = digest_subject("en")
    assert len({ru, uk, en}) == 3
    assert digest_subject(None) == ru
    assert en == "Convioo — your daily summary"


def test_digest_body_renders_language_variants() -> None:
    summary = DigestSummary(new_leads=3, hot_leads=1, replies=2)

    html_en, text_en = render_digest_email(
        name="Ann", summary=summary, app_url="https://x.test", lang="en"
    )
    html_uk, text_uk = render_digest_email(
        name="Ann", summary=summary, app_url="https://x.test", lang="uk"
    )
    html_ru, text_ru = render_digest_email(
        name="Ann", summary=summary, app_url="https://x.test", lang="ru"
    )

    assert "New leads: 3" in text_en
    assert "Нових лідів: 3" in text_uk
    assert "Новых лидов: 3" in text_ru
    assert "Open CRM" in html_en
    assert "Відкрити CRM" in html_uk
    assert "Открыть CRM" in html_ru


# ── PATCH /api/v1/users/me persists language_code ──────────────────


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
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


def _client_for(user: User) -> TestClient:
    from leadgen.adapters.web_api.app import create_app

    async def _fake() -> User:
        return user

    app = create_app()
    app.dependency_overrides[auth_mod.get_current_user] = _fake
    return TestClient(app)


@pytest.mark.asyncio
async def test_patch_users_me_persists_language_code(patched_session_factory):
    user = User(id=1, email="u@example.com", first_name="U")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    client = _client_for(user)
    r = client.patch("/api/v1/users/me", json={"language_code": "uk"})
    assert r.status_code == 200, r.text
    assert r.json()["language_code"] == "uk"

    async with patched_session_factory() as s:
        row = await s.get(User, 1)
        assert row.language_code == "uk"


@pytest.mark.asyncio
async def test_patch_users_me_rejects_unknown_language(
    patched_session_factory,
):
    user = User(id=2, email="u2@example.com", first_name="U")
    async with patched_session_factory() as s:
        s.add(user)
        await s.commit()

    client = _client_for(user)
    r = client.patch("/api/v1/users/me", json={"language_code": "de"})
    assert r.status_code == 400

    async with patched_session_factory() as s:
        row = await s.get(User, 2)
        assert row.language_code is None
