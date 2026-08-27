from __future__ import annotations

from leadgen.pipeline.enrichment import _build_reviews_summary


def test_build_reviews_summary_limits_and_formats() -> None:
    reviews = [
        {"rating": 5, "text": {"text": "Отличный сервис и грамотные специалисты"}},
        {"rating": 4, "originalText": {"text": "Работают быстро и качественно"}},
        {"rating": 3, "text": {"text": "Нормально"}},
        {"rating": 2, "text": {"text": "Этот отзыв не должен попасть в summary"}},
    ]

    summary = _build_reviews_summary(reviews)

    assert summary is not None
    assert "[5/5]" in summary
    assert "[4/5]" in summary
    assert "[3/5]" in summary
    assert "не должен попасть" not in summary


def test_build_reviews_summary_empty() -> None:
    assert _build_reviews_summary([]) is None
    assert _build_reviews_summary(None) is None
