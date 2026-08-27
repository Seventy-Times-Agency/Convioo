"""Lead scoring (Anthropic call + heuristic fallback)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from leadgen.analysis._helpers import (
    LeadAnalysis,
    _extract_json,
    _first_text,
    _heuristic_analysis,
)
from leadgen.analysis.anthropic_caching import cached_system
from leadgen.analysis.prompts import _build_lead_context, _build_system_prompt
from leadgen.core.services import usage_tracker

logger = logging.getLogger(__name__)


def _build_score_components(lead: dict[str, Any], total: int) -> dict[str, int]:
    """Decompose total AI score into named buckets for UI display.

    Maxima: rating=35, website=25, social=20, email=10, recency=10 → 100.
    When the AI returns a score we can't decompose exactly, we scale
    each heuristic proportionally so the components sum to total.
    """
    rating = float(lead.get("rating") or 0)
    reviews_count = int(lead.get("reviews_count") or 0)

    raw_rating = 0
    if rating >= 4.5:
        raw_rating = 35
    elif rating >= 4.0:
        raw_rating = 25
    elif rating >= 3.5:
        raw_rating = 15
    elif rating > 0:
        raw_rating = 5

    raw_website = 25 if lead.get("website") else 0

    social_links = lead.get("social_links") or {}
    raw_social = min(20, len(social_links) * 7) if social_links else 0

    website_meta = lead.get("website_meta") or {}
    emails = website_meta.get("emails") or []
    raw_email = 10 if emails else 0

    if reviews_count >= 100:
        raw_recency = 10
    elif reviews_count >= 30:
        raw_recency = 7
    elif reviews_count >= 5:
        raw_recency = 4
    else:
        raw_recency = 0

    raw_total = raw_rating + raw_website + raw_social + raw_email + raw_recency
    if raw_total == 0:
        return {"rating": 0, "website": 0, "social": 0, "email": 0, "recency": 0}

    scale = total / raw_total
    return {
        "rating": round(raw_rating * scale),
        "website": round(raw_website * scale),
        "social": round(raw_social * scale),
        "email": round(raw_email * scale),
        "recency": round(raw_recency * scale),
    }


class ScoringMixin:
    async def analyze_lead(
        self,
        lead: dict[str, Any],
        niche: str,
        region: str,
        user_profile: dict[str, Any] | None = None,
    ) -> LeadAnalysis:
        lang = (user_profile or {}).get("language_code")
        if self.client is None:
            return _heuristic_analysis(lead, lang=lang)

        async with self._sem:
            try:
                context = _build_lead_context(lead, niche, region)
                system_prompt = _build_system_prompt(user_profile)
                msg = await self.client.messages.create(
                    model=self.model,
                    max_tokens=900,
                    system=cached_system(system_prompt),
                    messages=[{"role": "user", "content": context}],
                )
                await usage_tracker.record_claude_usage(getattr(msg, "usage", None))
                text = _first_text(msg)
                if text is None:
                    # Empty/non-text content (certain stop conditions) —
                    # fall back to the same heuristic path used when no
                    # client is configured.
                    return _heuristic_analysis(lead, lang=lang)
                data = _extract_json(text)
                total_score = int(data.get("score", 0) or 0)
                components = _build_score_components(lead, total_score)
                return LeadAnalysis(
                    score=total_score,
                    tags=[str(t) for t in (data.get("tags") or [])],
                    summary=str(data.get("summary") or ""),
                    advice=str(data.get("advice") or ""),
                    strengths=[str(s) for s in (data.get("strengths") or [])],
                    weaknesses=[str(s) for s in (data.get("weaknesses") or [])],
                    red_flags=[str(s) for s in (data.get("red_flags") or [])],
                    score_components=components,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("AI analyze_lead failed for %s", lead.get("name"))
                heuristic = _heuristic_analysis(lead, lang=lang)
                heuristic.error = str(exc)
                return heuristic

    async def analyze_batch(
        self,
        leads: list[dict[str, Any]],
        niche: str,
        region: str,
        user_profile: dict[str, Any] | None = None,
        progress_callback: Any = None,
    ) -> list[LeadAnalysis]:
        if not leads:
            return []

        # Batch path is opt-in via env. When enabled we skip the
        # per-lead loop entirely and let the chunk module own
        # parsing + heuristic-fallback semantics.
        from leadgen.config import get_settings as _settings_for_batch

        _bs = _settings_for_batch()
        if _bs.batch_scoring_enabled and self.client is not None:
            from leadgen.analysis.batch_scorer import analyze_in_chunks

            return await analyze_in_chunks(
                client=self.client,
                model=self.model,
                sem=self._sem,
                leads=leads,
                niche=niche,
                region=region,
                user_profile=user_profile,
                chunk_size=max(1, _bs.batch_scoring_chunk_size),
                progress_callback=progress_callback,
            )

        async def indexed(i: int, ctx: dict[str, Any]) -> tuple[int, LeadAnalysis]:
            result = await self.analyze_lead(
                ctx, niche, region, user_profile=user_profile
            )
            return i, result

        tasks = [asyncio.create_task(indexed(i, c)) for i, c in enumerate(leads)]
        results: list[LeadAnalysis | None] = [None] * len(leads)
        total = len(leads)
        for done, coro in enumerate(asyncio.as_completed(tasks), start=1):
            i, result = await coro
            results[i] = result
            if progress_callback is not None:
                try:
                    await progress_callback(done, total)
                except Exception:  # noqa: BLE001
                    logger.exception("analyze_batch progress_callback raised")
        return [r for r in results if r is not None]
