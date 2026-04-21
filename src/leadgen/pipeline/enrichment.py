"""Lead enrichment pipeline.

For each lead from the discovery step we:
  1. Fetch the website (title, description, contacts, socials, snippet).
  2. Fetch Google Place Details (recent reviews).
  3. Run an LLM analysis (score, advice, strengths/weaknesses, red flags).
  4. Persist the enrichment back into the Lead row.

Returns a list of dicts ready for downstream aggregation/delivery.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from leadgen.analysis import AIAnalyzer, LeadAnalysis
from leadgen.collectors import GooglePlacesCollector
from leadgen.collectors.website import (
    WebsiteCollector,
    WebsiteInfo,
    website_info_to_dict,
)
from leadgen.db import Lead, session_factory

logger = logging.getLogger(__name__)


def _build_reviews_summary(reviews: list[dict[str, Any]] | None) -> str | None:
    if not reviews:
        return None

    snippets: list[str] = []
    for review in reviews[:3]:
        rating = review.get("rating", "?")
        text_obj = review.get("text") or review.get("originalText") or {}
        text = text_obj.get("text", "") if isinstance(text_obj, dict) else str(text_obj)
        clean = " ".join(text.split())[:180]
        if clean:
            snippets.append(f"[{rating}/5] {clean}")

    if not snippets:
        return None
    return " | ".join(snippets)


async def enrich_leads(
    leads: list[Lead],
    collector: GooglePlacesCollector,
    niche: str,
    region: str,
) -> list[dict[str, Any]]:
    """Enrich a batch of leads in parallel and persist results."""
    if not leads:
        return []

    website_collector = WebsiteCollector()
    analyzer = AIAnalyzer()

    # 1. Websites in parallel
    website_results: list[WebsiteInfo] = await asyncio.gather(
        *[website_collector.fetch(lead.website) for lead in leads]
    )

    # 2. Google Place Details (reviews) in parallel, with light concurrency cap
    details_sem = asyncio.Semaphore(8)

    async def fetch_details(place_id: str) -> dict[str, Any] | None:
        async with details_sem:
            try:
                return await collector.get_details(place_id)
            except Exception:  # noqa: BLE001
                logger.warning("place details failed for %s", place_id, exc_info=True)
                return None

    details_results: list[dict[str, Any] | None] = await asyncio.gather(
        *[fetch_details(lead.source_id) for lead in leads]
    )

    # 3. Build LLM contexts
    contexts: list[dict[str, Any]] = []
    for lead, website, details in zip(leads, website_results, details_results, strict=False):
        reviews = details.get("reviews") if details else None
        contexts.append(
            {
                "name": lead.name,
                "category": lead.category,
                "address": lead.address,
                "phone": lead.phone,
                "website": lead.website,
                "rating": lead.rating,
                "reviews_count": lead.reviews_count,
                "website_meta": website_info_to_dict(website, include_main_text=True)
                if website.ok
                else None,
                "social_links": website.social_links if website.ok else {},
                "reviews": reviews,
                "reviews_summary": _build_reviews_summary(reviews),
            }
        )

    # 4. AI analysis in parallel
    analyses: list[LeadAnalysis] = await analyzer.analyze_batch(contexts, niche, region)

    # 5. Persist + build enriched dicts
    enriched_dicts: list[dict[str, Any]] = []
    async with session_factory() as session:
        for lead, website, analysis, ctx in zip(
            leads, website_results, analyses, contexts, strict=False
        ):
            db_lead = await session.get(Lead, lead.id)
            if db_lead is None:
                continue

            if website.ok:
                # Store a slim version (no main_text) to keep DB rows light
                db_lead.website_meta = website_info_to_dict(website, include_main_text=False)
                db_lead.social_links = website.social_links

            db_lead.score_ai = float(analysis.score)
            db_lead.tags = analysis.tags
            db_lead.summary = analysis.summary
            db_lead.advice = analysis.advice
            db_lead.strengths = analysis.strengths
            db_lead.weaknesses = analysis.weaknesses
            db_lead.red_flags = analysis.red_flags
            db_lead.reviews_summary = ctx.get("reviews_summary")
            db_lead.enriched = True

            enriched_dicts.append(
                {
                    **ctx,
                    "id": str(db_lead.id),
                    "score_ai": float(analysis.score),
                    "tags": analysis.tags,
                    "summary": analysis.summary,
                    "advice": analysis.advice,
                    "strengths": analysis.strengths,
                    "weaknesses": analysis.weaknesses,
                    "red_flags": analysis.red_flags,
                    "enriched": True,
                }
            )
        await session.commit()

    return enriched_dicts
