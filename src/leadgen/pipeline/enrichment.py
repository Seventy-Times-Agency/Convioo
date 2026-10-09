"""Lead enrichment pipeline.

For each lead from the discovery step, in chunks of ``ENRICH_CHUNK``:
  1. Fetch the website (title, description, contacts, socials, snippet).
  2. Take reviews from the map search (Place Details only for old rows).
  3. Run an LLM analysis (score, advice, strengths/weaknesses, red flags).
  4. Look up the decision maker — only for score >= 50 with an own domain.
  5. Persist the chunk back into the Lead rows.

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
from leadgen.collectors.google_places import REVIEWS_INLINE_KEY
from leadgen.collectors.website import (
    WebsiteCollector,
    WebsiteInfo,
    website_info_to_dict,
)
from leadgen.core.services.account.email_verification import (
    is_role_local,
    verify_email,
)
from leadgen.core.services.crm.decision_maker import (
    LookupInput,
    find_decision_maker,
)
from leadgen.core.services.crm.email_finder import find_email
from leadgen.core.services.search import usage_tracker
from leadgen.db import Lead, session_factory
from leadgen.utils.dedup import domain_root
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

    # Демо тоже пишет стоимость — чтобы счётчик затрат, потолок и
    # предупреждение на 80% были проверяемы без реальных API.
    await usage_tracker.record("google_text_search", 1)
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
                    "decision_maker": bool(owner),
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
    find_decision_makers: bool = True,
) -> list[dict[str, Any]]:
    """Enrich leads chunk by chunk and persist each chunk as it is ready.

    Порядок внутри порции — от дешёвого к дорогому: сайт → оценка
    Claude → ЛПР только для подходящих → запись. Порция записывается
    сразу: если запуск упадёт на середине, готовые лиды уже в базе и
    их можно выдать, а не потерять всё.

    ``progress_callback`` is invoked as ``(done, total)`` across all
    chunks.
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
    total = len(leads)
    enriched_dicts: list[dict[str, Any]] = []
    for start in range(0, total, ENRICH_CHUNK):
        chunk = leads[start : start + ENRICH_CHUNK]

        async def _chunk_progress(done: int, _total: int, _offset: int = start) -> None:
            if progress_callback is not None:
                await progress_callback(_offset + done, total)

        enriched_dicts.extend(
            await _enrich_chunk(
                chunk,
                collector,
                website_collector,
                analyzer,
                niche,
                region,
                user_profile,
                _chunk_progress,
                find_decision_makers,
            )
        )
    return enriched_dicts


#: Размер порции обогащения: сколько лидов доводится до записи за раз.
ENRICH_CHUNK = 10
#: ЛПР ищем только у лидов с такой оценкой и выше — на слабых платные
#: запросы к Hunter/Apollo не окупаются.
DM_MIN_SCORE = 50


def _reviews_for(lead: Lead) -> tuple[list[dict[str, Any]] | None, bool]:
    """Отзывы из поиска по карте. Второе значение — нужна ли карточка
    Google (только старые записи Google без отметки «отзывы запрошены»)."""
    raw = lead.raw or {}
    if raw.get(REVIEWS_INLINE_KEY):
        reviews = raw.get("reviews")
        return (reviews if isinstance(reviews, list) else None), False
    return None, lead.source == "google_places" and bool(lead.source_id)


def _dm_eligible(lead: Lead, analysis: LeadAnalysis) -> bool:
    """ЛПР ищем, только если компания подходит и у неё свой домен:
    по instagram/facebook/yelp Hunter и Apollo никого не находят."""
    return (
        not analysis.excluded
        and analysis.score >= DM_MIN_SCORE
        and domain_root(lead.website) is not None
    )


async def _enrich_chunk(
    leads: list[Lead],
    collector: GooglePlacesCollector | None,
    website_collector: WebsiteCollector,
    analyzer: AIAnalyzer,
    niche: str,
    region: str,
    user_profile: dict[str, Any] | None,
    progress_callback: ProgressCallback | None,
    find_decision_makers: bool,
) -> list[dict[str, Any]]:
    # 1. Сайты — параллельно (бесплатно).
    usage_tracker.set_stage("enrichment")
    website_results: list[WebsiteInfo] = await asyncio.gather(
        *[website_collector.fetch(lead.website) for lead in leads]
    )

    # 2. Отзывы: уже пришли поиском по карте. Карточку Google просим
    # только для старых записей без отзывов в поиске.
    details_sem = asyncio.Semaphore(8)

    async def reviews_of(lead: Lead) -> list[dict[str, Any]] | None:
        inline, need_details = _reviews_for(lead)
        if not need_details or collector is None:
            return inline
        async with details_sem:
            try:
                details = await collector.get_details(lead.source_id)
            except Exception:  # noqa: BLE001
                logger.warning("place details failed for %s", lead.source_id, exc_info=True)
                return None
        return details.get("reviews") if details else None

    reviews_results = await asyncio.gather(*[reviews_of(lead) for lead in leads])

    # 3. Build LLM contexts
    contexts: list[dict[str, Any]] = []
    for lead, website, reviews in zip(leads, website_results, reviews_results, strict=False):
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

    # 4. AI analysis — personalized for the user's profile
    usage_tracker.set_stage("scoring")
    analyses: list[LeadAnalysis] = await analyzer.analyze_batch(
        contexts,
        niche,
        region,
        user_profile=user_profile,
        progress_callback=progress_callback,
    )

    # 5. ЛПР — только для прошедших оценку (50+) со своим доменом.
    # Выключенный поиск ЛПР — «не искали»: ни одного запроса наружу.
    dm_results: list[dict | None] = [None] * len(leads)
    if find_decision_makers:
        usage_tracker.set_stage("decision_maker")
        dm_sem = asyncio.Semaphore(4)

        async def lookup_dm(lead: Lead, website: WebsiteInfo) -> dict | None:
            async with dm_sem:
                try:
                    return await find_decision_maker(
                        LookupInput(
                            company_name=lead.name,
                            website=lead.website,
                            phone=lead.phone,
                            address=lead.address,
                            homepage_text=getattr(website, "main_text", None),
                            social_links=(website.social_links if website.ok else {}),
                        )
                    )
                except Exception:  # noqa: BLE001
                    return None

        eligible = [
            i for i, (lead, analysis) in enumerate(zip(leads, analyses, strict=False))
            if _dm_eligible(lead, analysis)
        ]
        found = await asyncio.gather(
            *[lookup_dm(leads[i], website_results[i]) for i in eligible]
        )
        for i, dm in zip(eligible, found, strict=False):
            dm_results[i] = dm

    # 6. Persist + build enriched dicts (Hunter-подбор почты — досье).
    usage_tracker.set_stage("enrichment")
    enriched_dicts: list[dict[str, Any]] = []
    # Collect (db_lead, chosen_email) so we can verify all of them
    # concurrently (bounded) after the per-lead writes.
    to_verify: list[tuple[Lead, str]] = []
    async with session_factory() as session:
        for lead, website, analysis, ctx, dm in zip(
            leads, website_results, analyses, contexts, dm_results, strict=False
        ):
            db_lead = await session.get(Lead, lead.id)
            if db_lead is None:
                continue
            if analysis.excluded:
                # «Кого не нужно» из запуска: в выдачу не идёт. Отметка в
                # таблицах «уже видели» остаётся — снова не всплывёт.
                await session.delete(db_lead)
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
            from leadgen.core.services.crm.business_language import (
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
                    "decision_maker": bool(dm),
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
