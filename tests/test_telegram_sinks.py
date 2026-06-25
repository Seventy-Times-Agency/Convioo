"""Tests for the Telegram v2 progress + delivery sinks.

These are the bridge between run_search_with_sinks and the Telegram chat.
They must conform to the ProgressSink / DeliverySink protocols and emit
the right Telegram API calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from leadgen.adapters.telegram_v2.sinks import (
    TelegramDeliverySink,
    TelegramProgressSink,
)
from leadgen.core.services.sinks import DeliverySink, ProgressSink


@pytest.fixture
def tg_calls(monkeypatch):
    """Capture send_message / edit_message_text calls; fake message ids."""
    calls: dict[str, list[Any]] = {"send": [], "edit": []}

    async def fake_send(chat_id, text, parse_mode="HTML"):
        calls["send"].append((chat_id, text))
        return {"result": {"message_id": 42}}

    async def fake_edit(chat_id, message_id, text, parse_mode="HTML"):
        calls["edit"].append((chat_id, message_id, text))
        return {"result": {"message_id": message_id}}

    import leadgen.adapters.telegram_v2.api as tg_api

    monkeypatch.setattr(tg_api, "send_message", fake_send)
    monkeypatch.setattr(tg_api, "edit_message_text", fake_edit)
    return calls


# ── Protocol conformance ──────────────────────────────────────────────────


def test_progress_sink_conforms_to_protocol():
    assert isinstance(TelegramProgressSink(1), ProgressSink)


def test_delivery_sink_conforms_to_protocol():
    assert isinstance(TelegramDeliverySink(1), DeliverySink)


# ── TelegramProgressSink ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_phase_sends_first_then_edits(tg_calls):
    sink = TelegramProgressSink(555)

    await sink.phase("Collecting", "Google Places")
    assert len(tg_calls["send"]) == 1
    assert "Collecting" in tg_calls["send"][0][1]
    assert sink._msg_id == 42

    # Second phase edits the same message rather than sending a new one
    await sink.phase("Scoring")
    assert len(tg_calls["send"]) == 1
    assert len(tg_calls["edit"]) == 1
    assert tg_calls["edit"][0][1] == 42


@pytest.mark.asyncio
async def test_update_builds_progress_bar(tg_calls):
    sink = TelegramProgressSink(555)
    await sink.phase("Working")  # establishes _msg_id
    await sink.update(5, 10)
    assert tg_calls["edit"]
    bar_text = tg_calls["edit"][-1][2]
    assert "50%" in bar_text


@pytest.mark.asyncio
async def test_update_zero_total_is_noop(tg_calls):
    sink = TelegramProgressSink(555)
    await sink.phase("Working")
    edits_before = len(tg_calls["edit"])
    await sink.update(0, 0)
    assert len(tg_calls["edit"]) == edits_before  # no extra edit


@pytest.mark.asyncio
async def test_finish_edits_message(tg_calls):
    sink = TelegramProgressSink(555)
    await sink.phase("Working")
    await sink.finish("All done!")
    assert tg_calls["edit"][-1][2] == "All done!"


@pytest.mark.asyncio
async def test_update_before_phase_is_noop(tg_calls):
    """Without an established message id, update should not crash or edit."""
    sink = TelegramProgressSink(555)
    await sink.update(5, 10)
    assert tg_calls["edit"] == []


# ── TelegramDeliverySink ──────────────────────────────────────────────────


@dataclass
class _Stats:
    total: int = 12
    scored: int = 5


@dataclass
class _Lead:
    name: str
    score_ai: float | None = None
    phone: str | None = None
    website: str | None = None


@pytest.mark.asyncio
async def test_deliver_top_leads_sends_stats_then_leads(tg_calls):
    sink = TelegramDeliverySink(777)
    await sink.deliver_stats("roofers", "London", _Stats())
    await sink.deliver_top_leads(
        [
            _Lead("Acme Roofing", score_ai=88, phone="+1555", website="https://acme.test"),
            _Lead("Best Roofs", score_ai=72),
        ]
    )
    # First the stats card, then the top-leads list
    assert len(tg_calls["send"]) == 2
    assert "Search complete" in tg_calls["send"][0][1]
    assert "roofers" in tg_calls["send"][0][1]
    leads_msg = tg_calls["send"][1][1]
    assert "Acme Roofing" in leads_msg
    assert "88/100" in leads_msg
    assert "https://acme.test" in leads_msg


@pytest.mark.asyncio
async def test_deliver_top_leads_empty_sends_no_leads_message(tg_calls):
    sink = TelegramDeliverySink(777)
    await sink.deliver_top_leads([])
    assert len(tg_calls["send"]) == 1
    assert "No leads found" in tg_calls["send"][0][1]


@pytest.mark.asyncio
async def test_deliver_top_leads_caps_at_five(tg_calls):
    sink = TelegramDeliverySink(777)
    leads = [_Lead(f"Lead {i}", score_ai=50) for i in range(8)]
    await sink.deliver_top_leads(leads)
    leads_msg = tg_calls["send"][-1][1]
    assert "Lead 0" in leads_msg
    assert "Lead 4" in leads_msg
    assert "Lead 5" not in leads_msg  # capped at top 5


@pytest.mark.asyncio
async def test_deliver_insights_sends_snippet(tg_calls):
    sink = TelegramDeliverySink(777)
    await sink.deliver_insights("These leads look promising.")
    assert tg_calls["send"]
    assert "AI Insights" in tg_calls["send"][0][1]


@pytest.mark.asyncio
async def test_deliver_insights_empty_is_noop(tg_calls):
    sink = TelegramDeliverySink(777)
    await sink.deliver_insights("")
    assert tg_calls["send"] == []


@pytest.mark.asyncio
async def test_deliver_insights_truncates_long_text(tg_calls):
    sink = TelegramDeliverySink(777)
    await sink.deliver_insights("x" * 1000)
    sent = tg_calls["send"][0][1]
    assert "…" in sent


@pytest.mark.asyncio
async def test_deliver_excel_is_noop(tg_calls):
    sink = TelegramDeliverySink(777)
    await sink.deliver_excel([_Lead("X")], "niche", "region")
    assert tg_calls["send"] == []
    assert tg_calls["edit"] == []
