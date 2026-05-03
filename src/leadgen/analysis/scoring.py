"""Lead scoring (Anthropic call + heuristic fallback)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from leadgen.analysis._helpers import (
    LeadAnalysis,
    _extract_json,
    _heuristic_analysis,
)
from leadgen.analysis.prompts import _build_lead_context, _build_system_prompt

logger = logging.getLogger(__name__)


class ScoringMixin:
    async def analyze_lead(
        self,
        lead: dict[str, Any],
        niche: str,
        region: str,
        user_profile: dict[str, Any] | None = None,
    ) -> LeadAnalysis:
        if self.client is None:
            return _heuristic_analysis(lead)

        async with self._sem:
            try:
                context = _build_lead_context(lead, niche, region)
                system_prompt = _build_system_prompt(user_profile)
                msg = await self.client.messages.create(
                    model=self.model,
                    max_tokens=900,
                    system=system_prompt,
                    messages=[{"role": "user", "content": context}],
                )
                text = msg.content[0].text  # type: ignore[union-attr]
                data = _extract_json(text)
                return LeadAnalysis(
                    score=int(data.get("score", 0) or 0),
                    tags=[str(t) for t in (data.get("tags") or [])],
                    summary=str(data.get("summary") or ""),
                    advice=str(data.get("advice") or ""),
                    strengths=[str(s) for s in (data.get("strengths") or [])],
                    weaknesses=[str(s) for s in (data.get("weaknesses") or [])],
                    red_flags=[str(s) for s in (data.get("red_flags") or [])],
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("AI analyze_lead failed for %s", lead.get("name"))
                heuristic = _heuristic_analysis(lead)
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
