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

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile
from sqlalchemy import select, update

from leadgen.analysis import AIAnalyzer, BaseStats, aggregate_analysis
from leadgen.collectors import GooglePlacesCollector, RawLead
from leadgen.config import settings
from leadgen.db import Lead, SearchQuery, session_factory
from leadgen.export.excel import build_excel
from leadgen.pipeline.enrichment import enrich_leads

logger = logging.getLogger(__name__)


async def run_search(query_id: uuid.UUID, chat_id: int, bot: Bot) -> None:
    """Execute a lead-generation search and deliver results to the user."""
    progress_id: int | None = None
    try:
        progress_msg = await bot.send_message(
            chat_id, "🔍 Ищу компании в Google Maps..."
        )
        progress_id = progress_msg.message_id

        async with session_factory() as session:
            query = await session.get(SearchQuery, query_id)
            if query is None:
                logger.error("run_search: query %s not found", query_id)
                return
            query.status = "running"
            await session.commit()
            niche, region = query.niche, query.region

        # 1. Discovery
        collector = GooglePlacesCollector()
        raw_leads: list[RawLead] = await collector.search(niche=niche, region=region)

        if not raw_leads:
            await _edit(
                bot,
                chat_id,
                progress_id,
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

        enrich_n = min(settings.max_enrich_leads, len(all_leads))
        await _edit(
            bot,
            chat_id,
            progress_id,
            f"✓ Найдено <b>{len(all_leads)}</b> компаний.\n"
            f"⏳ Анализирую топ-{enrich_n}: сайты, соцсети, отзывы, AI-скоринг...",
        )

        # 3. Enrichment
        top_leads = all_leads[:enrich_n]
        enriched = await enrich_leads(top_leads, collector, niche, region)

        await _edit(
            bot,
            chat_id,
            progress_id,
            f"✓ Проанализировано <b>{len(enriched)}</b> лидов.\n"
            "⏳ Формирую итоговый отчёт по базе...",
        )

        # 4. Aggregation + base insights
        analyzer = AIAnalyzer()
        stats = aggregate_analysis(enriched)
        insights = await analyzer.base_insights(enriched, niche, region)

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

        await _edit(bot, chat_id, progress_id, "✓ Готово!")

        # 6. Delivery
        await _deliver(bot, chat_id, niche, region, final_leads, stats, insights)

    except Exception as exc:  # noqa: BLE001
        logger.exception("run_search: failed for query %s", query_id)
        async with session_factory() as session:
            await session.execute(
                update(SearchQuery)
                .where(SearchQuery.id == query_id)
                .values(status="failed", error=str(exc)[:1000])
            )
            await session.commit()
        try:
            await bot.send_message(
                chat_id,
                f"❌ Не удалось выполнить поиск: {html_escape(str(exc)[:300])}",
            )
        except Exception:  # noqa: BLE001
            logger.exception("run_search: failed to notify user")


async def _edit(bot: Bot, chat_id: int, message_id: int | None, text: str) -> None:
    if message_id is None:
        return
    try:
        await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id)
    except TelegramBadRequest:
        # Message too old or content unchanged — fall back to a fresh message
        try:
            await bot.send_message(chat_id, text)
        except Exception:  # noqa: BLE001
            logger.exception("progress edit fallback failed")


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
        f"📊 <b>Анализ базы</b>\n"
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
    await bot.send_message(chat_id, f"💡 <b>Инсайты по базе</b>\n\n{insights_text}")

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
        socials = " ".join(f"[{k}]" for k in lead.social_links.keys())
        parts.append(f"📱 {html_escape(socials)}")

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
