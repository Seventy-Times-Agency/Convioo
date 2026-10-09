"""Воронка добычи: бесплатные проверки до трат, дубли до лимита,
глубокий анализ и ЛПР только для прошедших, выдача готового при сбое."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from leadgen.collectors.google_places import REVIEWS_INLINE_KEY, RawLead
from leadgen.db.models import Lead, SearchQuery, TeamSeenLead
from leadgen.pipeline import enrichment as enrich_mod
from leadgen.pipeline import search as search_mod
from leadgen.pipeline.search import FUNNELS

pytest_plugins = ["tests.test_team_roles_wave1"]


def _raw(i: int, *, phone: str | None = None, website: str | None = None, name: str | None = None) -> RawLead:
    return RawLead(
        source="google_places",
        source_id=f"place-{i}",
        name=name or f"Dental {i}",
        phone=phone,
        website=website,
        address=f"{i} Main St, Kyiv",
        rating=4.5,
        reviews_count=10 + i,
        raw={"demo": {"score": 70}},
    )


@pytest.fixture
def demo_on(monkeypatch):
    from leadgen.config import get_settings

    monkeypatch.setenv("DEMO_MODE", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _query(maker, crew, **kw) -> uuid.UUID:
    async with maker() as session:
        q = SearchQuery(
            id=uuid.uuid4(),
            user_id=crew["ids"]["owner"],
            team_id=crew["team_id"],
            niche="dentists",
            region="Kyiv",
            source="web",
            status="pending",
            **kw,
        )
        session.add(q)
        await session.commit()
        return q.id


@pytest.mark.asyncio
async def test_duplicates_and_no_contact_dropped_before_the_limit(
    crew, patched_session_factory, demo_on, monkeypatch
):
    # 10 уже были у команды (по телефону), 5 без телефона и сайта,
    # 15 свежих и ещё одна копия свежей под другим id (тот же телефон).
    found = (
        [_raw(i, phone=f"+38050000{i:04d}") for i in range(10)]
        + [_raw(100 + i) for i in range(5)]
        + [_raw(200 + i, phone=f"+38067000{i:04d}") for i in range(15)]
        + [_raw(999, phone="+380670000000")]
    )
    import leadgen.collectors.mock as mock_mod

    monkeypatch.setattr(mock_mod, "demo_leads", lambda niche, region, limit: list(found))
    async with patched_session_factory() as session:
        for i in range(10):
            session.add(
                TeamSeenLead(
                    team_id=crew["team_id"],
                    source="osm",  # найден другим источником — всё равно дубль
                    source_id=f"osm-{i}",
                    phone_e164=f"+38050000{i:04d}",
                    first_user_id=crew["ids"]["owner"],
                )
            )
        await session.commit()

    qid = await _query(patched_session_factory, crew, max_results=12)
    await search_mod.run_search_with_sinks(qid, None, None)

    async with patched_session_factory() as session:
        q = await session.get(SearchQuery, qid)
        n = (await session.execute(select(func.count(Lead.id)).where(Lead.query_id == qid))).scalar_one()
    funnel = FUNNELS.pop(qid)
    # Раньше лимит резал до дублей: из 12 заказанных пришло бы 2.
    assert q.status == "done"
    assert n == 12 and q.leads_count == 12
    assert funnel["duplicates"] == 10
    assert funnel["no_contact"] == 5
    assert funnel["over_limit"] == 3  # 15 свежих − 12; копия по телефону не считается
    assert funnel["delivered"] == 12


@pytest.mark.asyncio
async def test_enrichment_uses_inline_reviews_and_gates_decision_makers(
    crew, patched_session_factory, monkeypatch
):
    from leadgen.analysis import LeadAnalysis
    from leadgen.collectors.website import WebsiteInfo

    qid = await _query(patched_session_factory, crew, max_results=10)
    specs = [
        # (сайт, оценка, исключён)
        ("https://good-dental.ua", 80, False),  # ЛПР ищем
        ("https://weak-dental.ua", 30, False),  # слабый — не ищем
        ("https://instagram.com/x", 90, False),  # не свой домен — не ищем
        ("https://chain-dental.ua", 85, True),  # «кого не нужно» — удаляется
    ]
    leads: list[Lead] = []
    async with patched_session_factory() as session:
        for i, (site, _s, _e) in enumerate(specs):
            lead = Lead(
                query_id=qid,
                name=f"Clinic {i}",
                website=site,
                phone=f"+3805000{i}",
                source="google_places",
                source_id=f"p{i}",
                raw={REVIEWS_INLINE_KEY: True, "reviews": [{"rating": 5, "text": {"text": "great"}}]},
            )
            session.add(lead)
            leads.append(lead)
        await session.commit()

    class FakeSite:
        async def fetch(self, url):
            return WebsiteInfo(url=url or "", ok=False)

    seen_contexts: list[dict] = []

    class FakeAnalyzer:
        async def analyze_batch(self, contexts, niche, region, user_profile=None, progress_callback=None):
            seen_contexts.extend(contexts)
            by_site = {s: (score, ex) for s, score, ex in specs}
            return [
                LeadAnalysis(score=by_site[c["website"]][0], excluded=by_site[c["website"]][1])
                for c in contexts
            ]

    class NoDetails:
        async def get_details(self, place_id):
            raise AssertionError("Place Details must not be called when reviews came with search")

    dm_calls: list[str] = []

    async def fake_dm(inp):
        dm_calls.append(inp.website)
        return {"name": "Owner", "source": "test"}

    async def no_email(domain):
        return None

    monkeypatch.setattr(enrich_mod, "WebsiteCollector", FakeSite)
    monkeypatch.setattr(enrich_mod, "AIAnalyzer", FakeAnalyzer)
    monkeypatch.setattr(enrich_mod, "find_decision_maker", fake_dm)
    monkeypatch.setattr(enrich_mod, "find_email", no_email)

    out = await enrich_mod.enrich_leads(leads, NoDetails(), "dentists", "Kyiv", find_decision_makers=True)

    assert dm_calls == ["https://good-dental.ua"]
    assert all(c["reviews"] for c in seen_contexts)
    assert len(out) == 3
    assert sum(1 for d in out if d["decision_maker"]) == 1
    async with patched_session_factory() as session:
        names = sorted(
            (await session.execute(select(Lead.website).where(Lead.query_id == qid))).scalars().all()
        )
    assert "https://chain-dental.ua" not in names


def test_decision_maker_tokens_charged_only_when_found():
    from leadgen.core.services.account import tokens

    assert tokens.quote(10, find_decision_makers=True).total == 20  # резерв — по максимуму
    assert tokens.quote(10, find_decision_makers=True, decision_makers=3).total == 13
    assert tokens.quote(10, find_decision_makers=False, decision_makers=3).total == 10


@pytest.mark.asyncio
async def test_crash_mid_enrichment_delivers_ready_leads(
    crew, patched_session_factory, demo_on, monkeypatch
):
    import leadgen.collectors.mock as mock_mod
    from leadgen.adapters.web_api.routes import _helpers as helpers_mod
    from leadgen.core.services.account import tokens

    found = [_raw(300 + i, phone=f"+38063000{i:04d}") for i in range(15)]
    monkeypatch.setattr(mock_mod, "demo_leads", lambda niche, region, limit: list(found))

    async def half_then_crash(leads, *a, **kw):
        async with patched_session_factory() as session:
            for lead in leads[:10]:
                (await session.get(Lead, lead.id)).enriched = True
            await session.commit()
        raise RuntimeError("anthropic overloaded")

    monkeypatch.setattr(search_mod, "enrich_leads", half_then_crash)

    async with patched_session_factory() as session:
        await tokens.grant(session, crew["team_id"], 100, reason="test")
        await session.commit()
    qid = await _query(patched_session_factory, crew, max_results=15)
    async with patched_session_factory() as session:
        await tokens.hold(session, crew["team_id"], qid, 15, user_id=crew["ids"]["owner"])
        await session.commit()

    await search_mod.run_search_with_sinks(qid, None, None)
    await helpers_mod.finish_search_run(qid)

    async with patched_session_factory() as session:
        q = await session.get(SearchQuery, qid)
        balance = await tokens.balance(session, crew["team_id"])
    assert q.status == "done"
    assert q.leads_count == 15
    assert q.error.startswith("partial")
    # Списаны только 10 оценённых, остальные 5 — бесплатно.
    assert balance == 90
    assert q.economics["delivered"] == 15
