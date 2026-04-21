from __future__ import annotations

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
