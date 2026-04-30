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
from leadgen.config import get_settings
from leadgen.core.services import DeliverySink, ProgressSink
from leadgen.db import Lead, SearchQuery, session_factory
from leadgen.db.models import TeamSeenLead, UserSeenLead
from leadgen.pipeline.enrichment import enrich_leads
from leadgen.utils.metrics import (
    leads_discovered_total,
    leads_persisted_total,
    leads_skipped_total,
    search_duration_seconds,
    searches_total,
)

logger = logging.getLogger(__name__)

SEARCH_TIMEOUT_SEC = 10 * 60


def _has_cyrillic_signal(lead: RawLead) -> bool:
    """True when the place name or address contains Cyrillic glyphs.

    Used as a cheap, high-precision proxy for "this business operates
    in Russian / Ukrainian". Cyrillic in either field on Google Maps
    is essentially never accidental — the owner deliberately wrote
    their name in Cyrillic for that audience. No false-positive risk
    we care about for Slavic-language sales targeting.
    """
    parts = [lead.name or "", lead.address or "", lead.category or ""]
    for piece in parts:
        for char in piece:
            if "Ѐ" <= char <= "ӿ":
                return True
    return False


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
        logger.info(
            "run_search: query loaded niche=%r region=%r user=%s",
            niche,
            region,
            user_id,
        )

        # 1. Discovery
        await _pcall(progress, "phase",
            "🔎 <b>Шаг 1/4: ищу компании в Google Maps</b>",
            "сканирую выдачу · обычно 5–15 секунд",
        )
        user_language = (user_profile or {}).get("language_code") or "en"
        collector = GooglePlacesCollector(language=user_language)
        logger.info("run_search: calling google places search")
        raw_leads: list[RawLead] = await collector.search(niche=niche, region=region)
        logger.info("run_search: google places returned %d leads", len(raw_leads))
        leads_discovered_total.labels(source="google_places").inc(len(raw_leads))
        raw_leads = raw_leads[: get_settings().max_results_per_query]

        # Per-search target language filter — used when a salesperson
        # only works leads in specific languages (e.g. RU/UK on a US
        # market). We use a script-based heuristic on the place name +
        # address: Cyrillic in either field strongly implies Russian /
        # Ukrainian operation. Other languages stay as soft hints
        # passed to Claude (no client-side filter).
        if target_languages:
            slavic_target = any(
                code.lower() in {"ru", "uk", "be", "bg"}
                for code in target_languages
            )
            if slavic_target:
                pre_filter_count = len(raw_leads)
                raw_leads = [
                    lead for lead in raw_leads if _has_cyrillic_signal(lead)
                ]
                logger.info(
                    "run_search: language filter (%s) kept %d/%d leads",
                    target_languages,
                    len(raw_leads),
                    pre_filter_count,
                )
            # Pass to Claude regardless so it can downgrade non-matches
            # the heuristic missed (English-named clinic with Russian
            # reviews etc.).
            if user_profile is None:
                user_profile = {}
            user_profile = {
                **user_profile,
                "target_languages": list(target_languages),
            }

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
        async with session_factory() as session:
            incoming_source_ids = [r.source_id for r in raw_leads if r.source_id]
            already_seen: set[str] = set()
            if not skip_dedup and incoming_source_ids:
                # Personal dedup: things this user has already received.
                if user_id != 0:
                    seen_rows = await session.execute(
                        select(UserSeenLead.source_id)
                        .where(UserSeenLead.user_id == user_id)
                        .where(UserSeenLead.source == "google_places")
                        .where(UserSeenLead.source_id.in_(incoming_source_ids))
                    )
                    already_seen.update(row[0] for row in seen_rows.all())
                # Team dedup: hard rule — if any teammate has seen this
                # place under this team, exclude it. The same lead never
                # appears in two members' CRMs in one team.
                if team_id is not None:
                    team_rows = await session.execute(
                        select(TeamSeenLead.source_id)
                        .where(TeamSeenLead.team_id == team_id)
                        .where(TeamSeenLead.source == "google_places")
                        .where(TeamSeenLead.source_id.in_(incoming_source_ids))
                    )
                    already_seen.update(row[0] for row in team_rows.all())

            batch_seen: set[str] = set()
            rows: list[Lead] = []
            seen_to_insert: list[dict[str, Any]] = []
            duplicates = 0
            for r in raw_leads:
                if not r.source_id or r.source_id in batch_seen:
                    leads_skipped_total.labels(reason="missing_source_id").inc()
                    continue
                if r.source_id in already_seen:
                    duplicates += 1
                    leads_skipped_total.labels(reason="duplicate").inc()
                    continue
                batch_seen.add(r.source_id)
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


