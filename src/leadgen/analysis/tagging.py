"""Niche / search-axis suggestion + intent extraction."""

from __future__ import annotations

import logging
from typing import Any

from leadgen.analysis._helpers import (
    _clean_niches,
    _extract_json,
    _heuristic_intent,
    _trim_or_none,
)

logger = logging.getLogger(__name__)


class TaggingMixin:
    async def suggest_niches(
        self,
        user_profile: dict[str, Any] | None,
        existing: list[str] | None = None,
        max_results: int = 8,
    ) -> list[str]:
        profile = user_profile or {}
        seed = (
            profile.get("service_description")
            or profile.get("profession")
            or ""
        ).strip()
        if not seed or self.client is None:
            return []

        skip_set = {n.strip().lower() for n in (existing or []) if n}

        system = (
            "Ты — Henry, senior B2B sales-консультант. На вход даётся "
            "описание того что юзер продаёт; на выход — ровно "
            f"{max_results} конкретных типов бизнеса (ниш), для которых "
            "его услуга действительно полезна и которые легко находятся "
            "по Google Maps.\n\n"
            "Каждая ниша:\n"
            "- 1-4 слова, конкретный тип бизнеса (не «B2B вообще»).\n"
            "- На языке оригинального описания (русский / английский / …).\n"
            "- Должна реально пересекаться с тем, что продаёт юзер. Не "
            "бросай туда «всё подряд».\n"
            "- Не повторяй ниши, которые юзер уже добавил (см. блок ниже).\n\n"
            "Формат ответа — СТРОГО JSON без markdown:\n"
            '{"niches": ["…", "…", "…"]}'
        )
        skip_block = ""
        if skip_set:
            skip_block = (
                "\n\nУже выбраны (НЕ предлагай эти):\n"
                + "\n".join(f"- {n}" for n in sorted(skip_set))
            )

        user_msg = f"Что продаёт юзер:\n{seed}{skip_block}"

        try:
            async with self._sem:
                msg = await self.client.messages.create(
                    model=self.model,
                    max_tokens=400,
                    system=system,
                    messages=[{"role": "user", "content": user_msg}],
                )
                raw = msg.content[0].text  # type: ignore[union-attr]
                data = _extract_json(raw) or {}
        except Exception:  # noqa: BLE001
            logger.exception("suggest_niches failed")
            return []

        niches = data.get("niches") or []
        if not isinstance(niches, list):
            return []
        cleaned: list[str] = []
        seen: set[str] = set()
        for n in niches:
            if not isinstance(n, str):
                continue
            text = n.strip().strip("\"'«»").strip()
            if not text or len(text) > 80:
                continue
            key = text.lower()
            if key in skip_set or key in seen:
                continue
            seen.add(key)
            cleaned.append(text)
            if len(cleaned) >= max_results:
                break
        return cleaned

    async def extract_search_intent(self, description: str) -> dict[str, Any]:
        text = (description or "").strip()
        if not text:
            return {"niches": [], "region": None, "error": "empty"}

        if self.client is None:
            return _heuristic_intent(text)

        system = (
            "Ты помогаешь B2B-продажнику сформулировать поисковый запрос для "
            "Google Maps. Пользователь описывает свободным текстом, каких "
            "клиентов он ищет. Твоя задача — вытащить из описания 1–7 "
            "конкретных, коротких ниш бизнеса, каждая из которых пригодна "
            "как запрос в Google Maps (например: «стоматология», "
            "«автосервис», «фитнес-клуб», «кофейня»). Также вытащи регион/"
            "город если он упомянут.\n\n"
            "Отвечай СТРОГО в JSON, без markdown и пояснений:\n"
            '{"niches": ["…", "…"], "region": "город/регион или null"}\n\n'
            "Правила:\n"
            "- Каждая ниша: 2–60 символов, в единственном или привычном "
            "поисковом виде (например «салон красоты», не «салоны красоты»).\n"
            "- Не выдумывай ниши, которых нет в описании. Если описание "
            "размытое (например «малый бизнес»), верни максимум одну общую "
            "формулировку.\n"
            "- region — просто название города/области/страны из текста, "
            "без предлогов. Если нет — null.\n"
            "- Пиши по-русски."
        )

        try:
            async with self._sem:
                msg = await self.client.messages.create(
                    model=self.model,
                    max_tokens=400,
                    system=system,
                    messages=[{"role": "user", "content": text}],
                )
                raw = msg.content[0].text  # type: ignore[union-attr]
                data = _extract_json(raw)
        except Exception as exc:  # noqa: BLE001
            logger.exception("extract_search_intent failed")
            fallback = _heuristic_intent(text)
            fallback["error"] = str(exc)
            return fallback

        niches = _clean_niches(data.get("niches"))
        region_raw = data.get("region")
        region = (str(region_raw).strip() if region_raw else "") or None
        if not niches:
            return _heuristic_intent(text)
        return {"niches": niches, "region": region, "error": None}

    async def suggest_search_axes(
        self,
        user_profile: dict[str, Any] | None,
        max_results: int = 4,
    ) -> list[dict[str, Any]]:
        profile = user_profile or {}
        offer = (
            profile.get("service_description")
            or profile.get("profession")
            or ""
        ).strip()
        niches = list(profile.get("niches") or [])
        region = (profile.get("home_region") or "").strip()

        if not (offer or niches or region):
            return []
        if self.client is None:
            return []

        seed_lines = []
        if offer:
            seed_lines.append(f"Что продаёт юзер: {offer}")
        if niches:
            seed_lines.append("Целевые ниши: " + ", ".join(niches))
        if region:
            seed_lines.append(f"Базовый регион: {region}")
        seed = "\n".join(seed_lines)

        system = (
            "Ты — Henry, senior B2B sales-консультант. Юзер открыл "
            "новую сессию поиска и хочет несколько ГОТОВЫХ к запуску "
            "конфигураций. Учитывай его профиль, выдай "
            f"{max_results} разных вариантов — РАЗНЫЕ по нише или "
            "региону, не одно и то же с переименованной.\n\n"
            "Каждая конфигурация:\n"
            "- niche: 2-5 слов, конкретный тип бизнеса (НЕ «B2B»). "
            "На языке оригинала.\n"
            "- region: конкретный город (не страна, не «вся "
            "Европа»). Если у юзера home_region — половина вариантов "
            "локально, остальное — соседние / релевантные города.\n"
            "- ideal_customer: 1-2 предложения с конкретикой "
            "(размер, ценовой сегмент, цифровая зрелость).\n"
            "- exclusions: 1 фраза или null.\n"
            "- rationale: 1 короткое предложение почему этот вариант "
            "имеет смысл под этого юзера.\n\n"
            "Если у юзера региональный охват очевидно широкий "
            "(онлайн-агентство, SaaS) — обязательно одна-две "
            "карточки про менее очевидные города (не только NY/Berlin, "
            "но Stamford, Boston, Wien, Amsterdam).\n\n"
            "Формат ответа — СТРОГО JSON без markdown:\n"
            '{"options": [{"niche": "…", "region": "…", '
            '"ideal_customer": "…", "exclusions": "…|null", '
            '"rationale": "…"}, …]}'
        )

        try:
            async with self._sem:
                msg = await self.client.messages.create(
                    model=self.model,
                    max_tokens=900,
                    system=system,
                    messages=[{"role": "user", "content": seed}],
                )
                raw = msg.content[0].text  # type: ignore[union-attr]
                data = _extract_json(raw) or {}
        except Exception:  # noqa: BLE001
            logger.exception("suggest_search_axes failed")
            return []

        options = data.get("options") or []
        if not isinstance(options, list):
            return []
        cleaned: list[dict[str, Any]] = []
        for opt in options[: max_results * 2]:
            if not isinstance(opt, dict):
                continue
            niche = _trim_or_none(opt.get("niche"))
            opt_region = _trim_or_none(opt.get("region"))
            if not niche or not opt_region:
                continue
            cleaned.append(
                {
                    "niche": niche[:80],
                    "region": opt_region[:80],
                    "ideal_customer": (
                        _trim_or_none(opt.get("ideal_customer")) or None
                    ),
                    "exclusions": _trim_or_none(opt.get("exclusions")) or None,
                    "rationale": (
                        _trim_or_none(opt.get("rationale")) or None
                    ),
                }
            )
            if len(cleaned) >= max_results:
                break
        return cleaned
