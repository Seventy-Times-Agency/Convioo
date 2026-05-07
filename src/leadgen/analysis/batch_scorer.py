"""Batch scoring: ask Claude about N leads in a single request.

The default scorer in :mod:`leadgen.analysis.scoring` issues one
Anthropic call per lead. With prompt caching that's already cheap,
but the per-request HTTP overhead and the duplicated user-profile
preamble still add up at 50+ leads per search.

Batching trades a slightly fattier prompt for one tenth the HTTP
calls. Concretely:

* **Tokens.** The 4 KB system prompt is sent once per chunk instead
  of once per lead — caching makes the marginal saving smaller, but
  the per-call ``messages`` framing (~150 tokens) is genuinely
  duplicated and goes away here.
* **Latency.** Five round-trips at 1.5 s each beats one round-trip
  at ~3 s, especially on the cold-cache path.
* **Reliability.** Anthropic occasionally returns malformed JSON
  on a single lead. Per-chunk we can still recover the other four
  by parsing the array element-wise, while a per-lead retry storm
  amplifies a transient API hiccup.

The batch path is **opt-in** via ``BATCH_SCORING_ENABLED`` so we can
ship this and roll over per-tenant once we're confident the JSON
shape comes back stable. Default behaviour is unchanged when off.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from leadgen.analysis._helpers import (
    LeadAnalysis,
    _extract_json,
    _heuristic_analysis,
)
from leadgen.analysis.anthropic_caching import cached_system
from leadgen.analysis.prompts import _build_lead_context, _build_system_prompt
from leadgen.analysis.scoring import _build_score_components
from leadgen.core.services import usage_tracker

logger = logging.getLogger(__name__)


# Five is the sweet spot empirically: small enough to keep the
# response well under the 900-token max we use elsewhere, big enough
# to amortise the round-trip + system prompt across the chunk.
DEFAULT_CHUNK_SIZE = 5


_BATCH_INSTRUCTIONS = (
    "You will receive an array of leads numbered 0..N-1. Score each one "
    "using the same rubric as a single-lead call. Return a JSON object "
    'of the form {"results": [{"index": <int>, "score": ..., '
    '"tags": [...], "summary": "...", "advice": "...", '
    '"strengths": [...], "weaknesses": [...], "red_flags": [...]}]}. '
    "Preserve the input ``index`` exactly so the caller can re-align. "
    "Do NOT wrap the JSON in markdown. Do NOT add commentary."
)


def _build_batch_user_message(
    leads: list[dict[str, Any]], niche: str, region: str
) -> str:
    """Concat the per-lead contexts into one message annotated by index."""
    blocks: list[str] = [_BATCH_INSTRUCTIONS, "", f"Leads ({len(leads)}):"]
    for i, lead in enumerate(leads):
        blocks.append(f"\n=== Lead index={i} ===")
        blocks.append(_build_lead_context(lead, niche, region))
    return "\n".join(blocks)


def _parse_batch_response(
    text: str, leads: list[dict[str, Any]]
) -> list[LeadAnalysis]:
    """Decode Claude's array reply, falling back to heuristics per slot."""
    fallbacks = [_heuristic_analysis(lead) for lead in leads]

    parsed = _extract_json(text)
    if not isinstance(parsed, dict):
        logger.warning("batch_scorer: top-level JSON not an object, full fallback")
        return fallbacks
    rows = parsed.get("results")
    if not isinstance(rows, list):
        logger.warning("batch_scorer: 'results' missing or wrong type, full fallback")
        return fallbacks

    out: list[LeadAnalysis] = list(fallbacks)
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            idx = int(row.get("index"))
        except (TypeError, ValueError):
            continue
        if idx < 0 or idx >= len(leads):
            continue
        total_score = int(row.get("score", 0) or 0)
        components = _build_score_components(leads[idx], total_score)
        out[idx] = LeadAnalysis(
            score=total_score,
            tags=[str(t) for t in (row.get("tags") or [])],
            summary=str(row.get("summary") or ""),
            advice=str(row.get("advice") or ""),
            strengths=[str(s) for s in (row.get("strengths") or [])],
            weaknesses=[str(s) for s in (row.get("weaknesses") or [])],
            red_flags=[str(s) for s in (row.get("red_flags") or [])],
            score_components=components,
        )
    return out


async def analyze_chunk(
    *,
    client: Any,
    model: str,
    sem: asyncio.Semaphore,
    leads: list[dict[str, Any]],
    niche: str,
    region: str,
    user_profile: dict[str, Any] | None,
) -> list[LeadAnalysis]:
    """Run one Anthropic call covering ``leads`` and parse the array reply.

    The ``client`` / ``model`` / ``sem`` are passed in so this module
    stays decoupled from :class:`AIAnalyzer`'s lifecycle — tests and
    the eventual SDK migration can drop in any awaitable client.
    """
    if not leads:
        return []
    if client is None:
        return [_heuristic_analysis(lead) for lead in leads]

    system_prompt = _build_system_prompt(user_profile)
    user_message = _build_batch_user_message(leads, niche, region)
    # Budget proportional to chunk size so a 5-lead reply has
    # headroom; the per-lead tail uses ~600 tokens in practice.
    max_tokens = max(900, 700 * len(leads))

    async with sem:
        try:
            msg = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=cached_system(system_prompt),
                messages=[{"role": "user", "content": user_message}],
            )
            await usage_tracker.record_claude_usage(
                getattr(msg, "usage", None)
            )
            text = "".join(
                getattr(block, "text", "") for block in msg.content
            )
        except Exception as exc:  # noqa: BLE001 — degrade to heuristics
            logger.exception(
                "batch_scorer: chunk failed (%d leads): %s", len(leads), exc
            )
            return [_heuristic_analysis(lead) for lead in leads]

    return _parse_batch_response(text, leads)


async def analyze_in_chunks(
    *,
    client: Any,
    model: str,
    sem: asyncio.Semaphore,
    leads: list[dict[str, Any]],
    niche: str,
    region: str,
    user_profile: dict[str, Any] | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    progress_callback: Any = None,
) -> list[LeadAnalysis]:
    """Drive ``analyze_chunk`` across all leads with optional progress hook.

    Mirrors the surface of ``ScoringMixin.analyze_batch`` so call
    sites can swap implementations behind a feature flag.
    """
    if not leads:
        return []

    chunks: list[list[dict[str, Any]]] = [
        leads[i : i + chunk_size] for i in range(0, len(leads), chunk_size)
    ]

    async def run_chunk(chunk: list[dict[str, Any]]) -> list[LeadAnalysis]:
        return await analyze_chunk(
            client=client,
            model=model,
            sem=sem,
            leads=chunk,
            niche=niche,
            region=region,
            user_profile=user_profile,
        )

    results: list[LeadAnalysis] = []
    total = len(leads)
    done = 0
    for coro in asyncio.as_completed([run_chunk(c) for c in chunks]):
        chunk_results = await coro
        results.extend(chunk_results)
        done += len(chunk_results)
        if progress_callback is not None:
            try:
                await progress_callback(min(done, total), total)
            except Exception:  # noqa: BLE001
                logger.exception("batch_scorer progress_callback raised")
    return results
