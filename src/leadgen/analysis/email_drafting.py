"""Cold-email draft generator."""

from __future__ import annotations

import logging
from typing import Any

from leadgen.analysis._helpers import (
    _extract_json,
    _format_lead_for_email,
    _heuristic_email,
    _trim_or_none,
)
from leadgen.analysis.anthropic_caching import cached_system
from leadgen.analysis.prompts import _format_user_profile
from leadgen.utils.locale_text import normalize_lang

logger = logging.getLogger(__name__)


# Human-readable names the prompt uses to pin the email language.
# This is the *email* language — distinct from the UI language: the
# user may run the UI in Ukrainian but write outreach in English.
_EMAIL_LANGUAGE_NAME = {
    "ru": "Russian (русский)",
    "uk": "Ukrainian (українська)",
    "en": "English",
}


class EmailDraftingMixin:
    async def generate_cold_email(
        self,
        lead: dict[str, Any],
        user_profile: dict[str, Any] | None = None,
        tone: str = "professional",
        extra_context: str | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        clean_tone = (tone or "professional").strip().lower()
        if clean_tone not in {"professional", "casual", "bold"}:
            clean_tone = "professional"

        # Effective email language: explicit per-email override wins,
        # then the user's UI language, then ru (frontend default).
        email_lang = normalize_lang(
            language or (user_profile or {}).get("language_code")
        )
        email_lang_name = _EMAIL_LANGUAGE_NAME[email_lang]

        if self.client is None:
            return _heuristic_email(
                lead, user_profile, clean_tone, language=email_lang
            )

        profile_block = _format_user_profile(user_profile) if user_profile else ""
        calendly_hint = ""
        if user_profile and user_profile.get("calendly_url"):
            calendly_hint = (
                f"\n\nЕСЛИ РЕЛЕВАНТНО: упомяни в P.S. или в CTA ссылку для записи: "
                f"{user_profile['calendly_url']}\n"
                f"Например: «есть в расписании в среду — доступен тут: [ссылка]» или "
                f"просто в CTA: «ответьте или выберите время: [ссылка]»"
            )
        lead_block = _format_lead_for_email(lead)
        tone_hint = {
            "professional": (
                "Тон: профессиональный, тёплый, по-человечески "
                "уверенный. Без формальностей вроде «уважаемый»."
            ),
            "casual": (
                "Тон: лёгкий, дружелюбный, как письмо знакомому. "
                "Без сленга, но без жёстких формальностей."
            ),
            "bold": (
                "Тон: уверенный, прямой, с конкретным провокационным "
                "наблюдением. Без агрессии, но без воды."
            ),
        }[clean_tone]
        extra_block = ""
        if extra_context:
            extra_block = (
                "\n\nДополнительный контекст от продажника "
                f"(учти при формулировке):\n{extra_context.strip()}"
            )

        system = (
            "Ты — senior B2B-копирайтер по холодным письмам. 10+ лет "
            "пишешь outbound для агентств, SaaS, локальных услуг. "
            "Твои письма открывают и отвечают потому что они "
            "персональные, короткие и не звучат как спам.\n\n"
            "==============================================\n"
            "ЗАДАЧА\n"
            "==============================================\n"
            "Написать ОДНО первое холодное письмо от лица продажника "
            "конкретно этому лиду. Используй данные про лида (его "
            "сильные стороны, слабые, AI-advice) и профиль продажника "
            "(что он продаёт, кому). Письмо ДОЛЖНО быть про этого "
            "конкретного лида, не общая шаблонка.\n\n"
            "==============================================\n"
            "ЖЁСТКИЕ ПРАВИЛА\n"
            "==============================================\n"
            "1. Тема: 4-8 слов, без капса, без эмодзи, без "
            "«предложение / коммерческое». Цель — открыть.\n"
            "2. Тело: 50-100 слов МАКСИМУМ. Длиннее — не читают.\n"
            "3. Структура тела:\n"
            "   • 1-2 строки персонализированного opener-а — отсылка "
            "к чему-то конкретному в этой компании (рейтинг, отзывы, "
            "сильная сторона, заметная слабость, рынок). НЕ «я "
            "посмотрел ваш сайт и впечатлился» — это пустой шаблон.\n"
            "   • 1-2 строки value: что у тебя есть полезного для "
            "именно их ситуации. Связь между их слабостью / "
            "возможностью и твоим оффером.\n"
            "   • 1 короткое предложение CTA. Не «давайте созвон "
            "на этой неделе», а «есть смысл показать пример?» или "
            "«ответьте если интересно — пришлю короткое "
            "видео/кейс».\n"
            "4. БЕЗ КЛИШЕ:\n"
            "   • «I hope this email finds you well»\n"
            "   • «Sorry to bother»\n"
            "   • «Just wanted to reach out»\n"
            "   • «Quick question»\n"
            "   • «Уважаемый», «надеюсь у вас всё хорошо»\n"
            "5. Без markdown, без эмодзи, без буллетов в теле. "
            "Обычный текст с переносами строк.\n"
            f"6. CRITICAL — ЯЗЫК ПИСЬМА: write the email (subject and "
            f"body) in {email_lang_name}. Это выбор пользователя — "
            "пиши на этом языке независимо от языка этих инструкций, "
            "профиля продажника или данных лида.\n"
            f"7. {tone_hint}\n\n"
            "==============================================\n"
            "ФОРМАТ ОТВЕТА — СТРОГО JSON БЕЗ MARKDOWN\n"
            "==============================================\n"
            '{"subject": "…", "body": "…"}'
        )
        if profile_block:
            system += "\n\nПРОФИЛЬ ПРОДАЖНИКА:\n" + profile_block
        system += "\n\nЛИД:\n" + lead_block + calendly_hint + extra_block

        try:
            async with self._sem:
                msg = await self.client.messages.create(
                    model=self.model,
                    max_tokens=600,
                    system=cached_system(system),
                    messages=[
                        {
                            "role": "user",
                            "content": (
                                "Напиши письмо для этого лида. "
                                "Write the email (subject and body) in "
                                f"{email_lang_name}. "
                                "Отвечай только JSON-ом."
                            ),
                        }
                    ],
                )
                raw = msg.content[0].text  # type: ignore[union-attr]
                data = _extract_json(raw) or {}
        except Exception:  # noqa: BLE001
            logger.exception("generate_cold_email failed")
            return _heuristic_email(
                lead, user_profile, clean_tone, language=email_lang
            )

        subject = _trim_or_none(data.get("subject")) or ""
        body = _trim_or_none(data.get("body")) or ""
        if not subject or not body:
            return _heuristic_email(
                lead, user_profile, clean_tone, language=email_lang
            )
        return {"subject": subject, "body": body, "tone": clean_tone}
