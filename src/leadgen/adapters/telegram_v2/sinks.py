"""Telegram sinks for run_search_with_sinks."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from leadgen.adapters.telegram_v2 import api as tg

if TYPE_CHECKING:
    from leadgen.db.models import Lead

logger = logging.getLogger(__name__)


class TelegramProgressSink:
    """Sends/edits a progress message in a Telegram chat."""

    def __init__(self, chat_id: int) -> None:
        self.chat_id = chat_id
        self._msg_id: int | None = None

    async def phase(self, title: str, subtitle: str = "") -> None:
        text = f"<b>{title}</b>"
        if subtitle:
            text += f"\n{subtitle}"
        if self._msg_id is None:
            result = await tg.send_message(self.chat_id, text)
            self._msg_id = (result.get("result") or {}).get("message_id")
        else:
            await tg.edit_message_text(self.chat_id, self._msg_id, text)

    async def update(self, done: int, total: int) -> None:
        if total <= 0:
            return
        pct = done * 100 // total
        bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
        text = f"[{bar}] {pct}%"
        if self._msg_id:
            await tg.edit_message_text(self.chat_id, self._msg_id, text)

    async def finish(self, text: str) -> None:
        if self._msg_id:
            await tg.edit_message_text(self.chat_id, self._msg_id, text or "Done.")


class TelegramDeliverySink:
    """Sends search results to a Telegram chat."""

    def __init__(self, chat_id: int) -> None:
        self.chat_id = chat_id
        self._stats_text: str | None = None

    async def deliver_stats(self, niche: str, region: str, stats: Any) -> None:
        total = getattr(stats, "total", "?")
        scored = getattr(stats, "scored", "?")
        self._stats_text = (
            f"<b>Search complete</b>\n"
            f"Niche: {niche} | Region: {region}\n"
            f"Found: {total} leads, {scored} AI-scored"
        )

    async def deliver_insights(self, insights: str) -> None:
        if insights:
            snippet = insights[:500] + ("…" if len(insights) > 500 else "")
            await tg.send_message(self.chat_id, f"<b>AI Insights</b>\n{snippet}")

    async def deliver_top_leads(self, leads: list[Lead]) -> None:
        if not leads:
            await tg.send_message(self.chat_id, "No leads found for this search.")
            return
        if self._stats_text:
            await tg.send_message(self.chat_id, self._stats_text)
        lines = ["<b>Top leads:</b>"]
        for i, lead in enumerate(leads[:5], 1):
            score = f" | Score: {lead.score_ai}/100" if lead.score_ai else ""
            phone = f" | {lead.phone}" if lead.phone else ""
            website = f"\n  {lead.website}" if lead.website else ""
            lines.append(f"{i}. <b>{lead.name}</b>{score}{phone}{website}")
        await tg.send_message(self.chat_id, "\n".join(lines))

    async def deliver_excel(self, leads: list[Lead], niche: str, region: str) -> None:
        # Telegram doesn't support inline Excel; skip. Leads are accessible in the web CRM.
        pass
