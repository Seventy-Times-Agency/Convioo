"""Tests for AIAnalyzer.normalize_profession heuristic fallback.

The LLM branch is covered via the /diag command in production; the
heuristic path (no API key / API error) must still return something
usable so the rest of the pipeline keeps working.
"""

from __future__ import annotations

import pytest

from leadgen.analysis.ai_analyzer import AIAnalyzer


@pytest.mark.asyncio
async def test_normalize_profession_without_key_returns_trimmed_original() -> None:
    # No client → we return the input unchanged (trimmed). The rest of the
    # pipeline is designed to handle raw text, so this is a safe fallback.
    analyzer = AIAnalyzer(api_key="")
    raw = "  Мы начинающее агентство, делаем сайты и рекламу  "
    result = await analyzer.normalize_profession(raw)
    assert result == raw.strip()


@pytest.mark.asyncio
async def test_normalize_profession_empty_returns_empty() -> None:
    analyzer = AIAnalyzer(api_key="")
    assert await analyzer.normalize_profession("") == ""
    assert await analyzer.normalize_profession("   ") == ""
