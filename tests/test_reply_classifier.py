"""AI reply classification: the classifier service, its graceful fallbacks,
and the routing it drives inside the reply tracker."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import leadgen.core.services.email_reply_tracker as tracker
from leadgen.config import get_settings
from leadgen.core.services import reply_classifier
from leadgen.core.services.reply_classifier import (
    REPLY_CATEGORIES,
    classify_reply,
    routing_for,
)
from leadgen.core.services.suppression import is_suppressed
from leadgen.db.models import Base, Lead, LeadActivity, SearchQuery, User

# --------------------------------------------------------------------------
# Pure helpers: normalization + routing table
# --------------------------------------------------------------------------


def test_coerce_clamps_and_defaults() -> None:
    out = reply_classifier._coerce(
        {
            "category": "NONSENSE",
            "sentiment": "furious",
            "confidence": 5,
            "summary": "x" * 500,
            "suggested_reply": "  hi  ",
        }
    )
    assert out["category"] == "other"
    assert out["sentiment"] == "neutral"
    assert out["confidence"] == 1.0
    assert len(out["summary"]) <= 200
    assert out["suggested_reply"] == "hi"


def test_coerce_accepts_valid() -> None:
    out = reply_classifier._coerce(
        {
            "category": "interested",
            "sentiment": "positive",
            "confidence": 0.85,
            "summary": "Wants a demo",
            "suggested_reply": "Great, how's Tuesday?",
        }
    )
    assert out["category"] == "interested"
    assert out["sentiment"] == "positive"
    assert out["confidence"] == 0.85


def test_routing_covers_every_category() -> None:
    for cat in REPLY_CATEGORIES:
        route = routing_for(cat)
        assert set(route) == {"suppress", "lead_status", "not_a_reply"}
    assert routing_for("unsubscribe")["suppress"] is True
    assert routing_for("auto_reply")["not_a_reply"] is True
    assert routing_for("not_interested")["lead_status"] == "lost"
    # Unknown category falls back to the "other" policy.
    assert routing_for("???") == reply_classifier.CATEGORY_ROUTING["other"]


# --------------------------------------------------------------------------
# classify_reply graceful degradation
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classify_empty_body_is_neutral(monkeypatch) -> None:
    s = get_settings()
    monkeypatch.setattr(s, "anthropic_api_key", "sk-test", raising=False)
    out = await classify_reply("   ")
    assert out["category"] == "other"
    assert out["confidence"] == 0.0


@pytest.mark.asyncio
async def test_classify_no_api_key_is_neutral(monkeypatch) -> None:
    s = get_settings()
    monkeypatch.setattr(s, "anthropic_api_key", "", raising=False)
    out = await classify_reply("I'd love a demo next week!")
    assert out["category"] == "other"


@pytest.mark.asyncio
async def test_classify_parses_claude_json(monkeypatch) -> None:
    s = get_settings()
    monkeypatch.setattr(s, "anthropic_api_key", "sk-test", raising=False)

    class _Block:
        text = (
            '{"category":"meeting_request","sentiment":"positive",'
            '"confidence":0.9,"summary":"Wants a call","suggested_reply":"Sure!"}'
        )

    class _Msg:
        content = [_Block()]

    class _Messages:
        async def create(self, **kw):
            return _Msg()

    class _FakeClient:
        def __init__(self, *a, **kw):
            self.messages = _Messages()

    monkeypatch.setattr(
        reply_classifier.anthropic, "AsyncAnthropic", _FakeClient
    )
    out = await classify_reply("Can we hop on a call?", subject="Re: hi")
    assert out["category"] == "meeting_request"
    assert out["sentiment"] == "positive"
    assert out["suggested_reply"] == "Sure!"


@pytest.mark.asyncio
async def test_classify_api_error_is_neutral(monkeypatch) -> None:
    s = get_settings()
    monkeypatch.setattr(s, "anthropic_api_key", "sk-test", raising=False)

    class _Boom:
        def __init__(self, *a, **kw):
            raise RuntimeError("network down")

    monkeypatch.setattr(reply_classifier.anthropic, "AsyncAnthropic", _Boom)
    out = await classify_reply("hello")
    assert out["category"] == "other"


# --------------------------------------------------------------------------
# Routing inside scan_replies_for_user
# --------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded(db_engine):
    maker = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    async with maker() as session:
        user = User(
            id=1,
            email="agent@example.com",
            password_hash="x",
            email_reply_tracking_enabled=True,
            email_reply_last_checked_at=None,
        )
        session.add(user)
        await session.flush()
        query = SearchQuery(
            id=uuid.uuid4(),
            user_id=user.id,
            niche="roofers",
            region="NYC",
            status="done",
        )
        session.add(query)
        await session.flush()
        lead = Lead(
            id=uuid.uuid4(),
            query_id=query.id,
            source="google",
            source_id=str(uuid.uuid4()),
            name="Acme Roofing",
            lead_status="contacted",
        )
        session.add(lead)
        await session.flush()
        outbound = LeadActivity(
            lead_id=lead.id,
            user_id=user.id,
            kind="email_sent",
            payload={"message_id": "<sent-123@mail>"},
        )
        session.add(outbound)
        await session.commit()
        return SimpleNamespace(
            maker=maker, user_id=user.id, lead_id=lead.id
        )


def _patch_gmail(monkeypatch, *, from_email: str, body: str) -> None:
    async def _fake_list(access_token, *, after_epoch):
        return [{"id": "reply-1"}]

    async def _fake_headers(access_token, message_id):
        return {
            "in-reply-to": "<sent-123@mail>",
            "from": from_email,
            "_thread_id": "t1",
        }

    async def _fake_get_message(access_token, msg_id):
        return {
            "from_email": from_email,
            "subject": "Re: hi",
            "body_text": body,
            "snippet": body[:80],
        }

    monkeypatch.setattr(tracker, "_list_recent_messages", _fake_list)
    monkeypatch.setattr(tracker, "_fetch_message_headers", _fake_headers)
    monkeypatch.setattr(tracker.gmail, "get_message", _fake_get_message)


@pytest.mark.asyncio
async def test_unsubscribe_reply_suppresses_and_marks_lost(
    monkeypatch, seeded
) -> None:
    _patch_gmail(
        monkeypatch, from_email="lead@acme.com", body="please remove me"
    )

    async def _fake_classify(body, **kw):
        return {
            "category": "unsubscribe",
            "sentiment": "negative",
            "confidence": 0.95,
            "summary": "Asked to be removed",
            "suggested_reply": "",
        }

    monkeypatch.setattr(tracker, "classify_reply", _fake_classify)

    async with seeded.maker() as session:
        user = await session.get(User, seeded.user_id)
        recorded = await tracker.scan_replies_for_user(
            session, user, access_token="tok"
        )
    assert recorded == 1
    async with seeded.maker() as session:
        lead = await session.get(Lead, seeded.lead_id)
        assert lead.lead_status == "lost"
        assert await is_suppressed(
            session, user_id=seeded.user_id, email="lead@acme.com"
        )


@pytest.mark.asyncio
async def test_interested_reply_marks_replied_and_stores_verdict(
    monkeypatch, seeded
) -> None:
    _patch_gmail(
        monkeypatch,
        from_email="Bob <lead@acme.com>",
        body="Sounds great, when can we talk?",
    )

    async def _fake_classify(body, **kw):
        return {
            "category": "meeting_request",
            "sentiment": "positive",
            "confidence": 0.9,
            "summary": "Wants to talk",
            "suggested_reply": "How's Tuesday?",
        }

    monkeypatch.setattr(tracker, "classify_reply", _fake_classify)

    async with seeded.maker() as session:
        user = await session.get(User, seeded.user_id)
        await tracker.scan_replies_for_user(
            session, user, access_token="tok"
        )
    async with seeded.maker() as session:
        lead = await session.get(Lead, seeded.lead_id)
        assert lead.lead_status == "replied"
        acts = (
            await session.execute(
                LeadActivity.__table__.select().where(
                    LeadActivity.kind == "email_replied"
                )
            )
        ).mappings().all()
        assert len(acts) == 1
        assert acts[0]["payload"]["category"] == "meeting_request"
        assert acts[0]["payload"]["suggested_reply"] == "How's Tuesday?"


@pytest.mark.asyncio
async def test_auto_reply_does_not_change_status(monkeypatch, seeded) -> None:
    _patch_gmail(
        monkeypatch,
        from_email="lead@acme.com",
        body="I am out of office until Monday.",
    )

    async def _fake_classify(body, **kw):
        return {
            "category": "auto_reply",
            "sentiment": "neutral",
            "confidence": 0.99,
            "summary": "OOO",
            "suggested_reply": "",
        }

    monkeypatch.setattr(tracker, "classify_reply", _fake_classify)

    async with seeded.maker() as session:
        user = await session.get(User, seeded.user_id)
        await tracker.scan_replies_for_user(
            session, user, access_token="tok"
        )
    async with seeded.maker() as session:
        lead = await session.get(Lead, seeded.lead_id)
        # Auto-reply must not advance the lead — still "contacted".
        assert lead.lead_status == "contacted"
