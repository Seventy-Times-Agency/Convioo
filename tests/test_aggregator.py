from __future__ import annotations

from leadgen.analysis.aggregator import aggregate_analysis


def test_aggregate_analysis_counts_and_average() -> None:
    leads = [
        {
            "enriched": True,
            "score_ai": 90,
            "website": "https://a.example",
            "social_links": {"vk": "https://vk.com/a"},
            "phone": "+79990000000",
        },
        {
            "enriched": True,
            "score_ai": 60,
            "website": None,
            "social_links": {},
            "phone": None,
        },
        {
            "enriched": False,
            "score_ai": 20,
            "website": "https://b.example",
            "social_links": {"telegram": "https://t.me/b"},
            "phone": "+79991111111",
        },
    ]

    stats = aggregate_analysis(leads)

    assert stats.total == 3
    assert stats.enriched == 2
    assert stats.avg_score == (90 + 60 + 20) / 3
    assert stats.hot_count == 1
    assert stats.warm_count == 1
    assert stats.cold_count == 1
    assert stats.with_website == 2
    assert stats.with_socials == 2
    assert stats.with_phone == 2


def test_aggregate_analysis_handles_invalid_scores() -> None:
    leads = [{"enriched": True, "score_ai": "bad"}, {"enriched": True, "score_ai": None}]

    stats = aggregate_analysis(leads)

    assert stats.total == 2
    assert stats.avg_score == 0.0
    assert stats.hot_count == 0
    assert stats.warm_count == 0
    assert stats.cold_count == 0
