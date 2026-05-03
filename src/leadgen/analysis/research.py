"""Per-lead deep research mixins (decision makers, outreach signals)."""

from __future__ import annotations

import logging
from typing import Any

from leadgen.analysis._helpers import _extract_json, _trim_or_none
from leadgen.analysis.prompts import _format_user_profile
from leadgen.collectors.website import WebsiteCollector

logger = logging.getLogger(__name__)


class ResearchMixin:
    async def extract_decision_makers(
        self,
        website_url: str,
    ) -> list[dict[str, Any]]:
        if not website_url or self.client is None:
            return []
        try:
            async with WebsiteCollector() as collector:
                info = await collector.fetch(website_url)
        except Exception:  # noqa: BLE001
            logger.exception(
                "extract_decision_makers: site fetch failed %s", website_url
            )
            return []
        if not info.ok or not info.main_text:
            return []

        site_excerpt = (info.main_text or "")[:8000]
        emails_seen = ", ".join(info.emails[:10]) or "—"
        socials = ", ".join(
            f"{k}: {v}" for k, v in (info.social_links or {}).items()
        )
        meta_block_lines = []
        if info.title:
            meta_block_lines.append(f"Title: {info.title}")
        if info.description:
            meta_block_lines.append(f"Meta: {info.description}")
        meta_block_lines.append(f"Emails on page: {emails_seen}")
        if socials:
            meta_block_lines.append(f"Social links: {socials}")
        meta_block = "\n".join(meta_block_lines)

        system = (
            "Ты — research-аналитик для B2B sales. Извлеки из текста "
            "сайта людей-лиц, принимающих решение (founder, CEO, "
            "CMO, head of sales, owner). Каждому укажи name, role, "
            "email, linkedin когда есть. Цели: дать продажнику "
            "конкретное имя для первой строки cold-email и для "
            "follow-up.\n\n"
            "Жёсткие правила:\n"
            "- НЕ выдумывай. Если на странице нет имени — пропусти "
            "запись. Лучше 1 надёжный контакт, чем 4 угаданных.\n"
            "- email только если он явно написан на странице или "
            "следует из доменного шаблона ([email protected]).\n"
            "- linkedin — только когда есть реальная ссылка.\n"
            "- role короткая (1-3 слова): Founder / CEO / Head of "
            "Marketing.\n"
            "- Максимум 4 человека. Один человек = одна запись.\n\n"
            "Формат ответа — СТРОГО JSON без markdown:\n"
            '{"people": [{"name": "…", "role": "…|null", '
            '"email": "…|null", "linkedin": "…|null"}, ...]}'
        )

        user_msg_parts: list[str] = []
        if meta_block:
            user_msg_parts.append(meta_block)
        user_msg_parts.append(f"Page text:\n{site_excerpt}")
        user_msg = "\n\n".join(user_msg_parts)

        try:
            async with self._sem:
                msg = await self.client.messages.create(
                    model=self.model,
                    max_tokens=600,
                    system=system,
                    messages=[{"role": "user", "content": user_msg}],
                )
                raw = msg.content[0].text  # type: ignore[union-attr]
                data = _extract_json(raw) or {}
        except Exception:  # noqa: BLE001
            logger.exception("extract_decision_makers: LLM failed")
            return []

        people_raw = data.get("people") or []
        if not isinstance(people_raw, list):
            return []
        out: list[dict[str, Any]] = []
        for p in people_raw[:4]:
            if not isinstance(p, dict):
                continue
            name = _trim_or_none(p.get("name"))
            if not name:
                continue
            entry = {
                "name": name[:120],
                "role": (_trim_or_none(p.get("role")) or None),
                "email": (_trim_or_none(p.get("email")) or None),
                "linkedin": (_trim_or_none(p.get("linkedin")) or None),
            }
            out.append(entry)
        return out

    async def research_lead_for_outreach(
        self,
        lead: dict[str, Any],
        user_profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        website_url = (lead.get("website") or "").strip()
        empty: dict[str, Any] = {
            "notable_facts": [],
            "recent_signal": None,
            "suggested_opener": None,
        }
        if not website_url or self.client is None:
            return empty

        try:
            async with WebsiteCollector() as collector:
                info = await collector.fetch(website_url)
        except Exception:  # noqa: BLE001
            logger.exception(
                "research_lead_for_outreach: site fetch failed for %s",
                website_url,
            )
            return empty

        if not info.ok or not info.main_text:
            return empty

        site_excerpt = (info.main_text or "")[:6000]
        meta_block = []
        if info.title:
            meta_block.append(f"Title: {info.title}")
        if info.description:
            meta_block.append(f"Meta description: {info.description}")
        meta_str = "\n".join(meta_block)

        profile_block = (
            _format_user_profile(user_profile) if user_profile else ""
        )

        system = (
            "Ты — research-аналитик для холодных продаж. Прочитай сайт "
            "лида и вытащи 2-4 КОНКРЕТНЫХ факта про этот бизнес, "
            "которые продажник может процитировать в первой строке "
            "холодного письма. Цель — НЕ повторить шаблон «у вас "
            "красивый сайт», а сказать что-то настолько конкретное, "
            "что лид поймёт: письмо реально про него.\n\n"
            "Также найди RECENT_SIGNAL — любую заметную свежесть "
            "(новая услуга, открыли локацию, недавний пост, апдейт "
            "сайта). Если ничего такого нет — null.\n\n"
            "На базе этого предложи 1-2 предложения «opener» под "
            "конкретный профиль продавца. Это будет ПЕРВАЯ строка "
            "его cold-email — должна быть короткая и личная.\n\n"
            "ПРАВИЛА:\n"
            "- Факты — короткие фразы 5-15 слов. Цитируй сайт почти "
            "дословно когда можно.\n"
            "- Не выдумывай. Если факта нет в excerpt — не пиши.\n"
            "- Язык: на котором написан сайт. Если он английский — "
            "пиши факты на английском.\n"
            "- recent_signal — фраза 5-15 слов либо null.\n"
            "- suggested_opener — 1-2 предложения, не больше 200 знаков.\n\n"
            "Формат ответа — СТРОГО JSON без markdown:\n"
            '{"notable_facts": ["…", "…"], '
            '"recent_signal": "…|null", '
            '"suggested_opener": "…|null"}'
            + (
                "\n\nПрофиль продавца:\n" + profile_block
                if profile_block
                else ""
            )
        )

        user_msg_parts = [meta_str] if meta_str else []
        user_msg_parts.append(f"Сайт excerpt:\n{site_excerpt}")
        user_msg = "\n\n".join(user_msg_parts)

        try:
            async with self._sem:
                msg = await self.client.messages.create(
                    model=self.model,
                    max_tokens=600,
                    system=system,
                    messages=[{"role": "user", "content": user_msg}],
                )
                raw = msg.content[0].text  # type: ignore[union-attr]
                data = _extract_json(raw) or {}
        except Exception:  # noqa: BLE001
            logger.exception("research_lead_for_outreach: LLM call failed")
            return empty

        facts_raw = data.get("notable_facts") or []
        notable_facts: list[str] = []
        if isinstance(facts_raw, list):
            for f in facts_raw[:4]:
                cleaned = _trim_or_none(f)
                if cleaned:
                    notable_facts.append(cleaned[:200])
        recent = _trim_or_none(data.get("recent_signal"))
        opener = _trim_or_none(data.get("suggested_opener"))
        return {
            "notable_facts": notable_facts,
            "recent_signal": recent,
            "suggested_opener": opener[:300] if opener else None,
        }
