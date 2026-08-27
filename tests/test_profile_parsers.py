"""Tests for free-form profile-field parsers (name / age / biz / region).

These exercise the heuristic fast paths only — the LLM branch is
covered by integration-level smoke via /diag in production. The
heuristic path is what runs whenever ANTHROPIC_API_KEY is unset or the
API call fails, so it must always produce a reasonable answer.
"""

from __future__ import annotations

import pytest

from leadgen.analysis.ai_analyzer import (
    _NAME_PREFIX_PATTERNS,
    _REGION_PREFIX_PATTERNS,
    AIAnalyzer,
    _age_from_number,
    _biz_from_headcount,
    _strip_patterns,
)


@pytest.mark.parametrize(
    "age,expected",
    [
        (15, "<18"),
        (18, "18-24"),
        (24, "18-24"),
        (25, "25-34"),
        (34, "25-34"),
        (35, "35-44"),
        (44, "35-44"),
        (45, "45-54"),
        (54, "45-54"),
        (55, "55+"),
        (99, "55+"),
        (-1, None),
        (200, None),
    ],
)
def test_age_from_number(age: int, expected: str | None) -> None:
    assert _age_from_number(age) == expected


@pytest.mark.parametrize(
    "n,expected",
    [
        (0, "solo"),
        (1, "solo"),
        (2, "small"),
        (10, "small"),
        (11, "medium"),
        (50, "medium"),
        (51, "large"),
        (500, "large"),
    ],
)
def test_biz_from_headcount(n: int, expected: str) -> None:
    assert _biz_from_headcount(n) == expected


def test_strip_patterns_name() -> None:
    assert _strip_patterns("меня зовут Алексей", _NAME_PREFIX_PATTERNS) == "Алексей"
    assert _strip_patterns("Зови меня Марком", _NAME_PREFIX_PATTERNS) == "Марком"
    assert _strip_patterns("Саша", _NAME_PREFIX_PATTERNS) == "Саша"


def test_strip_patterns_region() -> None:
    assert _strip_patterns("я из Москвы", _REGION_PREFIX_PATTERNS) == "Москвы"
    assert _strip_patterns("живу в Берлине", _REGION_PREFIX_PATTERNS) == "Берлине"
    assert _strip_patterns("Алматы", _REGION_PREFIX_PATTERNS) == "Алматы"


@pytest.mark.asyncio
async def test_parse_name_bare_word() -> None:
    # No API key → heuristic path.
    analyzer = AIAnalyzer(api_key="")
    assert await analyzer.parse_name("Саша") == "Саша"


@pytest.mark.asyncio
async def test_parse_name_with_prefix() -> None:
    analyzer = AIAnalyzer(api_key="")
    assert await analyzer.parse_name("меня зовут Алексей") == "Алексей"


@pytest.mark.asyncio
async def test_parse_name_politeness() -> None:
    analyzer = AIAnalyzer(api_key="")
    # "Марк пожалуйста" → "Марк"
    assert await analyzer.parse_name("зови меня Марк пожалуйста") == "Марк"


@pytest.mark.asyncio
async def test_parse_name_empty() -> None:
    analyzer = AIAnalyzer(api_key="")
    assert await analyzer.parse_name("") is None
    assert await analyzer.parse_name("   ") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text,expected",
    [
        ("мне 30", "25-34"),
        ("28 лет", "25-34"),
        ("44", "35-44"),
        ("55+", "55+"),
        ("17 с половиной", "<18"),
        ("я 50-летний юрист", "45-54"),
    ],
)
async def test_parse_age_number_and_range(text: str, expected: str) -> None:
    analyzer = AIAnalyzer(api_key="")
    assert await analyzer.parse_age(text) == expected


@pytest.mark.asyncio
async def test_parse_age_empty_and_ambiguous() -> None:
    analyzer = AIAnalyzer(api_key="")
    # No number, no range string, no LLM → None
    assert await analyzer.parse_age("") is None
    assert await analyzer.parse_age("не скажу") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text,expected",
    [
        ("я соло", "solo"),
        ("один работаю", "solo"),
        ("фрилансер", "solo"),
        ("команда 5 человек", "small"),
        ("компания на 30 сотрудников", "medium"),
        ("крупный бизнес на 200", "large"),
        ("solo", "solo"),
    ],
)
async def test_parse_business_size(text: str, expected: str) -> None:
    analyzer = AIAnalyzer(api_key="")
    assert await analyzer.parse_business_size(text) == expected


@pytest.mark.asyncio
async def test_parse_business_size_empty() -> None:
    analyzer = AIAnalyzer(api_key="")
    assert await analyzer.parse_business_size("") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text,expected",
    [
        ("Москва", "Москва"),
        ("Нью-Йорк", "Нью-Йорк"),
        ("я из Берлина", "Берлина"),
        ("живу в Алматы", "Алматы"),
        ("город Казань", "Казань"),
    ],
)
async def test_parse_region(text: str, expected: str) -> None:
    analyzer = AIAnalyzer(api_key="")
    assert await analyzer.parse_region(text) == expected


@pytest.mark.asyncio
async def test_parse_region_empty() -> None:
    analyzer = AIAnalyzer(api_key="")
    assert await analyzer.parse_region("") is None
    assert await analyzer.parse_region("   ") is None
