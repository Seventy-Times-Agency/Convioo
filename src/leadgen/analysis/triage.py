"""Быстрый отсев «кого не нужно» по названиям — до глубокого анализа.

Если в запуске задано «кого не нужно» (сети, франшизы, госучреждения),
раньше это выяснялось только на полной оценке: сайт скачан, Claude
прочитал досье — и компания выкинута. Здесь один короткий запрос на
пачку до ``TRIAGE_CHUNK`` компаний: только название, категория и
домен. Отсеиваются явные совпадения; сомнительные идут дальше, на
полную оценку, где решение принимается по сайту и отзывам.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from leadgen.analysis._helpers import _extract_json, _first_text
from leadgen.core.services.search import usage_tracker
from leadgen.utils.dedup import domain_root

logger = logging.getLogger(__name__)

TRIAGE_CHUNK = 25

_PROMPT = (
    "You screen B2B prospects before a costly analysis.\n"
    "Target niche: {niche}.\n"
    "Exclude companies that clearly match: {exclusions}.\n"
    "Also exclude companies that are clearly NOT in the target niche.\n"
    "If unsure, keep the company.\n"
    "Reply with JSON only: {{\"exclude\": [indexes]}}.\n\n"
    "Companies:\n{lines}"
)


def _line(i: int, lead: Any) -> str:
    parts = [f"{i}. {getattr(lead, 'name', '') or '?'}"]
    if getattr(lead, "category", None):
        parts.append(str(lead.category))
    dom = domain_root(getattr(lead, "website", None))
    if dom:
        parts.append(dom)
    return " — ".join(parts)


async def _one_chunk(client: Any, model: str, leads: list[Any], niche: str, exclusions: str) -> set[int]:
    prompt = _PROMPT.format(
        niche=niche,
        exclusions=exclusions,
        lines="\n".join(_line(i, lead) for i, lead in enumerate(leads)),
    )
    try:
        msg = await usage_tracker.tracked_create(
            client,
            model=model,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        data = _extract_json(_first_text(msg) or "{}")
        raw = data.get("exclude") if isinstance(data, dict) else None
        out: set[int] = set()
        for v in raw or []:
            try:
                idx = int(v)
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(leads):
                out.add(idx)
        return out
    except Exception:  # noqa: BLE001 — отсев необязателен: пропускаем всех
        logger.warning("triage chunk failed", exc_info=True)
        return set()


async def quick_exclude(leads: list[Any], *, niche: str, exclusions: str) -> set[int]:
    """Индексы компаний, которые явно подпадают под исключения."""
    if not leads or not (exclusions or "").strip():
        return set()
    from leadgen.analysis import AIAnalyzer

    analyzer = AIAnalyzer()
    if analyzer.client is None:
        return set()
    token = usage_tracker.set_stage("triage")
    try:
        chunks = [leads[i : i + TRIAGE_CHUNK] for i in range(0, len(leads), TRIAGE_CHUNK)]
        results = await asyncio.gather(
            *[_one_chunk(analyzer.client, analyzer.model, c, niche, exclusions) for c in chunks]
        )
    finally:
        usage_tracker.reset_stage(token)
    out: set[int] = set()
    for n, found in enumerate(results):
        out.update(n * TRIAGE_CHUNK + i for i in found)
    return out
