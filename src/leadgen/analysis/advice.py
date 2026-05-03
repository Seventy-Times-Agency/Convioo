"""Henry advisory primitives: consult, chat, session summary, weekly check-in, base insights."""

from __future__ import annotations

import logging
from typing import Any

from leadgen.analysis import henry_core
from leadgen.analysis._helpers import (
    _clean_profile_suggestion,
    _clean_team_suggestion,
    _extract_json,
    _heuristic_consult,
    _trim_or_none,
)
from leadgen.analysis.prompts import (
    _assistant_personal_system_prompt,
    _assistant_team_system_prompt,
    _format_user_profile,
)

logger = logging.getLogger(__name__)


class AdviceMixin:
    async def consult_search(
        self,
        history: list[dict[str, str]],
        user_profile: dict[str, Any] | None = None,
        current_state: dict[str, Any] | None = None,
        last_asked_slot: str | None = None,
    ) -> dict[str, Any]:
        clean_history = [
            {"role": m["role"], "content": str(m.get("content", "")).strip()}
            for m in history
            if m.get("role") in {"user", "assistant"} and m.get("content")
        ]
        state = current_state or {}
        carried_niche = _trim_or_none(state.get("niche"))
        carried_region = _trim_or_none(state.get("region"))
        carried_ideal = _trim_or_none(state.get("ideal_customer"))
        carried_exclusions = _trim_or_none(state.get("exclusions"))
        valid_slots = {"niche", "region", "ideal_customer", "exclusions"}
        carried_slot = (
            last_asked_slot if last_asked_slot in valid_slots else None
        )

        if not clean_history:
            profile = user_profile or {}
            niches = profile.get("niches") or []
            region = profile.get("home_region")
            profession = (
                profile.get("profession") or profile.get("service_description")
            )
            if niches and region:
                niches_preview = ", ".join(niches[:3])
                reply = (
                    f"Привет. Вижу — у вас в фокусе {niches_preview} "
                    f"в {region}. С какой ниши сегодня начнём, или "
                    "хотите подобрать что-то новое?"
                )
            elif niches:
                niches_preview = ", ".join(niches[:3])
                reply = (
                    f"Привет. У вас в нишах {niches_preview}. С какой "
                    "из них сегодня работаем и в каком городе?"
                )
            elif region and profession:
                reply = (
                    f"Привет. Знаю что вы продаёте {profession} в "
                    f"{region}. Какой сегмент сегодня ищем?"
                )
            else:
                reply = (
                    "Привет — расскажите, кого ищете: какая ниша, "
                    "в каком городе или регионе, и что именно делает "
                    "идеального клиента для вас."
                )
            return {
                "reply": reply,
                "niche": carried_niche,
                "region": carried_region,
                "ideal_customer": carried_ideal,
                "exclusions": carried_exclusions,
                "ready": bool(carried_niche and carried_region),
                "last_asked_slot": carried_slot,
            }

        if self.client is None:
            fallback = _heuristic_consult(
                clean_history, last_asked_slot=carried_slot
            )
            fallback["niche"] = fallback.get("niche") or carried_niche
            fallback["region"] = fallback.get("region") or carried_region
            fallback["ideal_customer"] = (
                fallback.get("ideal_customer") or carried_ideal
            )
            fallback["exclusions"] = (
                fallback.get("exclusions") or carried_exclusions
            )
            fallback["ready"] = bool(
                fallback["niche"] and fallback["region"]
            )
            return fallback

        profile_block = _format_user_profile(user_profile) if user_profile else ""
        state_block = (
            "\n\n=============================================="
            "\nТЕКУЩЕЕ СОСТОЯНИЕ ФОРМЫ\n"
            "==============================================\n"
            "(уже извлечено и видно пользователю справа):\n"
            f"- niche: {carried_niche or 'null'}\n"
            f"- region: {carried_region or 'null'}\n"
            f"- ideal_customer: {carried_ideal or 'null'}\n"
            f"- exclusions: {carried_exclusions or 'null'}\n"
            "Эти значения УЖЕ записаны в форме. Не перезаписывай их, "
            "если пользователь явно не поправляет соответствующее поле. "
            "Если поле уже заполнено и пользователь не упоминает его — "
            "верни тот же текст что в текущем состоянии (не null).\n"
        )
        awaiting_block = ""
        if carried_slot:
            awaiting_block = (
                "\n=============================================="
                "\nКАКОЙ СЛОТ ТЫ ЖДЁШЬ ПРЯМО СЕЙЧАС"
                "\n=============================================="
                f"\nНа предыдущем ходу ты задал вопрос про слот "
                f"«{carried_slot}». Если ответ юзера выглядит как "
                "ответ именно на этот вопрос — обновляй ТОЛЬКО этот "
                "слот, остальные верни как в текущем состоянии. Если "
                "ответ — встречный вопрос или смена темы — НЕ "
                "обновляй слоты, отвечай по теме его сообщения.\n"
            )
        surface = (
            "\n\n=============================================="
            "\nГДЕ ТЫ СЕЙЧАС РАБОТАЕШЬ — ПОИСКОВЫЙ КОНСУЛЬТАНТ\n"
            "==============================================\n"
            "Это окно сборки нового поиска (/app/search). Помогаешь "
            "продажнику собрать ОСМЫСЛЕННЫЙ запрос под Google Maps — "
            "не «50 любых стоматологий», а «50 стоматологий в Берлине, "
            "премиум, рейтинг 4.5+, без сетей».\n\n"
            "Чем точнее запрос — тем выше hot-rate. 80% продажников "
            "описывают ICP размыто и теряют время на холодных лидах. "
            "Твоя работа — копнуть один-два раза, пока запрос не станет "
            "конкретным, потом запускаем.\n\n"
            "==============================================\n"
            "ОПИРАЙСЯ НА ПРОФИЛЬ ЮЗЕРА (если он заполнен)\n"
            "==============================================\n"
            "Профиль продавца — что он продаёт, его регион, его ниши — "
            "приклеен ниже системного промпта. Если он заполнен:\n"
            "- НЕ переспрашивай то, что в нём уже есть. «Чем "
            "занимаетесь?» / «На что охотитесь?» — это потеря времени.\n"
            "- Открывай разговор персонализированно: «Вижу, у вас "
            "{profession}, охотитесь на {ниши}. Под этот поиск возьмём "
            "{одну из ниш} в {home_region}, или сегодня другой "
            "сегмент?»\n"
            "- Когда юзер просит «подбери варианты» / «что попробовать» "
            "/ «не знаю с чего начать» — предлагай 2-3 конкретные "
            "связки (niche+region) на базе его профиля. Учитывай его "
            "целевые ниши. Если у юзера США → можно предложить не "
            "только NY, но и Stamford, Boston, Austin. Если EU → не "
            "только Berlin, но и Munich, Wien, Amsterdam.\n"
            "- НЕ задавай вопрос если ответ уже виден из профиля.\n\n"
            "ОСИ КОТОРЫЕ НУЖНО ПРОЯСНИТЬ:\n"
            "1. niche — конкретный тип бизнеса (2-5 слов). Не «B2B», "
            "не «малый бизнес». «Стоматологическая клиника», "
            "«барбершоп».\n"
            "2. region — конкретный город. «Берлин», «Stamford, CT». "
            "Не страна, не «вся Европа». Если дают страну — переспроси "
            "первый город для старта. Если город звучит подозрительно "
            "(опечатка, несуществующее место) — переспроси: «Уточните "
            "— это {что-то рядом из реальных}? Или другой город?» Не "
            "запускай заведомо невалидный регион.\n"
            "3. ideal_customer — 1-3 предложения с конкретикой "
            "(размер бизнеса, ценовой сегмент, рейтинг, цифровая "
            "зрелость, триггеры покупки).\n"
            "4. exclusions — кого не нужно (сети, франшизы, "
            "уже отработанный сегмент).\n\n"
            "ХОРОШИЙ FLOW (профиль ПУСТОЙ):\n"
            "Юзер: «Я ищу стоматологии».\n"
            "Ты: «Понял. В каком городе стартуем — и какой типичный "
            "успешный клиент у вас был, премиум или средний?» "
            "(last_asked_slot=region)\n"
            "Юзер: «А что значит горячий лид?»\n"
            "Ты: «Лид с AI-скором ≥75 — сравниваем сайт, отзывы, "
            "соцсети с вашим профилем. Так что важно для вас?» "
            "(slots не трогаем, last_asked_slot остаётся ideal_customer)\n\n"
            "ХОРОШИЙ FLOW (профиль ЗАПОЛНЕН — ниши = roofing/tatto/nails, "
            "регион = Stamford, продаёт AI-автоматизацию):\n"
            "Юзер: первое сообщение / 'привет' / 'давай'.\n"
            "Ты: «Привет. У вас в фокусе roofing/tattoo/nails в "
            "Stamford. С какой ниши сегодня начнём — или хотите "
            "попробовать что-то новое из соседних городов "
            "(Norwalk, Bridgeport)?» (last_asked_slot=niche)\n"
            "Юзер: «давай маникюр».\n"
            "Ты: «Окей, nails salon в Stamford. По вашему профилю "
            "целитесь в платежеспособных без своего сайта — "
            "запустим с этим, или хотите уточнить ICP?» "
            "(niche=nails salon, region=Stamford, "
            "ideal_customer=платёжеспособные без сайта, "
            "last_asked_slot=ideal_customer)\n"
            "Юзер: «запускай».\n"
            "Ты: «Понял, готово.» (ready=true)\n\n"
            "ГОТОВНОСТЬ К ЗАПУСКУ:\n"
            "ready=true только когда: niche есть короткой фразой; "
            "region — конкретный город; юзер либо ответил про идеального "
            "клиента, либо явно сказал «и так норм / запускай». "
            "ideal_customer/exclusions — желательны, но не обязательны."
        )
        json_format = (
            "\n\n=============================================="
            "\nФОРМАТ ОТВЕТА — СТРОГО ОДИН JSON БЕЗ MARKDOWN\n"
            "==============================================\n"
            "Возвращай ВСЕ четыре слота на каждом ходу. Если слот уже "
            "заполнен в текущем состоянии и юзер его не трогал — "
            "повтори то же значение, НЕ ставь null. last_asked_slot = "
            "имя слота про который ты задаёшь вопрос на этом ходу "
            "(niche|region|ideal_customer|exclusions), или null.\n"
            '{"reply": "…", "niche": "…|null", "region": "…|null", '
            '"ideal_customer": "…|null", "exclusions": "…|null", '
            '"ready": true|false, '
            '"last_asked_slot": "niche|region|ideal_customer|exclusions|null"}'
        )
        system = (
            henry_core.base_block()
            + "\n\n"
            + henry_core.knowledge_block()
            + surface
            + state_block
            + awaiting_block
            + json_format
        )
        if profile_block:
            system += "\n\n=============================================="
            system += "\nПРОФИЛЬ ПРОДАВЦА (под кого подбираем лидов)\n"
            system += "==============================================\n"
            system += profile_block

        try:
            async with self._sem:
                msg = await self.client.messages.create(
                    model=self.model,
                    max_tokens=600,
                    system=system,
                    messages=clean_history,
                )
                raw = msg.content[0].text  # type: ignore[union-attr]
                data = _extract_json(raw) or {}
        except Exception:  # noqa: BLE001
            logger.exception("consult_search failed")
            fallback = _heuristic_consult(
                clean_history, last_asked_slot=carried_slot
            )
            fallback["niche"] = fallback.get("niche") or carried_niche
            fallback["region"] = fallback.get("region") or carried_region
            fallback["ideal_customer"] = (
                fallback.get("ideal_customer") or carried_ideal
            )
            fallback["exclusions"] = (
                fallback.get("exclusions") or carried_exclusions
            )
            fallback["ready"] = bool(
                fallback["niche"] and fallback["region"]
            )
            return fallback

        def pick(slot: str, llm_value: Any, carried: str | None) -> str | None:
            if carried_slot and carried_slot != slot:
                return carried
            return _trim_or_none(llm_value) or carried

        next_niche = pick("niche", data.get("niche"), carried_niche)
        next_region = pick("region", data.get("region"), carried_region)
        next_ideal = pick(
            "ideal_customer", data.get("ideal_customer"), carried_ideal
        )
        next_exclusions = pick(
            "exclusions", data.get("exclusions"), carried_exclusions
        )

        next_slot_raw = _trim_or_none(data.get("last_asked_slot"))
        next_slot = (
            next_slot_raw if next_slot_raw in valid_slots else None
        )

        return {
            "reply": str(data.get("reply") or "").strip()
            or "Расскажите подробнее — какая ниша и в каком городе?",
            "niche": next_niche,
            "region": next_region,
            "ideal_customer": next_ideal,
            "exclusions": next_exclusions,
            "ready": bool(data.get("ready"))
            and bool(next_niche)
            and bool(next_region),
            "last_asked_slot": next_slot,
        }

    async def assistant_chat(
        self,
        history: list[dict[str, str]],
        user_profile: dict[str, Any] | None = None,
        team_context: dict[str, Any] | None = None,
        awaiting_field: str | None = None,
        memories: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        clean_history = [
            {"role": m["role"], "content": str(m.get("content", "")).strip()}
            for m in history
            if m.get("role") in {"user", "assistant"} and m.get("content")
        ]
        is_team = bool(team_context)
        is_owner = bool(team_context and team_context.get("is_owner"))
        mode = "team_owner" if is_owner else "team_member" if is_team else "personal"

        valid_personal_fields = {
            "display_name",
            "age_range",
            "business_size",
            "service_description",
            "home_region",
            "niches",
        }
        carried_awaiting = (
            awaiting_field if awaiting_field in valid_personal_fields else None
        )

        empty_response: dict[str, Any] = {
            "reply": "",
            "mode": mode,
            "profile_suggestion": None,
            "team_suggestion": None,
            "suggestion_summary": None,
            "awaiting_field": carried_awaiting,
        }
        if not clean_history:
            if is_team:
                team_name = (team_context or {}).get("name") or "вашей команды"
                empty_response["reply"] = (
                    f"Привет. Сейчас вы работаете в команде «{team_name}» — "
                    "помогу с подбором лидов под её специфику, расскажу про "
                    "коллег и их зоны ответственности. С чем работаем?"
                )
            else:
                empty_response["reply"] = (
                    "Привет, я Henry — ваш консультант Convioo. "
                    "Могу помочь с настройкой профиля, объяснить как работает "
                    "оценка лидов, подсказать как точнее описать ваш сегмент. "
                    "С чем поможем?"
                )
            return empty_response

        if self.client is None:
            empty_response["reply"] = (
                "Сейчас я могу отвечать только когда AI подключён. "
                "Попробуйте позже."
            )
            return empty_response

        if is_team:
            # In team mode personal profile is intentionally hidden, but
            # we still pass language_code through team_context so Henry
            # answers in the viewer's UI language.
            viewer_lang = (
                (team_context or {}).get("viewer_language_code")
                or (user_profile or {}).get("language_code")
            )
            system = _assistant_team_system_prompt(
                team_context,
                is_owner,
                memories=memories,
                viewer_language_code=viewer_lang,
            )
        else:
            system = _assistant_personal_system_prompt(
                user_profile,
                awaiting_field=carried_awaiting,
                memories=memories,
            )

        try:
            async with self._sem:
                msg = await self.client.messages.create(
                    model=self.model,
                    max_tokens=700,
                    system=system,
                    messages=clean_history,
                )
                raw = msg.content[0].text  # type: ignore[union-attr]
                data = _extract_json(raw) or {}
        except Exception as exc:  # noqa: BLE001
            slug, ru_label = self._classify_anthropic_error(exc)
            logger.exception(
                "assistant_chat failed (%s) for user_id=%s team=%s",
                slug,
                (team_context or {}).get("viewer_user_id") if team_context else None,
                (team_context or {}).get("team_id") if team_context else None,
            )
            return {
                "reply": (
                    f"Секунду — у меня сейчас {ru_label}. Дайте мне "
                    "пару секунд и пришлите сообщение ещё раз. Если "
                    "повторится — это не вы, это инфра."
                ),
                "mode": mode,
                "profile_suggestion": None,
                "team_suggestion": None,
                "suggestion_summary": None,
                "awaiting_field": carried_awaiting,
            }

        profile_suggestion: dict[str, Any] | None = None
        team_suggestion: dict[str, Any] | None = None
        if not is_team:
            profile_suggestion = _clean_profile_suggestion(
                data.get("profile_suggestion")
            )
        if is_owner:
            team_suggestion = _clean_team_suggestion(
                data.get("team_suggestion"), team_context
            )

        next_awaiting_raw = _trim_or_none(data.get("awaiting_field"))
        next_awaiting = (
            next_awaiting_raw
            if next_awaiting_raw in valid_personal_fields
            else None
        )

        return {
            "reply": str(data.get("reply") or "").strip()
            or "Расскажите подробнее, чтобы я мог помочь.",
            "mode": mode,
            "profile_suggestion": profile_suggestion,
            "team_suggestion": team_suggestion,
            "suggestion_summary": _trim_or_none(data.get("suggestion_summary")),
            "awaiting_field": next_awaiting if not is_team else None,
        }

    async def summarize_session(
        self,
        history: list[dict[str, str]],
        user_profile: dict[str, Any] | None = None,
        existing_memories: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        clean_history = [
            {"role": m["role"], "content": str(m.get("content", "")).strip()}
            for m in history
            if m.get("role") in {"user", "assistant"} and m.get("content")
        ]
        if not clean_history or self.client is None:
            return {"summary": None, "facts": []}

        existing_block = ""
        if existing_memories:
            bullets = []
            for em in existing_memories[:10]:
                kind = (em.get("kind") or "").upper()
                content = (em.get("content") or "").strip()
                if content:
                    bullets.append(f"- [{kind}] {content}")
            if bullets:
                existing_block = (
                    "\n\nЧто ты УЖЕ записал ранее (не дублируй эти "
                    "факты, выдай только новое):\n" + "\n".join(bullets)
                )

        profile_block = (
            _format_user_profile(user_profile) if user_profile else ""
        )

        system = (
            "Ты — Henry, ведёшь дневник наблюдений по своему клиенту. "
            "На вход — последние реплики из вашего диалога. На выход — "
            "ОДНО короткое резюме сессии (1-3 предложения) и 0-5 "
            "конкретных ДОЛГОИГРАЮЩИХ фактов о юзере (что продаёт, "
            "целевые ниши, типичные возражения, его hot-rate, "
            "регион работы — то, что пригодится тебе через неделю).\n\n"
            "Правила:\n"
            "- Никаких офтоп-фактов («у юзера хорошее настроение»).\n"
            "- Только то, что повлияет на следующие диалоги или скоринг.\n"
            "- Не дублируй то, что уже записано (см. блок ниже).\n"
            "- Язык фактов — на котором писал юзер.\n"
            "- Если новых фактов нет — facts: [].\n"
            "- Если сессия была короткой / пустой / только про офтоп — "
            "summary: null.\n\n"
            "Формат ответа — СТРОГО JSON без markdown:\n"
            '{"summary": "…|null", "facts": ["…", "…"]}'
            + (
                "\n\nПрофиль юзера для контекста:\n" + profile_block
                if profile_block
                else ""
            )
            + existing_block
        )

        try:
            async with self._sem:
                msg = await self.client.messages.create(
                    model=self.model,
                    max_tokens=400,
                    system=system,
                    messages=clean_history[-12:],
                )
                raw = msg.content[0].text  # type: ignore[union-attr]
                data = _extract_json(raw) or {}
        except Exception:  # noqa: BLE001
            slug, _ = self._classify_anthropic_error(
                Exception("summarize_session")
            )
            logger.exception("summarize_session failed (%s)", slug)
            return {"summary": None, "facts": []}

        summary = _trim_or_none(data.get("summary"))
        facts_raw = data.get("facts") or []
        facts: list[str] = []
        if isinstance(facts_raw, list):
            for f in facts_raw[:5]:
                cleaned = _trim_or_none(f)
                if cleaned:
                    facts.append(cleaned[:500])
        return {
            "summary": summary[:500] if summary else None,
            "facts": facts,
        }

    async def weekly_checkin(
        self,
        stats: dict[str, Any],
        user_profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        def _fallback() -> dict[str, Any]:
            total = int(stats.get("leads_total") or 0)
            hot = int(stats.get("hot_total") or 0)
            untouched = int(stats.get("untouched_14d") or 0)
            new7 = int(stats.get("new_this_week") or 0)
            if total == 0:
                summary = (
                    "Лидов в CRM пока нет — запустите первый поиск из "
                    "сайдбара, и я подберу что-нибудь под ваш профиль."
                )
            else:
                hot_rate = hot * 100 // max(total, 1)
                summary = (
                    f"В базе {total} лидов, {hot_rate}% горячих. "
                    f"За неделю добавилось {new7}. "
                    f"Без касания 14+ дней — {untouched}."
                )
            highlights: list[str] = []
            if hot > 0:
                highlights.append(f"{hot} горячих лидов в работе")
            if untouched > 0:
                highlights.append(
                    f"{untouched} лидов без касания — стоит вернуться"
                )
            if new7 > 0:
                highlights.append(f"+{new7} лидов за последнюю неделю")
            return {"summary": summary, "highlights": highlights[:3]}

        if self.client is None:
            return _fallback()

        profile_block = (
            _format_user_profile(user_profile) if user_profile else ""
        )

        stats_lines = [
            f"- Всего лидов: {stats.get('leads_total', 0)}",
            f"- Горячих: {stats.get('hot_total', 0)}",
            f"- Тёплых: {stats.get('warm_total', 0)}",
            f"- Холодных: {stats.get('cold_total', 0)}",
            f"- Новых за неделю: {stats.get('new_this_week', 0)}",
            f"- Без касания 14+ дней: {stats.get('untouched_14d', 0)}",
            f"- Сессий за неделю: {stats.get('sessions_this_week', 0)}",
        ]
        if stats.get("last_session_at"):
            stats_lines.append(
                f"- Последняя сессия: {stats['last_session_at']}"
            )
        stats_block = "\n".join(stats_lines)

        system = (
            henry_core.PERSONA
            + "\n\n"
            + "ЭТО WEEKLY CHECK-IN.\n"
            "Тебе дали свежий снэпшот по CRM юзера. Дай короткий "
            "human-разбор: 2-3 предложения в твоём стиле (живой sales-"
            "консультант, без воды) — что важно из этих цифр, что бы "
            "ты сделал прямо сейчас. Плюс 1-3 коротких bullet-"
            "highlights для UI-чипов (5-9 слов каждый).\n\n"
            "ПРАВИЛА:\n"
            "- НЕ хвали ради похвалы. Если hot-rate низкий — назови это.\n"
            "- НЕ перечисляй цифры тупо («у вас 80 лидов, 30% горячих»). "
            "Скажи что это значит и что делать.\n"
            "- Если нет лидов вообще — мотивируй запустить первый поиск.\n"
            "- highlights — действенные («Hot за неделю: 5», "
            "«18 лидов без касания»), не общие.\n"
            "- Язык: тот, что в профиле юзера (русский / английский).\n\n"
            "Формат ответа — СТРОГО JSON без markdown:\n"
            '{"summary": "…", "highlights": ["…", "…"]}'
            + (
                "\n\nПрофиль юзера:\n" + profile_block
                if profile_block
                else ""
            )
        )

        try:
            async with self._sem:
                msg = await self.client.messages.create(
                    model=self.model,
                    max_tokens=400,
                    system=system,
                    messages=[
                        {"role": "user", "content": stats_block},
                    ],
                )
                raw = msg.content[0].text  # type: ignore[union-attr]
                data = _extract_json(raw) or {}
        except Exception:  # noqa: BLE001
            logger.exception("weekly_checkin failed")
            return _fallback()

        summary = _trim_or_none(data.get("summary")) or _fallback()["summary"]
        highlights_raw = data.get("highlights") or []
        highlights: list[str] = []
        if isinstance(highlights_raw, list):
            for h in highlights_raw[:3]:
                cleaned = _trim_or_none(h)
                if cleaned:
                    highlights.append(cleaned[:80])
        return {"summary": summary[:600], "highlights": highlights}

    async def base_insights(
        self,
        analysed_leads: list[dict[str, Any]],
        niche: str,
        region: str,
        user_profile: dict[str, Any] | None = None,
    ) -> str:
        if not analysed_leads:
            return "Нет данных для анализа."

        if self.client is None:
            hot = sum(1 for lead in analysed_leads if float(lead.get("score_ai") or 0) >= 75)
            with_site = sum(1 for lead in analysed_leads if lead.get("website"))
            with_social = sum(1 for lead in analysed_leads if (lead.get("social_links") or {}))
            return (
                f"• По нише «{niche}» в регионе «{region}» собрано {len(analysed_leads)} компаний.\n"
                f"• Горячих лидов (75+) — {hot}.\n"
                f"• С сайтом: {with_site}/{len(analysed_leads)}, с соцсетями: {with_social}/{len(analysed_leads)}.\n"
                "• Рекомендуемый фокус: лиды с высоким рейтингом и активными соцсетями.\n"
                "• Для холодных лидов: предлагай быстрый аудит сайта и репутации."
            )

        snapshot_lines: list[str] = []
        for lead in analysed_leads[:25]:
            snapshot_lines.append(
                f"- {lead.get('name', '?')}: "
                f"score={lead.get('score_ai', '?')}, "
                f"tags={lead.get('tags') or []}, "
                f"summary={lead.get('summary') or ''}"
            )

        profile_block = _format_user_profile(user_profile) if user_profile else ""
        prompt = (
            f"Ниша: {niche}. Регион: {region}.\n"
            f"Всего лидов в базе: {len(analysed_leads)}.\n"
            f"{profile_block}\n\n"
            "Срез по проанализированным лидам:\n"
            f"{chr(10).join(snapshot_lines)}\n\n"
            "Дай короткий аналитический вывод по всей базе (5-7 пунктов) "
            "ИМЕННО под услугу этого пользователя:\n"
            "1) Какие общие паттерны по бизнесам в этой выборке?\n"
            "2) На каких клиентах пользователю фокусироваться в первую очередь и почему?\n"
            "3) Какие типичные слабые места у этих бизнесов может закрыть именно услуга пользователя?\n"
            "4) Какие риски / на что обратить внимание?\n"
            "5) Конкретные рекомендации: с чего начать обзвон/переписку, какой питч использовать.\n\n"
            "Пиши коротко, по делу, маркированным списком на русском языке. "
            "Без markdown-обёрток, просто текст."
        )

        try:
            async with self._sem:
                msg = await self.client.messages.create(
                    model=self.model,
                    max_tokens=700,
                    messages=[{"role": "user", "content": prompt}],
                )
                return msg.content[0].text.strip()  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001
            logger.exception("base_insights failed")
            return f"(не удалось сформировать инсайты: {exc})"
