"""Tests for free-form search intent extraction (niches + region)."""

from __future__ import annotations

import pytest

from leadgen.analysis.ai_analyzer import (
    AIAnalyzer,
    _clean_niches,
    _heuristic_intent,
)


def test_clean_niches_dedupes_and_trims() -> None:
    raw = [
        "  Стоматология  ",
        "стоматология",  # dupe, case-insensitive
        "фитнес-клуб",
        "",  # empty, drop
        "а",  # too short, drop
        "x" * 200,  # too long, drop
    ]
    assert _clean_niches(raw) == ["стоматология", "фитнес-клуб"]


def test_clean_niches_handles_non_list() -> None:
    assert _clean_niches(None) == []
    assert _clean_niches("стоматология") == ["стоматология"]
    assert _clean_niches([42, None, "кофейня"]) == ["кофейня"]


def test_clean_niches_caps_at_seven() -> None:
    raw = [f"ниша-{i}" for i in range(20)]
    assert len(_clean_niches(raw)) == 7


def test_heuristic_intent_splits_on_commas() -> None:
    out = _heuristic_intent("стоматологии, фитнес-клубы, автосервисы")
    assert out["niches"] == ["стоматологии", "фитнес-клубы", "автосервисы"]
    assert out["region"] is None
    assert out["error"] is None


def test_heuristic_intent_splits_on_conjunctions() -> None:
    out = _heuristic_intent("хочу стройку или бьюти")
    # "хочу стройку" is fine as a single chunk; "бьюти" is the second
    assert "бьюти" in out["niches"]
    assert len(out["niches"]) >= 2


def test_heuristic_intent_empty_returns_empty() -> None:
    assert _heuristic_intent("")["niches"] == []


def test_heuristic_intent_whole_text_when_no_separators() -> None:
    out = _heuristic_intent("стоматология")
    assert out["niches"] == ["стоматология"]


@pytest.mark.asyncio
async def test_extract_search_intent_without_api_key_uses_heuristic() -> None:
    analyzer = AIAnalyzer(api_key="")
    out = await analyzer.extract_search_intent(
        "рестораны, кафе и бары в Питере"
    )
    assert len(out["niches"]) >= 2
    assert all(isinstance(n, str) for n in out["niches"])
    # Heuristic fallback doesn't parse region — that's the LLM's job.
    assert out["region"] is None


@pytest.mark.asyncio
async def test_extract_search_intent_empty_input() -> None:
    analyzer = AIAnalyzer(api_key="")
    out = await analyzer.extract_search_intent("   ")
    assert out["niches"] == []
