"""Tests for profile formatting helpers used across onboarding / edit."""

from __future__ import annotations

import pytest

from leadgen.analysis.ai_analyzer import _BUSINESS_SIZE_LABEL, _format_user_profile
from leadgen.bot.keyboards import AGE_OPTIONS, BUSINESS_SIZE_OPTIONS


def test_age_options_are_unique() -> None:
    codes = [c for _, c in AGE_OPTIONS]
    assert len(codes) == len(set(codes))


def test_business_size_options_are_unique() -> None:
    codes = [c for _, c in BUSINESS_SIZE_OPTIONS]
    assert len(codes) == len(set(codes))


def test_business_size_label_covers_all_codes() -> None:
    # Every code offered to the user must have a human label for the AI prompt.
    for _, code in BUSINESS_SIZE_OPTIONS:
        assert code in _BUSINESS_SIZE_LABEL, f"no label for business_size code {code!r}"


@pytest.mark.parametrize(
    "profile",
    [
        {},
        None,
        {"display_name": "Иван"},
        {"age_range": "25-34", "business_size": "solo"},
        {
            "display_name": "Аня",
            "age_range": "35-44",
            "business_size": "small",
            "profession": "SMM-агентство",
            "home_region": "Алматы",
            "niches": ["рестораны", "кафе"],
        },
    ],
)
def test_format_user_profile_never_crashes(profile: dict | None) -> None:
    # The formatter is called on every AI request — it must survive any
    # combination of missing fields without raising.
    out = _format_user_profile(profile)
    assert isinstance(out, str)


def test_format_user_profile_includes_all_filled_fields() -> None:
    out = _format_user_profile(
        {
            "display_name": "Марк",
            "age_range": "25-34",
            "business_size": "solo",
            "profession": "Веб-разработчик",
            "home_region": "Берлин",
            "niches": ["кофейни", "барбершопы"],
        }
    )
    assert "Марк" in out
    assert "25-34" in out
    assert "соло" in out  # business_size label, not raw code
    assert "Веб-разработчик" in out
    assert "Берлин" in out
    assert "кофейни" in out
