"""Search orchestrator — client-agnostic core.

End-to-end flow (``run_search_with_sinks``):
  1. Load SearchQuery, mark running.
  2. Discover leads via ``GooglePlacesCollector``.
  3. Persist non-duplicate leads and remember them in ``user_seen_leads``.
  4. Enrich the top-N (websites + reviews + AI analysis).
  5. Aggregate stats and ask the LLM for high-level insights.
  6. Deliver everything via the ``DeliverySink``.
  7. Emit metrics at every terminal branch.

The core talks to the outside world only through ``ProgressSink`` and
``DeliverySink`` — no FastAPI, nothing client-specific. Web adapter
builds SSE-backed progress + DB-backed delivery sinks and calls in.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from html import escape as html_escape
from typing import Any

from sqlalchemy import select, update

from leadgen.analysis import AIAnalyzer, aggregate_analysis
from leadgen.collectors import GooglePlacesCollector, RawLead
from leadgen.collectors.google_places import GooglePlacesError
from leadgen.collectors.osm import discover_with_lock
from leadgen.config import get_settings
from leadgen.core.services import DeliverySink, ProgressSink
from leadgen.core.services.webhooks import (
    emit_event as emit_webhook_event,
)
from leadgen.core.services.webhooks import (
    serialize_lead as serialize_lead_for_webhook,
)
from leadgen.core.services.webhooks import (
    serialize_search as serialize_search_for_webhook,
)
from leadgen.data.cities import match_city
from leadgen.data.niches import match_niche
from leadgen.db import Lead, SearchQuery, session_factory
from leadgen.db.models import TeamSeenLead, UserSeenLead
from leadgen.pipeline.enrichment import enrich_leads
from leadgen.utils.dedup import domain_root, normalize_phone
from leadgen.utils.geocode import bbox_from_circle, geocode_region_dedup
from leadgen.utils.metrics import (
    leads_discovered_total,
    leads_persisted_total,
    leads_skipped_total,
    search_duration_seconds,
    searches_total,
)

logger = logging.getLogger(__name__)

SEARCH_TIMEOUT_SEC = 10 * 60


async def _empty_leads() -> list[RawLead]:
    """Sentinel coroutine for the asyncio.gather in discovery.

    Lets the OSM branch be a real awaitable when disabled instead of
    branching the gather call site.
    """
    return []


async def _yelp_search(
    *,
    niche: str,
    region: str,
    yelp_categories: list[str],
    bbox: tuple[float, float, float, float] | None,
    api_key: str,
    limit: int,
) -> list[RawLead]:
    """Run a Yelp search and never raise — return [] on any failure.

    Wrapping the collector here keeps the gather() call site short
    and matches the OSM branch's "best-effort" behavior: a flaky
    third-party should not fail the whole search.
    """
    from leadgen.collectors.yelp import YelpCollector, YelpError

    try:
        async with YelpCollector(api_key, max_results=limit) as client:
            return await client.search(
                niche=niche,
                region=region,
                yelp_categories=yelp_categories,
                bbox=bbox,
            )
    except YelpError as exc:
        logger.warning("yelp branch disabled this run: %s", exc)
        return []


_SLAVIC_CYRILLIC = frozenset({"ru", "uk", "be", "bg", "sr", "mk"})
# Languages whose business names would normally appear in Latin script.
# Drives the "no Cyrillic-only listings when targeting English/German/etc"
# filter — wrong script is a strong "not for this market" signal.
_LATIN_LANGUAGES = frozenset(
    {
        "en", "de", "fr", "es", "it", "pl", "cs", "sk", "pt", "nl",
        "sv", "no", "da", "fi", "et", "lv", "lt", "ro", "hu", "tr",
        "id", "ms", "vi", "az",
    }
)
# Default Google Places ``regionCode`` to bias for a given language.
# Empty entries leave the bias unset (e.g. en is global so no bias).
_LANGUAGE_REGION_HINT: dict[str, str] = {
    "uk": "UA",
    "ru": "",  # avoid biasing toward RU per project policy
    "be": "BY",
    "bg": "BG",
    "de": "DE",
    "fr": "FR",
    "es": "ES",
    "it": "IT",
    "pl": "PL",
    "cs": "CZ",
    "sk": "SK",
    "pt": "PT",
    "nl": "NL",
    "sv": "SE",
    "no": "NO",
    "da": "DK",
    "fi": "FI",
    "tr": "TR",
    "ja": "JP",
    "zh": "CN",
    "ko": "KR",
}


def _text_blob(lead: RawLead) -> str:
    return f"{lead.name or ''} {lead.address or ''} {lead.category or ''}"


def _has_cyrillic_signal(lead: RawLead) -> bool:
    """True when the place name or address contains Cyrillic glyphs.

    Cheap, high-precision proxy for "this business operates in
    Russian/Ukrainian/etc". Cyrillic in either field on Google Maps
    is essentially never accidental — the owner deliberately wrote
    their name in Cyrillic for that audience.
    """
    return any("Ѐ" <= char <= "ӿ" for char in _text_blob(lead))


def _is_predominantly_cyrillic(lead: RawLead) -> bool:
    """True when most letters in the lead's text are Cyrillic.

    Used as the inverse of the Latin-language filter: a name like
    "Кофейня Бариста" should be rejected when the user is searching
    for German leads, but a mostly-Latin name with one Cyrillic
    accent shouldn't be punished.
    """
    blob = _text_blob(lead)
    cyr = lat = 0
    for char in blob:
        if "Ѐ" <= char <= "ӿ":
            cyr += 1
        elif char.isalpha():
            lat += 1
    return cyr > 0 and cyr >= lat


def _passes_language_filter(
    lead: RawLead, target_languages: list[str]
) -> bool:
    """Hard client-side filter for the per-search language target.

    Logic:
      - If any Slavic-Cyrillic target is present, keep ``cyrillic``-
        signaled leads (existing behaviour).
      - Otherwise, if every target uses Latin script, drop leads whose
        text is predominantly Cyrillic.
      - Mixed / unknown targets pass through; Claude scores them.
    """
    if not target_languages:
        return True
    codes = {c.lower() for c in target_languages}
    if codes & _SLAVIC_CYRILLIC:
        return _has_cyrillic_signal(lead)
    if codes <= _LATIN_LANGUAGES:
        return not _is_predominantly_cyrillic(lead)
    return True


def _collector_locale(
    user_language: str | None, target_languages: list[str]
) -> tuple[str, str | None]:
    """Pick (languageCode, regionCode) for the Google Places call.

    Per-search ``target_languages`` win: if the user said "give me
    German leads", honour that on the discovery call instead of
    using the UI language. Region bias defaults to the language's
    home country (DE → DE, UK → UA) so Places stops returning
    Berlin clinics for Munich queries.
    """
    if target_languages:
        primary = target_languages[0].lower()
        region = _LANGUAGE_REGION_HINT.get(primary)
        return primary, region or None
    return user_language or "en", None


# ── Client-agnostic pipeline ───────────────────────────────────────────────


async def run_search_with_timeout(
    query_id: uuid.UUID,
    progress: ProgressSink | None,
    delivery: DeliverySink | None,
    user_profile: dict[str, Any] | None = None,
) -> None:
    """Wrap ``run_search_with_sinks`` with the wall-clock timeout.

    On timeout, marks the query failed in the DB and emits a
    ``timeout`` metric. Sinks are best-effort — if delivery hasn't
    been finalised yet, the SSE consumer will see the search end as
    failed via the regular DB poll.
    """
    try:
        await asyncio.wait_for(
            run_search_with_sinks(
                query_id,
                progress=progress,
                delivery=delivery,
                user_profile=user_profile,
            ),
            timeout=SEARCH_TIMEOUT_SEC,
        )
    except TimeoutError:
        logger.error(
            "run_search TIMEOUT after %ds for query %s", SEARCH_TIMEOUT_SEC, query_id
        )
        searches_total.labels(status="timeout").inc()
        async with session_factory() as session:
            await session.execute(
                update(SearchQuery)
                .where(SearchQuery.id == query_id)
                .values(
                    status="failed",
                    error=f"timeout after {SEARCH_TIMEOUT_SEC}s",
                )
            )
            await session.commit()




async def run_search_with_sinks(
    query_id: uuid.UUID,
    progress: ProgressSink | None,
    delivery: DeliverySink | None,
    user_profile: dict[str, Any] | None = None,
) -> None:
    """Pure pipeline — no aiogram, no web framework, only sinks.

    Accepts optional sinks so batch / CLI callers can pass None and still
    run the whole search; every sink call is routed through
    ``_pcall`` / ``_dcall`` which silently no-op when the sink is absent.
    """
    logger.info(
        "run_search_with_sinks ENTER query_id=%s profile=%s",
        query_id,
        bool(user_profile),
    )
    started_at = time.monotonic()
    try:
        async with session_factory() as session:
            query = await session.get(SearchQuery, query_id)
            if query is None:
                logger.error("run_search: query %s not found", query_id)
                return
            query.status = "running"
            await session.commit()
            niche, region = query.niche, query.region
            user_id = query.user_id
            team_id = query.team_id
            target_languages = list(query.target_languages or [])
            per_search_limit = query.max_results
            scope = (query.scope or "city").lower()
            radius_m = query.radius_m
            cached_lat = query.center_lat
            cached_lon = query.center_lon
            # Per-search source override (T6). None = honour env flags.
            enabled_sources_override: set[str] | None = (
                {s.lower() for s in (query.enabled_sources or [])}
                or None
            )
        logger.info(
            "run_search: query loaded niche=%r region=%r scope=%s radius_m=%s user=%s",
            niche,
            region,
            scope,
            radius_m,
            user_id,
        )

        # 1. Discovery — Google Places + (optional) OSM in parallel.
        await _pcall(progress, "phase",
            "🔎 <b>Шаг 1/4: ищу компании в Google Maps + OSM</b>",
            "сканирую выдачу · обычно 5–15 секунд",
        )
        ui_language = (user_profile or {}).get("language_code")
        language_code, region_code = _collector_locale(
            ui_language, target_languages
        )
        collector = GooglePlacesCollector(
            language=language_code,
            region_code=region_code,
        )
        logger.info("run_search: calling google places search")

        # Try to resolve the niche to a taxonomy entry — only matched
        # niches have OSM tag mappings. If nothing matches we silently
        # fall back to Google-only (matches Phase 2 behaviour).
        niche_entry = match_niche(niche, language=language_code)
        osm_tags = list(niche_entry.osm_tags) if niche_entry else []

        # Geo shape: figure out the bbox we'll feed both collectors.
        # 1) curated city → use stored coords + circle around them
        # 2) anything else → ask Nominatim (cached, single-flight)
        bbox: tuple[float, float, float, float] | None = None
        center_lat: float | None = cached_lat
        center_lon: float | None = cached_lon
        if cached_lat is not None and cached_lon is not None:
            if scope in {"city", "metro"} and radius_m:
                bbox = bbox_from_circle(cached_lat, cached_lon, radius_m)
        else:
            curated = match_city(region) if scope in {"city", "metro"} else None
            if curated is not None:
                center_lat, center_lon = curated.lat, curated.lon
                if radius_m:
                    bbox = bbox_from_circle(curated.lat, curated.lon, radius_m)
            else:
                geo = await geocode_region_dedup(region)
                if geo is not None:
                    center_lat, center_lon = geo.lat, geo.lon
                    if scope in {"state", "country"}:
                        bbox = geo.bbox_tuple()
                    elif scope in {"city", "metro"} and radius_m:
                        bbox = bbox_from_circle(geo.lat, geo.lon, radius_m)
                    elif scope in {"city", "metro"}:
                        # No radius supplied → keep Nominatim's natural
                        # city bbox (still strictly limits Google to the
                        # city boundary instead of biasing to similarly-
                        # named places elsewhere).
                        bbox = geo.bbox_tuple()

        # Persist the resolved center so re-runs hit the same anchor.
        if (
            center_lat is not None
            and center_lon is not None
            and (cached_lat != center_lat or cached_lon != center_lon)
        ):
            async with session_factory() as session:
                await session.execute(
                    update(SearchQuery)
                    .where(SearchQuery.id == query_id)
                    .values(
                        center_lat=center_lat, center_lon=center_lon
                    )
                )
                await session.commit()

        # Per-source toggle: ``enabled_sources_override`` (when set on
        # the SearchQuery row by the create endpoint) wins over the
        # global env flags. Lets a user skip a hot-rate-limited source
        # without rotating env vars.
        def _source_active(name: str, env_active: bool) -> bool:
            if enabled_sources_override is not None:
                return name in enabled_sources_override
            return env_active

        if _source_active("google", True):
            google_task = collector.search(
                niche=niche,
                region=region,
                location_restriction_bbox=bbox,
            )
        else:
            google_task = _empty_leads()

        if (
            osm_tags
            and _source_active("osm", get_settings().osm_enabled)
        ):
            osm_task = discover_with_lock(
                niche=niche,
                region=region,
                osm_tags=osm_tags,
                limit=get_settings().max_results_per_query,
                bbox=bbox,
            )
        else:
            osm_task = _empty_leads()

        # Yelp Fusion — opt-in per niche via the taxonomy's
        # ``yelp_categories``. Free-text niches (no taxonomy match)
        # silently skip Yelp so we don't burn the daily budget on
        # weak queries.
        yelp_categories = (
            list(niche_entry.yelp_categories) if niche_entry else []
        )
        yelp_settings = get_settings()
        if (
            yelp_categories
            and _source_active("yelp", yelp_settings.yelp_enabled)
            and yelp_settings.yelp_api_key
        ):
            yelp_task = _yelp_search(
                niche=niche,
                region=region,
                yelp_categories=yelp_categories,
                bbox=bbox,
                api_key=yelp_settings.yelp_api_key,
                limit=get_settings().max_results_per_query,
            )
        else:
            yelp_task = _empty_leads()

        google_leads, osm_leads, yelp_leads = await asyncio.gather(
            google_task, osm_task, yelp_task, return_exceptions=False
        )
        logger.info(
            "run_search: google=%d osm=%d yelp=%d (tags=%s, yelp_cats=%s)",
            len(google_leads),
            len(osm_leads),
            len(yelp_leads),
            osm_tags,
            yelp_categories,
        )
        leads_discovered_total.labels(source="google_places").inc(len(google_leads))
        leads_discovered_total.labels(source="osm").inc(len(osm_leads))
        leads_discovered_total.labels(source="yelp").inc(len(yelp_leads))

        # Merge: Google first (it has rating + reviews so the eventual
        # AI scorer has more to chew on), OSM + Yelp appended. Cross-
        # source dedup happens later via the existing fuzzy keys.
        raw_leads: list[RawLead] = (
            list(google_leads) + list(osm_leads) + list(yelp_leads)
        )

        # Per-search target language filter. Cyrillic-required for
        # Slavic targets (existing behaviour); Cyrillic-rejected for
        # Latin-script targets. Mixed targets stay as soft hints for
        # Claude downstream.
        if target_languages:
            pre_filter_count = len(raw_leads)
            raw_leads = [
                lead
                for lead in raw_leads
                if _passes_language_filter(lead, target_languages)
            ]
            logger.info(
                "run_search: language filter (%s) kept %d/%d leads",
                target_languages,
                len(raw_leads),
                pre_filter_count,
            )
            if user_profile is None:
                user_profile = {}
            user_profile = {
                **user_profile,
                "target_languages": list(target_languages),
            }

        # Apply the per-search limit AFTER language filtering so the
        # cap matches what the user actually keeps, not the raw page
        # of Google results.
        cap = per_search_limit or get_settings().max_results_per_query
        cap = max(1, min(cap, get_settings().max_results_per_query, 100))
        raw_leads = raw_leads[:cap]

        if not raw_leads:
            await _pcall(progress, "finish",
                f"По запросу «{html_escape(niche)} — {html_escape(region)}» "
                "ничего не найдено.\nПопробуй другую формулировку или более крупный регион.",
            )
            async with session_factory() as session:
                await session.execute(
                    update(SearchQuery)
                    .where(SearchQuery.id == query_id)
                    .values(
                        status="done",
                        finished_at=datetime.now(timezone.utc),
                        leads_count=0,
                    )
                )
                await session.commit()
            searches_total.labels(status="no_results").inc()
            return

        # 2. Persist + cross-run dedup.
        # The synthetic web-demo user (id=0) is shared by every visitor of
        # the open demo. If we deduped against its seen-leads history the
        # second visitor to search "roofing NYC" would get zero results —
        # every company is already "seen" by somebody's prior run. Skip
        # the dedup memory for user_id=0; real users keep the cross-run
        # dedup that the Telegram flow relies on.
        skip_dedup = user_id == 0 and team_id is None
        # Pre-compute the three dedup axes for every incoming lead
        # once so we don't re-normalise per loop iteration.
        lead_keys: list[tuple[RawLead, str | None, str | None]] = [
            (r, normalize_phone(r.phone), domain_root(r.website))
            for r in raw_leads
        ]

        async with session_factory() as session:
            incoming_source_ids = [r.source_id for r, _, _ in lead_keys if r.source_id]
            incoming_phones = [p for _, p, _ in lead_keys if p]
            incoming_domains = [d for _, _, d in lead_keys if d]

            seen_source_ids: set[str] = set()
            seen_phones: set[str] = set()
            seen_domains: set[str] = set()

            if not skip_dedup and (
                incoming_source_ids or incoming_phones or incoming_domains
            ):
                # Personal dedup along all three axes. We OR the keys
                # together so a Google rebrand that shipped a fresh
                # place_id but kept the phone still reads as a dupe.
                if user_id != 0:
                    user_clauses = []
                    if incoming_source_ids:
                        user_clauses.append(
                            UserSeenLead.source_id.in_(incoming_source_ids)
                        )
                    if incoming_phones:
                        user_clauses.append(
                            UserSeenLead.phone_e164.in_(incoming_phones)
                        )
                    if incoming_domains:
                        user_clauses.append(
                            UserSeenLead.domain_root.in_(incoming_domains)
                        )
                    from sqlalchemy import or_ as _or
                    user_rows = await session.execute(
                        select(
                            UserSeenLead.source_id,
                            UserSeenLead.phone_e164,
                            UserSeenLead.domain_root,
                        )
                        .where(UserSeenLead.user_id == user_id)
                        .where(UserSeenLead.source == "google_places")
                        .where(_or(*user_clauses))
                    )
                    for sid, phone, domain in user_rows.all():
                        if sid:
                            seen_source_ids.add(sid)
                        if phone:
                            seen_phones.add(phone)
                        if domain:
                            seen_domains.add(domain)
                # Team dedup mirror — a teammate's seen-lead blocks the
                # same place from showing up in another member's CRM.
                if team_id is not None:
                    team_clauses = []
                    if incoming_source_ids:
                        team_clauses.append(
                            TeamSeenLead.source_id.in_(incoming_source_ids)
                        )
                    if incoming_phones:
                        team_clauses.append(
                            TeamSeenLead.phone_e164.in_(incoming_phones)
                        )
                    if incoming_domains:
                        team_clauses.append(
                            TeamSeenLead.domain_root.in_(incoming_domains)
                        )
                    from sqlalchemy import or_ as _or
                    team_rows = await session.execute(
                        select(
                            TeamSeenLead.source_id,
                            TeamSeenLead.phone_e164,
                            TeamSeenLead.domain_root,
                        )
                        .where(TeamSeenLead.team_id == team_id)
                        .where(TeamSeenLead.source == "google_places")
                        .where(_or(*team_clauses))
                    )
                    for sid, phone, domain in team_rows.all():
                        if sid:
                            seen_source_ids.add(sid)
                        if phone:
                            seen_phones.add(phone)
                        if domain:
                            seen_domains.add(domain)

            batch_source_ids: set[str] = set()
            batch_phones: set[str] = set()
            batch_domains: set[str] = set()
            rows: list[Lead] = []
            seen_to_insert: list[dict[str, Any]] = []
            duplicates = 0
            for r, phone_key, domain_key in lead_keys:
                if not r.source_id or r.source_id in batch_source_ids:
                    leads_skipped_total.labels(reason="missing_source_id").inc()
                    continue
                # Cross-run dedup: any of the three axes matching prior
                # history is enough to call this a duplicate.
                if (
                    r.source_id in seen_source_ids
                    or (phone_key and phone_key in seen_phones)
                    or (domain_key and domain_key in seen_domains)
                ):
                    duplicates += 1
                    leads_skipped_total.labels(reason="duplicate").inc()
                    continue
                # Within-batch dedup: same logic, checks the keys we've
                # already accepted in this run.
                if (
                    (phone_key and phone_key in batch_phones)
                    or (domain_key and domain_key in batch_domains)
                ):
                    leads_skipped_total.labels(reason="duplicate").inc()
                    continue
                batch_source_ids.add(r.source_id)
                if phone_key:
                    batch_phones.add(phone_key)
                if domain_key:
                    batch_domains.add(domain_key)
                rows.append(
                    Lead(
                        query_id=query_id,
                        name=r.name,
                        website=r.website,
                        phone=r.phone,
                        address=r.address,
                        category=r.category,
                        rating=r.rating,
                        reviews_count=r.reviews_count,
                        latitude=r.latitude,
                        longitude=r.longitude,
                        source=r.source,
                        source_id=r.source_id,
                        raw=r.raw,
                    )
                )
                seen_to_insert.append(
                    {
                        "user_id": user_id,
                        "source": r.source,
                        "source_id": r.source_id,
                        "phone_e164": phone_key,
                        "domain_root": domain_key,
                    }
                )

            if not rows:
                logger.info(
                    "run_search: all %d leads were dupes for user %s",
                    duplicates,
                    user_id,
                )
                async with session_factory() as s2:
                    await s2.execute(
                        update(SearchQuery)
                        .where(SearchQuery.id == query_id)
                        .values(
                            status="done",
                            finished_at=datetime.now(timezone.utc),
                            leads_count=0,
                        )
                    )
                    await s2.commit()
                await _pcall(progress, "finish",
                    f"Все {duplicates} компаний по этому запросу ты уже получал(а). "
                    "Попробуй другую нишу или регион, чтобы найти новые."
                )
                searches_total.labels(status="no_results").inc()
                return

            session.add_all(rows)
            if seen_to_insert and not skip_dedup:
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                if user_id != 0:
                    stmt = pg_insert(UserSeenLead).values(seen_to_insert)
                    stmt = stmt.on_conflict_do_nothing(
                        index_elements=["user_id", "source", "source_id"]
                    )
                    await session.execute(stmt)
                if team_id is not None:
                    team_rows_to_insert = [
                        {
                            "team_id": team_id,
                            "source": item["source"],
                            "source_id": item["source_id"],
                            "phone_e164": item.get("phone_e164"),
                            "domain_root": item.get("domain_root"),
                            "first_user_id": user_id,
                        }
                        for item in seen_to_insert
                    ]
                    team_stmt = pg_insert(TeamSeenLead).values(team_rows_to_insert)
                    team_stmt = team_stmt.on_conflict_do_nothing(
                        index_elements=["team_id", "source", "source_id"]
                    )
                    await session.execute(team_stmt)
            await session.commit()
            leads_persisted_total.inc(len(rows))
            logger.info(
                "run_search: persisted %d leads (%d duplicates filtered) for user %s",
                len(rows),
                duplicates,
                user_id,
            )

            result = await session.execute(
                select(Lead)
                .where(Lead.query_id == query_id)
                .order_by(
                    Lead.rating.desc().nullslast(),
                    Lead.reviews_count.desc().nullslast(),
                )
            )
            all_leads = list(result.scalars().all())

        enrich_n = min(get_settings().max_enrich_leads, len(all_leads))

        # 3. Enrichment
        await _pcall(progress, "phase",
            f"🧠 <b>Шаг 2/4: анализ топ-{enrich_n} компаний</b>",
            "сайт · соцсети · отзывы · AI-оценка под твою услугу",
        )
        await _pcall(progress, "update", 0, enrich_n)
        top_leads = all_leads[:enrich_n]
        enriched = await enrich_leads(
            top_leads,
            collector,
            niche,
            region,
            user_profile=user_profile,
            progress_callback=(progress.update if progress is not None else None),
        )

        # 4. Aggregation + base insights
        await _pcall(progress, "phase",
            "📊 <b>Шаг 3/4: сводный отчёт по базе</b>",
            "считаю статистику и формирую AI-инсайты",
        )
        analyzer = AIAnalyzer()
        stats = aggregate_analysis(enriched)
        insights = await analyzer.base_insights(
            enriched, niche, region, user_profile=user_profile
        )

        # 5. Persist summary + re-fetch for delivery
        async with session_factory() as session:
            await session.execute(
                update(SearchQuery)
                .where(SearchQuery.id == query_id)
                .values(
                    status="done",
                    finished_at=datetime.now(timezone.utc),
                    leads_count=len(all_leads),
                    avg_score=stats.avg_score,
                    hot_leads_count=stats.hot_count,
                    analysis_summary={"insights": insights, "stats": stats.to_dict()},
                )
            )
            await session.commit()

            result = await session.execute(
                select(Lead)
                .where(Lead.query_id == query_id)
                .order_by(
                    Lead.score_ai.desc().nullslast(),
                    Lead.rating.desc().nullslast(),
                )
            )
            final_leads = list(result.scalars().all())

        await _pcall(progress, "finish",
            f"✅ <b>Готово!</b> Нашёл и проанализировал <b>{len(all_leads)}</b> "
            f"компаний, из них 🔥 горячих: <b>{stats.hot_count}</b>. Отчёт ниже 👇"
        )

        # 6. Delivery — through the sink; isolation is the sink's problem.
        await _dcall(delivery, "deliver_stats", niche, region, stats)
        await _dcall(delivery, "deliver_insights", insights)
        await _dcall(delivery, "deliver_top_leads", final_leads)
        await _dcall(delivery, "deliver_excel", final_leads, niche, region)

        # Outbound webhooks. Fire-and-forget; emit_event scopes itself
        # to the running loop and can't surface here.
        for lead_row in final_leads:
            emit_webhook_event(
                user_id,
                "lead.created",
                {
                    "lead": serialize_lead_for_webhook(lead_row),
                    "search_id": str(query_id),
                },
            )
        async with session_factory() as session:
            finished_query = await session.get(SearchQuery, query_id)
            if finished_query is not None:
                emit_webhook_event(
                    user_id,
                    "search.finished",
                    {"search": serialize_search_for_webhook(finished_query)},
                )

        searches_total.labels(status="done").inc()
        search_duration_seconds.observe(time.monotonic() - started_at)

    except GooglePlacesError as exc:
        logger.exception("run_search: google places failed for query %s", query_id)
        searches_total.labels(status="failed").inc()
        async with session_factory() as session:
            await session.execute(
                update(SearchQuery)
                .where(SearchQuery.id == query_id)
                .values(status="failed", error=str(exc)[:1000])
            )
            await session.commit()
            failed_query = await session.get(SearchQuery, query_id)
            if failed_query is not None:
                emit_webhook_event(
                    failed_query.user_id,
                    "search.finished",
                    {"search": serialize_search_for_webhook(failed_query)},
                )
        error_text = (
            "❌ <b>Не удалось выполнить поиск.</b>\n\n"
            f"Google Places API вернул ошибку: <code>{html_escape(str(exc)[:400])}</code>\n\n"
            "Проверь переменные в Railway:\n"
            "• <code>GOOGLE_PLACES_API_KEY</code> задан и не истёк\n"
            "• В Google Cloud Console включён <b>Places API (New)</b>\n"
            "• У ключа есть доступ / квота не исчерпана\n\n"
            "Можно запустить <b>/diag</b> — проверит все интеграции разом."
        )
        await _pcall(progress, "finish", error_text)
    except Exception as exc:  # noqa: BLE001
        logger.exception("run_search: failed for query %s", query_id)
        searches_total.labels(status="failed").inc()
        async with session_factory() as session:
            await session.execute(
                update(SearchQuery)
                .where(SearchQuery.id == query_id)
                .values(status="failed", error=str(exc)[:1000])
            )
            await session.commit()
            failed_query = await session.get(SearchQuery, query_id)
            if failed_query is not None:
                emit_webhook_event(
                    failed_query.user_id,
                    "search.finished",
                    {"search": serialize_search_for_webhook(failed_query)},
                )
        error_text = (
            "❌ <b>Поиск упал на неожиданной ошибке.</b>\n\n"
            f"<code>{html_escape(type(exc).__name__)}: "
            f"{html_escape(str(exc)[:400])}</code>\n\n"
            "Запусти <b>/diag</b> — покажет какой из сервисов сломан."
        )
        await _pcall(progress, "finish", error_text)
    finally:
        logger.info("run_search_with_sinks EXIT query_id=%s", query_id)


# ── Helpers ────────────────────────────────────────────────────────────────

async def _pcall(sink: ProgressSink | None, method: str, *args: Any) -> None:
    """Invoke a ProgressSink method, silently skipping if no sink is bound."""
    if sink is None:
        return
    try:
        await getattr(sink, method)(*args)
    except Exception:  # noqa: BLE001
        logger.exception("progress sink %s(*args) failed", method)


async def _dcall(sink: DeliverySink | None, method: str, *args: Any) -> None:
    """Invoke a DeliverySink method, silently skipping if no sink is bound."""
    if sink is None:
        return
    try:
        await getattr(sink, method)(*args)
    except Exception:  # noqa: BLE001
        logger.exception("delivery sink %s(*args) failed", method)


