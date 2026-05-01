"""ICP refinement: feedback storage + prompt block rendering."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from leadgen.core.services import icp_service
from leadgen.db.models import Base, Lead, SearchQuery, User


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _seed_user_with_lead(
    session: AsyncSession, *, user_id: int = 1, lead_name: str = "Acme"
) -> Lead:
    existing = await session.get(User, user_id)
    if existing is None:
        session.add(
            User(
                id=user_id,
                first_name="Test",
                last_name="User",
                queries_used=0,
                queries_limit=1000,
            )
        )
    query = SearchQuery(
        id=uuid.uuid4(),
        user_id=user_id,
        niche="roofing",
        region="NYC",
        source="web",
    )
    session.add(query)
    lead = Lead(
        id=uuid.uuid4(),
        query_id=query.id,
        name=lead_name,
        category="roofing",
        address="Brooklyn, NY",
        source="google",
        source_id=str(uuid.uuid4()),
    )
    session.add(lead)
    await session.commit()
    return lead


class TestUpsertVerdict:
    @pytest.mark.asyncio
    async def test_creates_new_row(self, session: AsyncSession) -> None:
        lead = await _seed_user_with_lead(session)
        row = await icp_service.upsert_verdict(
            session, user_id=1, lead_id=lead.id, verdict="fit", reason=None
        )
        assert row.verdict == "fit"
        assert row.reason is None

    @pytest.mark.asyncio
    async def test_updates_existing_row(self, session: AsyncSession) -> None:
        lead = await _seed_user_with_lead(session)
        await icp_service.upsert_verdict(
            session,
            user_id=1,
            lead_id=lead.id,
            verdict="fit",
            reason="liked",
        )
        row = await icp_service.upsert_verdict(
            session,
            user_id=1,
            lead_id=lead.id,
            verdict="not_fit",
            reason="changed mind",
        )
        assert row.verdict == "not_fit"
        assert row.reason == "changed mind"

    @pytest.mark.asyncio
    async def test_rejects_invalid_verdict(
        self, session: AsyncSession
    ) -> None:
        lead = await _seed_user_with_lead(session)
        with pytest.raises(ValueError):
            await icp_service.upsert_verdict(
                session,
                user_id=1,
                lead_id=lead.id,
                verdict="maybe",
                reason=None,
            )


class TestSnapshot:
    @pytest.mark.asyncio
    async def test_empty_snapshot(self, session: AsyncSession) -> None:
        await _seed_user_with_lead(session)
        snap = await icp_service.snapshot_for_user(session, user_id=1)
        assert snap.fit_count == 0
        assert snap.not_fit_count == 0
        assert snap.recent_examples == []

    @pytest.mark.asyncio
    async def test_counts_and_examples(self, session: AsyncSession) -> None:
        lead_a = await _seed_user_with_lead(session, lead_name="Alpha")
        lead_b = await _seed_user_with_lead(session, lead_name="Beta")
        await icp_service.upsert_verdict(
            session,
            user_id=1,
            lead_id=lead_a.id,
            verdict="fit",
            reason=None,
        )
        await icp_service.upsert_verdict(
            session,
            user_id=1,
            lead_id=lead_b.id,
            verdict="not_fit",
            reason="too big",
        )
        await session.commit()
        snap = await icp_service.snapshot_for_user(session, user_id=1)
        assert snap.fit_count == 1
        assert snap.not_fit_count == 1
        names = {e.lead_name for e in snap.recent_examples}
        assert names == {"Alpha", "Beta"}


class TestRender:
    def test_empty_snapshot_returns_empty_string(self) -> None:
        snap = icp_service.ICPSnapshot(
            fit_count=0, not_fit_count=0, recent_examples=[]
        )
        assert icp_service.render_icp_block(snap) == ""

    def test_block_includes_examples_and_reasons(self) -> None:
        snap = icp_service.ICPSnapshot(
            fit_count=1,
            not_fit_count=1,
            recent_examples=[
                icp_service.FeedbackExample(
                    verdict="fit",
                    lead_name="Acme Plumbing",
                    lead_summary=None,
                    lead_category="plumber",
                    lead_address="Brooklyn, NY",
                    reason="active blog",
                ),
                icp_service.FeedbackExample(
                    verdict="not_fit",
                    lead_name="MegaCorp",
                    lead_summary=None,
                    lead_category="enterprise",
                    lead_address="Manhattan, NY",
                    reason="too big",
                ),
            ],
        )
        rendered = icp_service.render_icp_block(snap)
        assert "Acme Plumbing" in rendered
        assert "active blog" in rendered
        assert "MegaCorp" in rendered
        assert "too big" in rendered
        assert "Понравились" in rendered
        assert "Не понравились" in rendered
