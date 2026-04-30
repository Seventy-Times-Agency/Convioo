"""Tests for profile formatting helpers used by the AI prompt builder."""

from __future__ import annotations

import pytest

from leadgen.analysis.ai_analyzer import _format_user_profile


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
