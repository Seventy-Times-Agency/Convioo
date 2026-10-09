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

from sqlalchemy import func, select, update

from leadgen.analysis import AIAnalyzer, aggregate_analysis
from leadgen.collectors import GooglePlacesCollector, RawLead
from leadgen.collectors.adzuna import search_hiring_companies
from leadgen.collectors.companies_house import search_new_businesses
from leadgen.collectors.google_places import GooglePlacesError
from leadgen.collectors.osm import discover_with_lock
from leadgen.config import get_settings
from leadgen.core.services import DeliverySink, ProgressSink, usage_tracker
from leadgen.core.services.integrations.webhooks import (
    emit_event as emit_webhook_event,
)
from leadgen.core.services.integrations.webhooks import (
    serialize_lead as serialize_lead_for_webhook,
)
from leadgen.core.services.integrations.webhooks import (
    serialize_search as serialize_search_for_webhook,
)
from leadgen.core.services.search import coverage as _coverage
from leadgen.core.services.search.search_cache import (
    cached_collector_run,
    make_geo_key,
)
from leadgen.core.services.search.tariff_limits import (
    check_daily_lead_quota,
    record_lead_usage,
)
from leadgen.data.cities import match_city
from leadgen.data.niches import match_niche
from leadgen.db import Lead, SearchQuery, session_factory
from leadgen.db.models import TeamSeenLead, User, UserSeenLead
from leadgen.integrations.slack import send_slack_notification
from leadgen.pipeline.enrichment import enrich_leads
from leadgen.pipeline.screening import Screen
from leadgen.utils.geocode import bbox_from_circle, geocode_region_dedup
from leadgen.utils.metrics import (
    leads_discovered_total,
    leads_persisted_total,
    search_duration_seconds,
    searches_total,
)

logger = logging.getLogger(__name__)

# Воронка запуска (сколько найдено, дублей, отсеяно, выдано) — копится
# по ходу поиска и забирается общим финалом запуска (finish_search_run),
# который пишет её в search_queries.economics вместе с расходами.
FUNNELS: dict[uuid.UUID, dict[str, int]] = {}

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


async def _fsq_search(
    *,
    niche: str,
    region: str,
    fsq_categories: list[str],
    bbox: tuple[float, float, float, float] | None,
    api_key: str,
    limit: int,
) -> list[RawLead]:
    """Run a Foursquare search; same fail-soft contract as ``_yelp_search``."""
    from leadgen.collectors.foursquare import FoursquareCollector, FoursquareError

    try:
        async with FoursquareCollector(
            api_key, max_results=limit
        ) as client:
            return await client.search(
                niche=niche,
                region=region,
                fsq_categories=fsq_categories,
                bbox=bbox,
            )
    except FoursquareError as exc:
        logger.warning("foursquare branch disabled this run: %s", exc)
        return []


async def _adzuna_search(niche: str, region: str, limit: int) -> list[RawLead]:
    """Fail-soft Adzuna wrapper — returns empty list on any error."""
    try:
        raw_dicts = await search_hiring_companies(niche=niche, region=region, limit=limit)
        return [
            RawLead(
                source=d["source"],
                source_id=d["source_id"],
                name=d["name"],
                website=d.get("website"),
                phone=d.get("phone"),
                address=d.get("address"),
                category=d.get("category"),
                rating=d.get("rating"),
                reviews_count=d.get("reviews_count"),
                latitude=d.get("latitude"),
                longitude=d.get("longitude"),
                raw=d.get("raw", {}),
                tags=d.get("tags"),
            )
            for d in raw_dicts
        ]
    except Exception:
        logger.warning("adzuna branch disabled this run", exc_info=True)
        return []


async def _companies_house_search(niche: str, region: str, limit: int) -> list:
    """Fail-soft Companies House wrapper."""
    try:
        raw_dicts = await search_new_businesses(niche=niche, region=region, limit=limit)
        return [
            RawLead(
                source=d["source"],
                source_id=d["source_id"],
                name=d["name"],
                website=d.get("website"),
                phone=d.get("phone"),
                address=d.get("address"),
                category=d.get("category"),
                rating=d.get("rating"),
                reviews_count=d.get("reviews_count"),
                latitude=d.get("latitude"),
                longitude=d.get("longitude"),
                raw=d.get("raw", {}),
                tags=d.get("tags"),
            )
            for d in raw_dicts
        ]
    except Exception:
        logger.warning("companies_house branch disabled this run", exc_info=True)
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
    target_languages: list[str], country_code: str | None = None
) -> tuple[str, str | None]:
    """Pick (languageCode, regionCode) for the Google Places call.

    Language: the first target language if the user asked for one,
    otherwise English (English-first, never the UI language). Region:
    the picked city's country; only free-text cities without a country
    fall back to the language's home country (DE → DE, UK → UA).
    """
    primary = target_languages[0].lower() if target_languages else None
    region = (country_code or "").upper() or None
    if region is None and primary:
        region = _LANGUAGE_REGION_HINT.get(primary) or None
    if region == "RU":
        region = None  # project policy: never bias toward RU
    return primary or "en", region


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
        await _salvage_partial(query_id)




async def _salvage_partial(query_id: uuid.UUID) -> int:
    """Запуск упал на середине — отдать то, что уже готово.

    Обогащение пишет лиды порциями, поэтому после сбоя часть уже
    оценена. Такой запуск закрывается как «готово» с пометкой о сбое:
    оценённые лиды выдаются и списываются, неоценённые остаются в
    выдаче бесплатно (они уже помечены «видели» — иначе пропали бы
    навсегда). Возвращает число выданных; 0 — выдавать нечего.
    """
    try:
        async with session_factory() as session:
            query = await session.get(SearchQuery, query_id)
            if query is None:
                return 0
            total = int(
                (
                    await session.execute(
                        select(func.count(Lead.id)).where(Lead.query_id == query_id)
                    )
                ).scalar_one()
            )
            if total == 0:
                return 0
            enriched_n = int(
                (
                    await session.execute(
                        select(func.count(Lead.id))
                        .where(Lead.query_id == query_id)
                        .where(Lead.enriched.is_(True))
                    )
                ).scalar_one()
            )
            query.status = "done"
            query.leads_count = total
            query.finished_at = datetime.now(timezone.utc)
            query.error = (
                f"partial: stopped after {enriched_n} of {total} analyzed — "
                f"{query.error or 'unexpected error'}"
            )[:1000]
            if query.team_id is not None:
                from leadgen.core.services.account import tokens as _tokens

                await _tokens.settle(
                    session,
                    query.team_id,
                    query_id,
                    actual_leads=enriched_n,
                    find_decision_makers=False,
                    reason=f"поиск прерван: {query.niche}, {query.region} — {enriched_n} готовых лидов",
                )
            await session.commit()
        funnel = FUNNELS.setdefault(query_id, {})
        funnel["delivered"] = total
        return total
    except Exception:  # noqa: BLE001 — спасение не должно ронять финал
        logger.exception("partial salvage failed for %s", query_id)
        return 0


def _passes_prefilters(lead: RawLead, pf: dict[str, Any]) -> bool:
    website = (getattr(lead, "website", None) or "").strip()
    mode = pf.get("website")
    if mode == "with" and not website:
        return False
    if mode == "without" and website:
        return False
    min_rating = pf.get("min_rating")
    rating = getattr(lead, "rating", None)
    if min_rating and rating is not None and rating < float(min_rating):
        return False
    min_reviews = pf.get("min_reviews")
    reviews = getattr(lead, "reviews_count", None)
    return not (min_reviews and reviews is not None and reviews < int(min_reviews))


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
            prefilters: dict[str, Any] = dict(query.prefilters or {})
            scope = (query.scope or "city").lower()
            radius_m = query.radius_m
            cached_lat = query.center_lat
            cached_lon = query.center_lon
            # Per-search source override (T6). None = honour env flags.
            enabled_sources_override: set[str] | None = (
                {s.lower() for s in (query.enabled_sources or [])}
                or None
            )
            # Pick the quota subject. Team-mode searches share the
            # workspace bucket (and the workspace plan); personal
            # searches stay on the individual's plan. Platform admins
            # always bypass — owner accounts shouldn't trip on their
            # own quota during testing.
            plan_user = await session.get(User, user_id) if user_id else None
            user_is_admin = bool(getattr(plan_user, "is_admin", False))
            if team_id is not None:
                from leadgen.db.models import Team as _Team

                team_row = await session.get(_Team, team_id)
                quota_plan = (
                    team_row.plan if team_row and team_row.plan else "free"
                )
                quota_team_id = str(team_id)
            else:
                quota_plan = (plan_user.plan if plan_user else None) or "free"
                quota_team_id = None
        logger.info(
            "run_search: query loaded niche=%r region=%r scope=%s radius_m=%s user=%s",
            niche,
            region,
            scope,
            radius_m,
            user_id,
        )

        # Bind the run to a user-id ContextVar so collectors and the
        # AI scorer can record their billable units against the right
        # tenant without passing user_id through every signature. The
        # token is reset in the ``finally`` of run_search_with_timeout
        # — see that function for the cleanup.
        _usage_token = usage_tracker.set_active_user(user_id)
        # Каждая трата дальше — этого поиска и команды (журнал трат).
        usage_tracker.bind_search(query_id, query.team_id)
        usage_tracker.set_stage("discovery")
        funnel = FUNNELS.setdefault(query_id, {})

        # Daily lead-volume guard — independent of the legacy monthly
        # search counter in BillingService. A user on plan ``solo``
        # may only see 100 leads/24h regardless of how many search
        # credits they've got left. We pre-check with the requested
        # ``per_search_limit`` so a single huge search can't slip
        # past a near-cap user. ``user_id == 0`` is the unauth /
        # debug path and stays unrestricted.
        if user_id and user_id != 0:
            quota = await check_daily_lead_quota(
                user_id,
                quota_plan,
                requested=per_search_limit or 50,
                is_admin=user_is_admin,
                team_id=quota_team_id,
            )
            if not quota.allowed:
                logger.info(
                    "run_search: tariff cap hit user=%s plan=%s used=%d cap=%d",
                    user_id,
                    quota.plan,
                    quota.used_24h,
                    quota.cap_24h,
                )
                async with session_factory() as _sess:
                    await _sess.execute(
                        update(SearchQuery)
                        .where(SearchQuery.id == query_id)
                        .values(
                            status="failed",
                            error=(
                                f"Daily limit on plan '{quota.plan}' reached "
                                f"({quota.used_24h}/{quota.cap_24h} leads in last 24h). "
                                f"Try again later or upgrade."
                            )[:1000],
                        )
                    )
                    await _sess.commit()
                searches_total.labels(status="failed").inc()
                await _pcall(
                    progress,
                    "finish",
                    (
                        "⛔ <b>Daily limit reached</b>\n\n"
                        f"Plan <code>{quota.plan}</code>: "
                        f"{quota.used_24h}/{quota.cap_24h} leads in the last 24 hours.\n"
                        "Wait or upgrade your plan to continue."
                    ),
                )
                return

        # 1. Discovery — Google Places + (optional) OSM in parallel.
        await _pcall(progress, "phase",
            "🔎 <b>Step 1/4: finding companies in Google Maps + OSM</b>",
            "scanning results · usually 5-15 seconds",
        )
        language_code, region_code = _collector_locale(
            target_languages, query.country_code
        )
        # Демо-режим: ключа Google нет и он не нужен — муляж парсера
        # подставляется ниже, а enrich_leads в демо не трогает
        # коллектор вовсе.
        collector = (
            None
            if get_settings().demo_active
            else GooglePlacesCollector(
                language=language_code,
                region_code=region_code,
            )
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
                # Демо-режим: без сети — геокодинг не нужен, муляж
                # парсера сам подставит адреса региона.
                geo = (
                    None
                    if get_settings().demo_active
                    else await geocode_region_dedup(region)
                )
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
        demo_run = get_settings().demo_active

        def _source_active(name: str, env_active: bool) -> bool:
            # Демо-режим: единственный «источник» — муляж вместо
            # Google; остальные коллекторы в сеть не ходят.
            if demo_run:
                return name == "google"
            if enabled_sources_override is not None:
                return name in enabled_sources_override
            return env_active

        # Срезы карты (весь город, его части, другие формулировки) и
        # память о прочёсанном: идём только в нетронутые за 30 дней.
        skip_dedup = user_id == 0 and team_id is None
        use_coverage = not demo_run and not skip_dedup
        cov_scope = _coverage.scope_key(team_id, user_id)
        cov_niche = _coverage.niche_key(niche)
        cov_region = _coverage.norm(region)
        tile_bbox = (
            bbox_from_circle(center_lat, center_lon, _coverage.DEFAULT_TILE_RADIUS_M)
            if bbox is None and center_lat is not None and center_lon is not None
            else None
        )
        slices = _coverage.build_slices(niche, niche_entry, language_code, bbox, tile_bbox)
        if use_coverage:
            async with session_factory() as session:
                done_slices = await _coverage.covered(session, cov_scope, cov_niche, cov_region)
            pending_slices = [sl for sl in slices if sl.key not in done_slices]
        else:
            pending_slices = list(slices)
        first_slice = pending_slices[0] if pending_slices else None
        if first_slice is None:
            funnel["exhausted"] = 1

        if demo_run:
            from leadgen.collectors.mock import demo_leads as _demo_leads

            async def _demo_task() -> list[RawLead]:
                return _demo_leads(
                    niche, region, per_search_limit or 20
                )

            google_task = _demo_task()
        elif _source_active("google", True) and first_slice is not None:
            google_task = collector.search(
                niche=first_slice.query,
                region=region,
                location_restriction_bbox=first_slice.bbox,
            )
        else:
            google_task = _empty_leads()

        if (
            osm_tags
            and _source_active("osm", get_settings().osm_enabled)
        ):
            _osm_key = make_geo_key(
                niche=niche,
                region=region,
                bbox=bbox,
                extras={
                    "tags": osm_tags,
                    "limit": get_settings().max_results_per_query,
                },
            )
            osm_task = cached_collector_run(
                source="osm",
                key=_osm_key,
                fetcher=lambda: discover_with_lock(
                    niche=niche,
                    region=region,
                    osm_tags=osm_tags,
                    limit=get_settings().max_results_per_query,
                    bbox=bbox,
                ),
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
            _yelp_key = make_geo_key(
                niche=niche,
                region=region,
                bbox=bbox,
                extras={"cats": yelp_categories},
            )
            yelp_task = cached_collector_run(
                source="yelp",
                key=_yelp_key,
                fetcher=lambda: _yelp_search(
                    niche=niche,
                    region=region,
                    yelp_categories=yelp_categories,
                    bbox=bbox,
                    api_key=yelp_settings.yelp_api_key,
                    limit=get_settings().max_results_per_query,
                ),
            )
        else:
            yelp_task = _empty_leads()

        # Foursquare Places — same opt-in pattern as Yelp.
        fsq_categories = (
            list(niche_entry.fsq_categories) if niche_entry else []
        )
        fsq_settings = get_settings()
        if (
            fsq_categories
            and fsq_settings.fsq_enabled
            and fsq_settings.fsq_api_key
        ):
            _fsq_key = make_geo_key(
                niche=niche,
                region=region,
                bbox=bbox,
                extras={"cats": fsq_categories},
            )
            fsq_task = cached_collector_run(
                source="foursquare",
                key=_fsq_key,
                fetcher=lambda: _fsq_search(
                    niche=niche,
                    region=region,
                    fsq_categories=fsq_categories,
                    bbox=bbox,
                    api_key=fsq_settings.fsq_api_key,
                    limit=get_settings().max_results_per_query,
                ),
            )
        else:
            fsq_task = _empty_leads()

        adzuna_settings = get_settings()
        if _source_active("adzuna", adzuna_settings.adzuna_enabled) and adzuna_settings.adzuna_app_id:
            adzuna_task = _adzuna_search(
                niche=niche,
                region=region,
                limit=get_settings().max_results_per_query,
            )
        else:
            adzuna_task = _empty_leads()

        ch_settings = get_settings()
        _is_uk = any(kw in region.lower() for kw in ("uk", "united kingdom", "england", "london", "manchester", "birmingham"))
        if _source_active("companies_house", ch_settings.companies_house_enabled) and _is_uk:
            ch_task = _companies_house_search(
                niche=niche,
                region=region,
                limit=get_settings().max_results_per_query,
            )
        else:
            ch_task = _empty_leads()

        # Two-tier discovery to protect Yelp + Foursquare's tiny daily
        # quotas (5k/950 free). Tier 1: cheap-and-fast — Google + OSM
        # + the niche-specific specialty sources. Tier 2: paid backups
        # Yelp + FSQ only when tier 1 is short on results. The
        # FALLBACK_SOURCES_ALWAYS_ON flag restores the legacy single
        # gather() for tenants who'd rather burn quota than miss rows.
        _runtime_settings = get_settings()
        if _runtime_settings.fallback_sources_always_on:
            (
                google_leads,
                osm_leads,
                yelp_leads,
                fsq_leads,
                adzuna_leads,
                ch_leads,
            ) = await asyncio.gather(
                google_task,
                osm_task,
                yelp_task,
                fsq_task,
                adzuna_task,
                ch_task,
                return_exceptions=False,
            )
        else:
            (
                google_leads,
                osm_leads,
                adzuna_leads,
                ch_leads,
            ) = await asyncio.gather(
                google_task, osm_task, adzuna_task, ch_task, return_exceptions=False
            )
            tier1_count = len(google_leads) + len(osm_leads)
            if tier1_count < _runtime_settings.fallback_min_leads:
                logger.info(
                    "run_search: tier1=%d < %d, activating yelp/fsq fallback",
                    tier1_count,
                    _runtime_settings.fallback_min_leads,
                )
                yelp_leads, fsq_leads = await asyncio.gather(
                    yelp_task, fsq_task, return_exceptions=False
                )
            else:
                logger.info(
                    "run_search: tier1=%d >= %d, skipping yelp/fsq (quota saved)",
                    tier1_count,
                    _runtime_settings.fallback_min_leads,
                )
                # Cancel the prebuilt coroutines so the collectors don't
                # actually fire — they're cold awaitables right now.
                yelp_task.close() if hasattr(yelp_task, "close") else None
                fsq_task.close() if hasattr(fsq_task, "close") else None
                yelp_leads = []
                fsq_leads = []
        logger.info(
            "run_search: google=%d osm=%d yelp=%d fsq=%d adzuna=%d ch=%d "
            "(tags=%s, yelp=%s, fsq=%s)",
            len(google_leads),
            len(osm_leads),
            len(yelp_leads),
            len(fsq_leads),
            len(adzuna_leads),
            len(ch_leads),
            osm_tags,
            yelp_categories,
            fsq_categories,
        )
        leads_discovered_total.labels(source="google_places").inc(len(google_leads))
        leads_discovered_total.labels(source="osm").inc(len(osm_leads))
        leads_discovered_total.labels(source="yelp").inc(len(yelp_leads))
        leads_discovered_total.labels(source="foursquare").inc(len(fsq_leads))
        leads_discovered_total.labels(source="adzuna").inc(len(adzuna_leads))
        leads_discovered_total.labels(source="companies_house").inc(len(ch_leads))

        if target_languages:
            user_profile = {
                **(user_profile or {}),
                "target_languages": list(target_languages),
            }
        exclusions = (prefilters or {}).get("exclude")
        cap = per_search_limit or get_settings().max_results_per_query
        cap = max(1, min(cap, get_settings().max_results_per_query, 100))

        async def _triage(batch: list[RawLead]) -> set[int]:
            from leadgen.analysis.triage import quick_exclude

            return await quick_exclude(batch, niche=niche, exclusions=str(exclusions))

        # Отбор: фильтры «до оценки» (сайт / рейтинг / отзывы; лиды без
        # данных проходят), язык, «без контактов», дубли по всем
        # источникам, быстрый отсев ИИ по «кого не нужно». Лимит —
        # потом, по свежим: раньше дубли съедали заказанное.
        screen = Screen(
            funnel=funnel,
            user_id=user_id,
            team_id=team_id,
            skip_dedup=skip_dedup,
            passes_prefilters=(lambda r: _passes_prefilters(r, prefilters)) if prefilters else None,
            passes_language=(
                (lambda r: _passes_language_filter(r, target_languages)) if target_languages else None
            ),
            triage=_triage if exclusions and not demo_run else None,
        )
        slice_log: list[tuple[str, int, int]] = []
        google_fresh = await screen.add(list(google_leads))
        if first_slice is not None and collector is not None:
            slice_log.append((first_slice.key, len(google_leads), google_fresh))
        await screen.add(
            list(osm_leads) + list(yelp_leads) + list(fsq_leads) + list(adzuna_leads) + list(ch_leads)
        )

        # Досбор до заказанного: следующие нетронутые срезы, пока не
        # наберём или пока два среза подряд не дадут почти одни дубли.
        if collector is not None and not demo_run and _source_active("google", True):
            low_streak = 0
            backfill = pending_slices[1:]
            for n, sl in enumerate(backfill):
                if len(screen.fresh) >= cap:
                    break
                await _pcall(progress, "phase",
                    "🔎 <b>Step 1/4: looking for more new companies</b>",
                    f"{len(screen.fresh)} of {cap} new so far · next district or wording",
                )
                try:
                    got = await collector.search(
                        niche=sl.query, region=region, location_restriction_bbox=sl.bbox
                    )
                except GooglePlacesError:
                    logger.warning("run_search: backfill slice %s failed", sl.key, exc_info=True)
                    break
                added = await screen.add(list(got))
                slice_log.append((sl.key, len(got), added))
                low_streak = low_streak + 1 if added < _coverage.LOW_YIELD else 0
                if low_streak >= _coverage.LOW_YIELD_STREAK:
                    funnel["exhausted"] = 1
                    break
                if n == len(backfill) - 1 and len(screen.fresh) < cap:
                    funnel["exhausted"] = 1
            if not backfill and len(screen.fresh) < cap:
                funnel["exhausted"] = 1
            funnel["slices"] = len(slice_log)

        funnel["over_limit"] = max(0, len(screen.fresh) - cap)
        if use_coverage and slice_log:
            # Срез, из которого остались свежие сверх лимита, не
            # помечаем пройденным — в следующий раз они всплывут.
            to_record = slice_log[:-1] if funnel["over_limit"] else slice_log
            async with session_factory() as session:
                for key, found_n, fresh_n in to_record:
                    await _coverage.record(
                        session, cov_scope, cov_niche, cov_region, key, found=found_n, fresh=fresh_n
                    )
                if funnel.get("exhausted"):
                    await _coverage.record(
                        session, cov_scope, cov_niche, cov_region, _coverage.EXHAUSTED_KEY,
                        found=0, fresh=0,
                    )
                else:
                    await _coverage.clear_exhausted(session, cov_scope, cov_niche, cov_region)
                await session.commit()

        if not screen.fresh:
            duplicates = funnel.get("duplicates", 0)
            await _pcall(progress, "finish",
                (
                    f"All {duplicates} companies for this query were already delivered to you. "
                    "This niche in this city looks exhausted — try a neighbouring city or a wider radius."
                )
                if duplicates
                else (
                    f"Nothing found for «{html_escape(niche)} — {html_escape(region)}».\n"
                    "Try a different wording or a larger region."
                ),
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

        # 2. Persist. The synthetic web-demo user (id=0) is shared by
        # every visitor of the open demo — no seen-leads memory for it.
        async with session_factory() as session:
            fresh = screen.fresh
            duplicates = funnel.get("duplicates", 0)
            # Лимит — по свежим. Первыми идут те, у кого больше данных
            # для оценки и способов связаться. Лишние сверх лимита не
            # помечаются «уже видели» и всплывут в следующем запуске.
            fresh.sort(
                key=lambda item: (
                    bool(item[0].website),
                    bool(item[0].phone),
                    item[0].reviews_count or 0,
                ),
                reverse=True,
            )
            funnel["over_limit"] = max(0, len(fresh) - cap)
            fresh = fresh[:cap]

            rows: list[Lead] = []
            seen_to_insert: list[dict[str, Any]] = []
            for r, phone_key, domain_key in fresh:
                initial_snapshots = None
                if r.rating is not None:
                    initial_snapshots = [
                        {
                            "date": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                            "rating": r.rating,
                            "reviews_count": r.reviews_count,
                        }
                    ]
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
                        rating_snapshots=initial_snapshots,
                        tags=r.tags or None,
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

            # Отсеянные быстрым ИИ тоже «уже видели» — второй раз за
            # них не платим.
            for r, phone_key, domain_key in screen.rejected:
                seen_to_insert.append(
                    {
                        "user_id": user_id,
                        "source": r.source,
                        "source_id": r.source_id,
                        "phone_e164": phone_key,
                        "domain_root": domain_key,
                    }
                )

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
            f"🧠 <b>Step 2/4: analyzing top {enrich_n} companies</b>",
            "website · socials · reviews · AI scoring for your service",
        )
        await _pcall(progress, "update", 0, enrich_n)
        top_leads = all_leads[:enrich_n]
        exclusions = (prefilters or {}).get("exclude")
        if exclusions:
            user_profile = {**(user_profile or {}), "exclusions": exclusions}
        enriched = await enrich_leads(
            top_leads,
            collector,
            niche,
            region,
            user_profile=user_profile,
            progress_callback=(progress.update if progress is not None else None),
            # NULL на старых строках означает «искали» — так поле не
            # переосмысливает поведение поисков, созданных до него.
            find_decision_makers=(
                query.find_decision_makers is not False
            ),
        )

        # Send Slack notifications for hot leads
        for item in enriched:
            if item.get("score_ai", 0) >= 80:
                send_slack_notification(
                    f"Hot lead found: {item.get('name', 'Unknown')} - score {item.get('score_ai', 0):.0f}"
                )

        # 4. Aggregation + base insights
        await _pcall(progress, "phase",
            "📊 <b>Step 3/4: summary report across the base</b>",
            "computing stats and generating AI insights",
        )
        analyzer = AIAnalyzer()
        stats = aggregate_analysis(enriched)
        usage_tracker.set_stage("insights")
        insights = await analyzer.base_insights(
            enriched, niche, region, user_profile=user_profile
        )

        # 5. Persist summary + re-fetch for delivery
        delivered_n = len(all_leads)
        if exclusions:
            # Исключённые ИИ компании удалены при оценке — считаем и
            # списываем только тех, кто остался в выдаче.
            async with session_factory() as session:
                delivered_n = int(
                    (
                        await session.execute(
                            select(func.count(Lead.id)).where(Lead.query_id == query_id)
                        )
                    ).scalar_one()
                )
        funnel["excluded"] = max(0, len(all_leads) - delivered_n)
        funnel["delivered"] = delivered_n
        dm_found = sum(1 for item in enriched if item.get("decision_maker"))
        if query.find_decision_makers is True:
            funnel["decision_makers"] = dm_found
        async with session_factory() as session:
            await session.execute(
                update(SearchQuery)
                .where(SearchQuery.id == query_id)
                .values(
                    status="done",
                    finished_at=datetime.now(timezone.utc),
                    leads_count=delivered_n,
                    avg_score=stats.avg_score,
                    hot_leads_count=stats.hot_count,
                    analysis_summary={"insights": insights, "stats": stats.to_dict()},
                )
            )
            # Закрываем резерв по факту: списываем за доставленных
            # лидов, остаток возвращаем. Поиск почти всегда приносит
            # меньше заказанного — списание вперёд означало бы брать
            # за лидов, которых команда не получила.
            if query.team_id is not None:
                from leadgen.core.services.account import tokens as _tokens

                try:
                    await _tokens.settle(
                        session,
                        query.team_id,
                        query_id,
                        actual_leads=delivered_n,
                        find_decision_makers=(
                            query.find_decision_makers is True
                        ),
                        decision_makers=dm_found,
                        reason=(
                            f"поиск: {query.niche}, {query.region} — "
                            f"{delivered_n} лидов"
                        ),
                    )
                except Exception:  # noqa: BLE001
                    # Учёт не должен ронять доставку результата: лиды
                    # уже собраны и оплачены платформой. Расхождение
                    # видно по журналу и правится adjust.
                    logger.warning(
                        "tokens.settle failed for search %s",
                        query_id,
                        exc_info=True,
                    )
                # Системная строка журнала: «добыча завершена».
                from leadgen.core.services.account import team_journal
                from leadgen.db.models.journal import JK_SEARCH_FINISHED

                await team_journal.record(
                    session,
                    query.team_id,
                    JK_SEARCH_FINISHED,
                    payload={
                        "leads": delivered_n,
                        "tokens": _tokens.quote(
                            delivered_n,
                            find_decision_makers=query.find_decision_makers is True,
                            decision_makers=dm_found,
                        ).total,
                        "niche": query.niche,
                        "region": query.region,
                    },
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
            f"✅ <b>Done!</b> Found and analyzed <b>{delivered_n}</b> "
            f"companies, 🔥 hot among them: <b>{stats.hot_count}</b>. Report below 👇"
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

        # Google Sheets sink — append enriched leads if user has configured it
        if enriched and user_id != 0:
            try:
                from leadgen.db import User as _User
                from leadgen.integrations.sheets import append_leads_to_sheet

                async with session_factory() as _sess:
                    _user = await _sess.get(_User, user_id)
                    _sheet_id = getattr(_user, "google_sheets_spreadsheet_id", None) if _user else None

                if _sheet_id:
                    await append_leads_to_sheet(_sheet_id, enriched)
            except Exception:
                logger.warning("run_search: sheets sink failed", exc_info=True)

        # Bump the daily lead-volume window with what we actually
        # delivered — partial-result searches don't get charged the
        # full ``per_search_limit``.
        if user_id and user_id != 0:
            await record_lead_usage(
                user_id,
                len(enriched or []),
                team_id=quota_team_id,
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
        salvaged = await _salvage_partial(query_id)
        error_text = (
            "❌ <b>Search failed.</b>\n\n"
            f"Google Places API returned an error: <code>{html_escape(str(exc)[:400])}</code>\n\n"
            "Check the variables in Railway:\n"
            "• <code>GOOGLE_PLACES_API_KEY</code> is set and not expired\n"
            "• <b>Places API (New)</b> is enabled in Google Cloud Console\n"
            "• the key has access / quota is not exhausted\n\n"
            "You can run <b>/diag</b> to check all integrations at once."
        )
        if salvaged:
            error_text = _partial_text(salvaged)
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
        salvaged = await _salvage_partial(query_id)
        error_text = (
            "❌ <b>Search crashed on an unexpected error.</b>\n\n"
            f"<code>{html_escape(type(exc).__name__)}: "
            f"{html_escape(str(exc)[:400])}</code>\n\n"
            "Run <b>/diag</b> to see which service is broken."
        )
        if salvaged:
            error_text = _partial_text(salvaged)
        await _pcall(progress, "finish", error_text)
    finally:
        # Always release the usage-tracker context binding, even on
        # error. ``_usage_token`` is only defined after the SearchQuery
        # row was loaded; guard with ``locals()`` so an early failure
        # in the load doesn't trigger a NameError here.
        _token = locals().get("_usage_token")
        if _token is not None:
            usage_tracker.reset_active_user(_token)
        logger.info("run_search_with_sinks EXIT query_id=%s", query_id)


# ── Helpers ────────────────────────────────────────────────────────────────

def _partial_text(n: int) -> str:
    return (
        f"⚠️ <b>Search stopped on an error</b>, but <b>{n}</b> companies were "
        "already found — they are in your results. Only analyzed ones are charged."
    )


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


