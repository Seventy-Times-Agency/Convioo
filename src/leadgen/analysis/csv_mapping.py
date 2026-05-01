"""Heuristic CSV-column → lead-field mapper.

Used as the cheap first pass before the AIAnalyzer's Claude fallback
on /api/v1/searches/csv-suggest-mapping. Pure dictionary lookup, no
network, deterministic — safe to call in tight loops.
"""

from __future__ import annotations

from typing import Any

# Substring → (canonical field, confidence). Order matters only for
# stability; the matcher always picks the highest-confidence hit.
CSV_HEADER_KEYWORDS: tuple[tuple[str, str, float], ...] = (
    # name
    ("company", "name", 0.95),
    ("business", "name", 0.9),
    ("organisation", "name", 0.9),
    ("organization", "name", 0.9),
    ("brand", "name", 0.8),
    ("название", "name", 0.95),
    ("компани", "name", 0.9),
    ("назва", "name", 0.9),
    ("name", "name", 0.85),
    # website
    ("website", "website", 0.95),
    ("homepage", "website", 0.9),
    ("domain", "website", 0.9),
    ("site", "website", 0.85),
    ("url", "website", 0.85),
    ("сайт", "website", 0.95),
    ("домен", "website", 0.9),
    # region / location
    ("region", "region", 0.9),
    ("location", "region", 0.9),
    ("address", "region", 0.85),
    ("city", "region", 0.9),
    ("country", "region", 0.85),
    ("регион", "region", 0.95),
    ("город", "region", 0.95),
    ("адрес", "region", 0.9),
    # phone
    ("phone", "phone", 0.95),
    ("tel", "phone", 0.9),
    ("mobile", "phone", 0.85),
    ("телефон", "phone", 0.95),
    # category
    ("category", "category", 0.95),
    ("industry", "category", 0.9),
    ("niche", "category", 0.85),
    ("sector", "category", 0.85),
    ("indust", "category", 0.85),
    ("категория", "category", 0.95),
    ("ниша", "category", 0.9),
    ("отрасль", "category", 0.9),
    # skip
    ("id", "skip", 0.7),
    ("row", "skip", 0.6),
    ("line", "skip", 0.6),
    ("number", "skip", 0.5),
    ("№", "skip", 0.6),
)


def heuristic_csv_mapping(headers: list[str]) -> list[dict[str, Any]]:
    """Cheap keyword-based first pass over CSV headers.

    Returns one entry per header. Headers that don't match any keyword
    fall through with ``field="extras"`` and confidence 0.0 — the AI
    pass downstream can refine them.
    """
    out: list[dict[str, Any]] = []
    for raw in headers:
        h_norm = (raw or "").strip().lower()
        best: tuple[str, float] = ("extras", 0.0)
        for needle, canonical, conf in CSV_HEADER_KEYWORDS:
            if needle in h_norm and conf > best[1]:
                best = (canonical, conf)
        out.append({"header": raw, "field": best[0], "confidence": best[1]})
    return out
