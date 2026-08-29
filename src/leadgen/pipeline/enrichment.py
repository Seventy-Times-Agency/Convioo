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
import urllib.parse
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from leadgen.analysis import AIAnalyzer, LeadAnalysis
from leadgen.collectors import GooglePlacesCollector
from leadgen.collectors.website import (
    WebsiteCollector,
    WebsiteInfo,
    website_info_to_dict,
)
from leadgen.core.services.decision_maker import find_decision_maker
from leadgen.core.services.email_finder import find_email
from leadgen.core.services.email_verification import (
    is_role_local,
    verify_email,
)
from leadgen.db import Lead, session_factory
from leadgen.utils.locale_text import normalize_lang, pick

ProgressCallback = Callable[[int, int], Awaitable[None]]

logger = logging.getLogger(__name__)


def pick_primary_email(emails: list[str] | None) -> str | None:
    """Choose the best address to send to from a scraped email list.

    Prefers a personal (non-role) address over a role one (info@,
    sales@…); within a group keeps source order. Returns None when the
    list is empty / contains no usable address.
    """
    if not emails:
        return None
    personal: list[str] = []
    role: list[str] = []
    for raw in emails:
        if not isinstance(raw, str):
            continue
        addr = raw.strip()
        if "@" not in addr:
            continue
        local = addr.split("@", 1)[0]
        (role if is_role_local(local) else personal).append(addr)
    if personal:
        return personal[0]
    if role:
        return role[0]
    return None


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


async def _apply_demo_enrichment(
    leads: list[Lead],
    progress_callback: ProgressCallback | None = None,
) -> list[dict[str, Any]]:
    """Demo-mode enrichment: copy the mock collector's ready-made
    analysis (raw["demo"]) onto each lead — no network, no keys."""
    import asyncio as _asyncio

    from leadgen.core.services import usage_tracker

    # Демо тоже пишет стоимость — чтобы счётчик затрат, потолок и
    # предупреждение на 80% были проверяемы без реальных API.
    await usage_tracker.record("google_text_search", 1)
    await usage_tracker.record("google_place_details", len(leads))
    await usage_tracker.record("claude_input_tokens", 8_000 * len(leads))
    await usage_tracker.record("claude_output_tokens", 1_200 * len(leads))

    enriched_dicts: list[dict[str, Any]] = []
    total = len(leads)
    async with session_factory() as session:
        for i, lead in enumerate(leads):
            db_lead = await session.get(Lead, lead.id)
            if db_lead is None:
                continue
            demo = (
                lead.raw.get("demo")
                if isinstance(lead.raw, dict)
                else None
            ) or {}
            score = float(demo.get("score", 60))
            db_lead.score_ai = score
            db_lead.summary = demo.get("summary")
            db_lead.advice = demo.get("advice")
            db_lead.strengths = demo.get("strengths") or []
            db_lead.weaknesses = demo.get("weaknesses") or []
            db_lead.red_flags = []
            db_lead.tags = demo.get("tags") or []
            db_lead.business_language = demo.get("business_language")
            db_lead.business_language_confidence = (
                "likely" if demo.get("business_language") else None
            )
            owner = demo.get("owner")
            if owner:
                db_lead.website_meta = {
                    **(db_lead.website_meta or {}),
                    "contact_person": {"name": owner, "source": "demo"},
                }
            db_lead.email_status = "unknown"
            db_lead.enriched = True
            enriched_dicts.append(
                {
                    "id": str(db_lead.id),
                    "name": db_lead.name,
                    "category": db_lead.category,
                    "address": db_lead.address,
                    "phone": db_lead.phone,
                    "website": db_lead.website,
                    "rating": db_lead.rating,
                    "reviews_count": db_lead.reviews_count,
                    "score_ai": score,
                    "tags": db_lead.tags,
                    "summary": db_lead.summary,
                    "advice": db_lead.advice,
                    "strengths": db_lead.strengths,
                    "weaknesses": db_lead.weaknesses,
                    "red_flags": [],
                    "enriched": True,
                }
            )
            if progress_callback is not None:
                await progress_callback(i + 1, total)
            # Лёгкая пауза, чтобы прогресс в UI выглядел как живой
            # скоринг, а не мгновенный дамп.
            await _asyncio.sleep(0.05)
        await session.commit()
    return enriched_dicts


async def enrich_leads(
    leads: list[Lead],
    # None только в демо-режиме — там обогащение идёт по муляжу и
    # Google Place Details не вызывается.
    collector: GooglePlacesCollector | None,
    niche: str,
    region: str,
    user_profile: dict[str, Any] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> list[dict[str, Any]]:
    """Enrich a batch of leads in parallel and persist results.

    ``progress_callback`` is invoked as ``(done, total)`` after each AI
    analysis completes — the heaviest step, which dominates wall-clock
    time and benefits most from per-item feedback.
    """
    if not leads:
        return []

    # Демо-режим: «обогащение» без сети и ключей — муляж парсера уже
    # положил готовый анализ в raw["demo"]; переносим его на лид,
    # отдаём прогресс как настоящий скоринг.
    from leadgen.config import get_settings as _gs

    if _gs().demo_active:
        return await _apply_demo_enrichment(leads, progress_callback)

    website_collector = WebsiteCollector()
    analyzer = AIAnalyzer()

    # 1. Websites in parallel
    website_results: list[WebsiteInfo] = await asyncio.gather(
        *[website_collector.fetch(lead.website) for lead in leads]
    )

    # Decision maker lookup — parallel, capped concurrency
    _dm_sem = asyncio.Semaphore(4)

    async def _lookup_dm(lead: Lead, website: WebsiteInfo) -> dict | None:
        async with _dm_sem:
            try:
                return await find_decision_maker(
                    lead.name,
                    getattr(website, "main_text", None),
                    website.social_links if website.ok else {},
                )
            except Exception:
                return None

    dm_results: list[dict | None] = await asyncio.gather(
        *[_lookup_dm(lead, website) for lead, website in zip(leads, website_results, strict=False)]
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

    # 4. AI analysis in parallel — personalized for the user's profile
    analyses: list[LeadAnalysis] = await analyzer.analyze_batch(
        contexts,
        niche,
        region,
        user_profile=user_profile,
        progress_callback=progress_callback,
    )

    # 5. Persist + build enriched dicts
    enriched_dicts: list[dict[str, Any]] = []
    # Collect (db_lead, chosen_email) so we can verify all of them
    # concurrently (bounded) after the per-lead writes, instead of
    # serializing 50 DNS round-trips inside the loop.
    to_verify: list[tuple[Lead, str]] = []
    async with session_factory() as session:
        for lead, website, analysis, ctx, dm in zip(
            leads, website_results, analyses, contexts, dm_results, strict=False
        ):
            db_lead = await session.get(Lead, lead.id)
            if db_lead is None:
                continue

            if website.ok:
                # Store a slim version (no main_text) to keep DB rows light
                db_lead.website_meta = website_info_to_dict(website, include_main_text=False)
                db_lead.social_links = website.social_links

            if dm is not None:
                current_meta = db_lead.website_meta or {}
                db_lead.website_meta = {**current_meta, "contact_person": dm}

            # Email waterfall: website scrape → Hunter.io
            meta = db_lead.website_meta or {}
            if not meta.get("emails"):
                domain = urllib.parse.urlparse(lead.website or "").netloc.removeprefix("www.")
                if domain:
                    found = await find_email(domain)
                    if found:
                        meta["emails"] = [found]
                        db_lead.website_meta = {**meta}

            # Pick the single best primary address for outreach. Defer the
            # actual DNS verification until after the loop (verified in a
            # bounded gather) so we don't serialize one lookup per lead.
            primary = pick_primary_email(meta.get("emails"))
            if primary:
                db_lead.contact_email = primary
                to_verify.append((db_lead, primary))
            else:
                db_lead.email_status = "unknown"

            db_lead.score_ai = float(analysis.score)

            # System tags are created in the search owner's UI language
            # (the pipeline already carries language_code in
            # ``user_profile``).
            tag_lang = normalize_lang(
                (user_profile or {}).get("language_code")
            )
            no_mobile_tag = pick(
                tag_lang,
                ru="Нет мобайла",
                uk="Немає мобайла",
                en="No mobile",
            )
            outdated_site_tag = pick(
                tag_lang,
                ru="Устаревший сайт",
                uk="Застарілий сайт",
                en="Outdated website",
            )
            dead_socials_tag = pick(
                tag_lang,
                ru="Мёртвые соцсети",
                uk="Мертві соцмережі",
                en="Dead social media",
            )
            rating_drop_tag = pick(
                tag_lang,
                ru="Просевший рейтинг",
                uk="Просілий рейтинг",
                en="Declining rating",
            )

            tags: list[str] = list(analysis.tags or [])
            meta = db_lead.website_meta or {}
            pagespeed = meta.get("pagespeed_mobile")
            if pagespeed is not None and pagespeed < 50 and no_mobile_tag not in tags:
                tags.append(no_mobile_tag)
            last_year = meta.get("last_modified_year")
            if last_year and last_year < 2021 and outdated_site_tag not in tags:
                tags.append(outdated_site_tag)

            social = db_lead.social_links or {}
            if len(social) == 0 and dead_socials_tag not in tags:
                tags.append(dead_socials_tag)

            snapshots = db_lead.rating_snapshots or []
            if len(snapshots) >= 2:
                rating_delta = snapshots[-1]["rating"] - snapshots[0]["rating"]
                if rating_delta <= -0.2 and rating_drop_tag not in tags:
                    tags.append(rating_drop_tag)
            db_lead.tags = tags
            db_lead.summary = analysis.summary
            db_lead.advice = analysis.advice
            db_lead.strengths = analysis.strengths
            db_lead.weaknesses = analysis.weaknesses
            db_lead.red_flags = analysis.red_flags
            db_lead.score_components = analysis.score_components
            db_lead.reviews_summary = ctx.get("reviews_summary")

            # Business-language verdict (generic engine; RU/UA preset
            # renders as separate labels in the База filter).
            from leadgen.core.services.business_language import (
                classify_business_language,
            )

            reviews_texts = [
                str(r.get("text") or "")
                for r in (ctx.get("reviews") or [])
                if isinstance(r, dict)
            ]
            owner_names = []
            if dm and isinstance(dm.get("name"), str):
                owner_names.append(dm["name"])
            meta_for_lang = ctx.get("website_meta") or {}
            verdict = classify_business_language(
                website_text=(
                    meta_for_lang.get("main_text")
                    if isinstance(meta_for_lang, dict)
                    else None
                ),
                reviews_texts=reviews_texts,
                owner_names=owner_names,
                social_links=db_lead.social_links or {},
                extra_text=lead.name,
            )
            db_lead.business_language = verdict.language
            db_lead.business_language_confidence = verdict.confidence

            db_lead.enriched = True

            enriched_dicts.append(
                {
                    **ctx,
                    "id": str(db_lead.id),
                    "score_ai": float(analysis.score),
                    "tags": tags,
                    "summary": analysis.summary,
                    "advice": analysis.advice,
                    "strengths": analysis.strengths,
                    "weaknesses": analysis.weaknesses,
                    "red_flags": analysis.red_flags,
                    "enriched": True,
                }
            )

        # Verify chosen addresses concurrently with a bounded semaphore so
        # the DNS lookups for a 50-lead batch overlap but never fan out
        # unboundedly. A verification failure must never break enrichment.
        if to_verify:
            verify_sem = asyncio.Semaphore(8)
            checked_at = datetime.now(timezone.utc)

            async def _verify(addr: str) -> str:
                async with verify_sem:
                    try:
                        result = await verify_email(addr)
                        return result.status
                    except Exception:  # noqa: BLE001
                        logger.warning(
                            "enrichment: email verify crashed for %s",
                            addr,
                            exc_info=True,
                        )
                        return "unknown"

            statuses = await asyncio.gather(
                *[_verify(addr) for _lead, addr in to_verify]
            )
            for (db_lead, _addr), status in zip(
                to_verify, statuses, strict=False
            ):
                db_lead.email_status = status
                db_lead.email_checked_at = checked_at

        await session.commit()

    return enriched_dicts
