"""Фильтры до оценки: сайт / рейтинг / отзывы на сырых находках."""

from __future__ import annotations

from leadgen.collectors.google_places import RawLead
from leadgen.pipeline.search import _passes_prefilters


def _lead(**kw) -> RawLead:
    base = {"name": "X", "source": "google_places", "source_id": "1", "raw": {}}
    base.update(kw)
    return RawLead(**base)


def test_website_modes():
    with_site = _lead(website="https://a.com")
    no_site = _lead(website=None)
    assert _passes_prefilters(with_site, {"website": "with"})
    assert not _passes_prefilters(no_site, {"website": "with"})
    assert _passes_prefilters(no_site, {"website": "without"})
    assert not _passes_prefilters(with_site, {"website": "without"})
    assert _passes_prefilters(with_site, {}) and _passes_prefilters(no_site, {})


def test_rating_and_reviews_pass_when_unknown():
    unrated = _lead(rating=None, reviews_count=None)
    weak = _lead(rating=3.2, reviews_count=4)
    strong = _lead(rating=4.7, reviews_count=120)
    pf = {"min_rating": 4.0, "min_reviews": 20}
    assert _passes_prefilters(unrated, pf)
    assert not _passes_prefilters(weak, pf)
    assert _passes_prefilters(strong, pf)
