"""Stateless aggregation of enriched lead data into base-level statistics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean
from typing import Any


@dataclass(slots=True)
class BaseStats:
    total: int
    enriched: int
    avg_score: float
    hot_count: int
    warm_count: int
    cold_count: int
    with_website: int
    with_socials: int
    with_phone: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def aggregate_analysis(enriched_leads: list[dict[str, Any]]) -> BaseStats:
    """Compute base-level statistics from a list of enriched lead dicts."""
    total = len(enriched_leads)
    enriched_count = sum(1 for lead in enriched_leads if lead.get("enriched"))

    scores: list[float] = []
    for lead in enriched_leads:
        s = lead.get("score_ai")
        if s is not None:
            try:
                scores.append(float(s))
            except (TypeError, ValueError):
                continue

    avg_score = float(mean(scores)) if scores else 0.0
    hot = sum(1 for s in scores if s >= 75)
    warm = sum(1 for s in scores if 50 <= s < 75)
    cold = sum(1 for s in scores if s < 50)

    with_website = sum(1 for lead in enriched_leads if lead.get("website"))
    with_socials = sum(
        1
        for lead in enriched_leads
        if (lead.get("social_links") or {}) and len(lead["social_links"]) > 0
    )
    with_phone = sum(1 for lead in enriched_leads if lead.get("phone"))

    return BaseStats(
        total=total,
        enriched=enriched_count,
        avg_score=avg_score,
        hot_count=hot,
        warm_count=warm,
        cold_count=cold,
        with_website=with_website,
        with_socials=with_socials,
        with_phone=with_phone,
    )
