"""Search orchestrator.

End-to-end flow:
  1. Discover leads via Google Places Text Search.
  2. Persist raw leads.
  3. Enrich top-N (websites + reviews + AI analysis).
  4. Aggregate base statistics + ask the LLM for high-level insights.
  5. Deliver everything to the user (stats card, insights, top leads, Excel).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from html import escape as html_escape
from typing import Any

from aiogram import Bot
from aiogram.types import BufferedInputFile
from sqlalchemy import select, update

from leadgen.analysis import AIAnalyzer, BaseStats, aggregate_analysis
from leadgen.collectors import GooglePlacesCollector, RawLead
from leadgen.collectors.google_places import GooglePlacesError
from leadgen.config import get_settings
from leadgen.db import Lead, SearchQuery, session_factory
from leadgen.export.excel import build_excel
from leadgen.pipeline.enrichment import enrich_leads
from leadgen.pipeline.progress import ProgressReporter

logger = logging.getLogger(__name__)


async def run_search(
    query_id: uuid.UUID,
    chat_id: int,
    bot: Bot,
    user_profile: dict[str, Any] | None = None,
) -> None:
    """Execute a lead-generation search and deliver results to the user."""
    logger.info(
        "run_search ENTER query_id=%s chat_id=%s profile=%s",
        query_id,
        chat_id,
        bool(user_profile),
    )
    progress_id: int | None = None
    reporter: ProgressReporter | None = None
    try:
        progress_msg = await bot.send_message(
            chat_id,
            "🚀 <b>Запускаю поиск</b>\n<i>подготовка…</i>",
        )
        progress_id = progress_msg.message_id
        reporter = ProgressReporter(bot, chat_id, progress_id)
        logger.info("run_search: progress message posted id=%s", progress_id)

        async with session_factory() as session:
            query = await session.get(SearchQuery, query_id)
            if query is None:
                logger.error("run_search: query %s not found", query_id)
                return
            query.status = "running"
            await session.commit()
            niche, region = query.niche, query.region
        logger.info(
            "run_search: query loaded niche=%r region=%r", niche, region
        )

        # 1. Discovery
        await reporter.phase(
            "🔎 <b>Шаг 1/4: ищу компании в Google Maps</b>",
            "сканирую выдачу · обычно 5–15 секунд",
        )
        collector = GooglePlacesCollector()
        logger.info("run_search: calling google places search")
        raw_leads: list[RawLead] = await collector.search(niche=niche, region=region)
        logger.info("run_search: google places returned %d leads", len(raw_leads))
        raw_leads = raw_leads[: get_settings().max_results_per_query]

        if not raw_leads:
            await reporter.finish(
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
            return

        # 2. Persist raw leads
        async with session_factory() as session:
            seen: set[str] = set()
            rows: list[Lead] = []
            for r in raw_leads:
                if not r.source_id or r.source_id in seen:
                    continue
                seen.add(r.source_id)
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
            session.add_all(rows)
            await session.commit()

            # Pick top-N for enrichment by Google rating + reviews count
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

        # 3. Enrichment — this is the long phase, show a live progress bar.
        await reporter.phase(
            f"🧠 <b>Шаг 2/4: анализ топ-{enrich_n} компаний</b>",
            "сайт · соцсети · отзывы · AI-оценка под твою услугу",
        )
        await reporter.update(0, enrich_n)
        top_leads = all_leads[:enrich_n]
        enriched = await enrich_leads(
            top_leads,
            collector,
            niche,
            region,
            user_profile=user_profile,
            progress_callback=reporter.update,
        )

        # 4. Aggregation + base insights
        await reporter.phase(
            "📊 <b>Шаг 3/4: сводный отчёт по базе</b>",
            "считаю статистику и формирую AI-инсайты",
        )
        analyzer = AIAnalyzer()
        stats = aggregate_analysis(enriched)
        insights = await analyzer.base_insights(
            enriched, niche, region, user_profile=user_profile
        )

        # 5. Persist summary
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

            # Re-fetch sorted by AI score for delivery
            result = await session.execute(
                select(Lead)
                .where(Lead.query_id == query_id)
                .order_by(
                    Lead.score_ai.desc().nullslast(),
                    Lead.rating.desc().nullslast(),
                )
            )
            final_leads = list(result.scalars().all())

        await reporter.finish(
            f"✅ <b>Готово!</b> Нашёл и проанализировал <b>{len(all_leads)}</b> "
            f"компаний, из них 🔥 горячих: <b>{stats.hot_count}</b>. Отчёт ниже 👇"
        )

        # 6. Delivery
        await _deliver(bot, chat_id, niche, region, final_leads, stats, insights)

    except GooglePlacesError as exc:
        logger.exception("run_search: google places failed for query %s", query_id)
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
        if reporter is not None:
            await reporter.finish(error_text)
        else:
            await bot.send_message(chat_id, error_text)
    except Exception as exc:  # noqa: BLE001
        logger.exception("run_search: failed for query %s", query_id)
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
        try:
            if reporter is not None:
                await reporter.finish(error_text)
            else:
                await bot.send_message(chat_id, error_text)
        except Exception:  # noqa: BLE001
            logger.exception("run_search: failed to notify user")
    finally:
        logger.info("run_search EXIT query_id=%s", query_id)


async def _deliver(
    bot: Bot,
    chat_id: int,
    niche: str,
    region: str,
    leads: list[Lead],
    stats: BaseStats,
    insights: str,
) -> None:
    # 1. Stats card
    stats_block = (
        f"📊 <b>Готово: твоя база лидов собрана</b>\n"
        f"Ниша: <b>{html_escape(niche)}</b>\n"
        f"Регион: <b>{html_escape(region)}</b>\n\n"
        f"Всего компаний: <b>{stats.total}</b>\n"
        f"Проанализировано AI: <b>{stats.enriched}</b>\n"
        f"Средний AI-скор: <b>{stats.avg_score:.0f}/100</b>\n\n"
        f"🔥 Горячих (75+): <b>{stats.hot_count}</b>\n"
        f"🌡 Тёплых (50-74): <b>{stats.warm_count}</b>\n"
        f"❄️ Холодных (&lt;50): <b>{stats.cold_count}</b>\n\n"
        f"С сайтом: <b>{stats.with_website}</b> / {stats.total}\n"
        f"С соцсетями: <b>{stats.with_socials}</b> / {stats.total}\n"
        f"С телефоном: <b>{stats.with_phone}</b> / {stats.total}"
    )
    await bot.send_message(chat_id, stats_block)

    # 2. AI insights over the entire base
    insights_text = html_escape(insights or "—")
    await bot.send_message(chat_id, f"💡 <b>Что это значит для продаж</b>\n\n{insights_text}")

    # 3. Top hot lead cards
    hot_leads = [lead for lead in leads if lead.score_ai is not None][:5]
    if hot_leads:
        await bot.send_message(chat_id, "🔥 <b>Топ-5 горячих лидов</b>")
        for lead in hot_leads:
            await bot.send_message(
                chat_id, _format_lead_card(lead), disable_web_page_preview=True
            )

    # 4. Excel export
    excel_bytes = build_excel(leads)
    filename = _safe_filename(f"leads_{niche}_{region}.xlsx")
    await bot.send_document(
        chat_id,
        document=BufferedInputFile(excel_bytes, filename=filename),
        caption=f"Полная база: {len(leads)} лидов",
    )


def _format_lead_card(lead: Lead) -> str:
    parts: list[str] = []

    score_str = f" — <b>{int(lead.score_ai)}/100</b>" if lead.score_ai is not None else ""
    parts.append(f"<b>{html_escape(lead.name)}</b>{score_str}")

    if lead.tags:
        emoji_map = {"hot": "🔥", "warm": "🌡", "cold": "❄️"}
        badges = "".join(emoji_map.get(t, "") for t in lead.tags if t in emoji_map)
        tags_text = ", ".join(lead.tags)
        prefix = f"{badges} " if badges else ""
        parts.append(f"{prefix}{html_escape(tags_text)}")

    if lead.summary:
        parts.append(f"📝 <i>{html_escape(lead.summary)}</i>")

    details: list[str] = []
    if lead.category:
        details.append(f"🏷 {html_escape(lead.category)}")
    if lead.rating is not None:
        rev = f" ({lead.reviews_count})" if lead.reviews_count else ""
        details.append(f"⭐ {lead.rating}{rev}")
    if details:
        parts.append(" • ".join(details))

    if lead.address:
        parts.append(f"📍 {html_escape(lead.address)}")
    if lead.phone:
        parts.append(f"📞 {html_escape(lead.phone)}")
    if lead.website:
        parts.append(f"🌐 {html_escape(lead.website)}")
    if lead.social_links:
        social_lines = " | ".join(
            f"{k}: {v}" for k, v in lead.social_links.items() if v
        )
        if social_lines:
            parts.append(f"📱 {html_escape(social_lines)}")

    if lead.advice:
        parts.append(f"\n💡 <b>Как зайти:</b> {html_escape(lead.advice)}")

    if lead.weaknesses:
        weak = ", ".join(lead.weaknesses[:3])
        parts.append(f"📉 <b>Точки роста:</b> {html_escape(weak)}")

    if lead.red_flags:
        flags = ", ".join(lead.red_flags[:3])
        parts.append(f"⚠️ <b>Риски:</b> {html_escape(flags)}")

    return "\n".join(parts)


def _safe_filename(name: str) -> str:
    allowed = "-_.() "
    cleaned = "".join(c if c.isalnum() or c in allowed else "_" for c in name)
    return cleaned.replace(" ", "_")
