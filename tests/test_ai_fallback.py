from __future__ import annotations

import asyncio
import types

import pytest

from leadgen.analysis.ai_analyzer import AIAnalyzer, _heuristic_analysis


def test_heuristic_analysis_scores_with_signals() -> None:
    lead = {
        "category": "Стоматология",
        "website": "https://clinic.example",
        "phone": "+79990000000",
        "rating": 4.8,
        "reviews_count": 180,
        "social_links": {"instagram": "https://instagram.com/clinic"},
        "website_meta": {"has_pricing": True, "has_portfolio": True, "has_blog": True},
    }

    analysis = _heuristic_analysis(lead)

    assert analysis.score >= 75
    assert "hot" in analysis.tags
    assert analysis.error == "anthropic_api_key_missing"


@pytest.mark.anyio
async def test_ai_analyzer_uses_fallback_without_key() -> None:
    analyzer = AIAnalyzer(api_key="")
    lead = {
        "name": "Test Lead",
        "website": None,
        "phone": None,
        "rating": None,
        "reviews_count": 0,
        "social_links": {},
        "website_meta": {},
    }

    result = await analyzer.analyze_lead(lead, niche="кофейни", region="Москва")

    assert result.error == "anthropic_api_key_missing"
    assert result.score >= 0
    assert result.tags


class _EmptyContentMessages:
    async def create(self, **kwargs):
        # Mimic Anthropic returning an empty content array (certain
        # stop conditions) — msg.content[0].text would IndexError.
        return types.SimpleNamespace(content=[], usage=None)


@pytest.mark.anyio
async def test_analyze_lead_falls_back_when_content_empty() -> None:
    analyzer = AIAnalyzer(api_key="dummy-key")
    # Swap in a stub client whose response has no content blocks.
    analyzer.client = types.SimpleNamespace(
        messages=_EmptyContentMessages()
    )
    analyzer._sem = asyncio.Semaphore(1)

    lead = {
        "name": "Empty Co",
        "website": "https://empty.example",
        "phone": "+10000000000",
        "rating": 4.6,
        "reviews_count": 120,
        "social_links": {},
        "website_meta": {},
    }

    result = await analyzer.analyze_lead(
        lead, niche="coffee", region="Boston"
    )

    # Falls through to the same heuristic path used when no client is
    # configured (which carries the heuristic marker), instead of
    # raising IndexError on an empty content array.
    assert "heuristic" in result.tags
    assert result.score >= 0
    assert result.error == "anthropic_api_key_missing"
