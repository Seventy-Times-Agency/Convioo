"""LLM-powered lead analyzer.

For each enriched lead we send a structured context (Google Maps data,
website snapshot, recent reviews) to Claude and ask for a JSON verdict:
score, tags, advice, strengths/weaknesses, red flags.

Also generates a high-level base summary from a list of analysed leads.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from anthropic import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic,
    InternalServerError,
    RateLimitError,
)

from leadgen.analysis import henry_core
from leadgen.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LeadAnalysis:
    score: int
    tags: list[str] = field(default_factory=list)
    summary: str = ""
    advice: str = ""
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    error: str | None = None


SYSTEM_PROMPT_BASE = """\
Ты — опытный B2B-продажник. Твоя задача — оценивать потенциальных клиентов
по доступной информации (данные из Google Maps, контент сайта, соцсети,
отзывы) ИМЕННО ПОД УСЛУГУ КОНКРЕТНОГО ПОЛЬЗОВАТЕЛЯ, который тебя спрашивает.

Возвращай результат СТРОГО в формате JSON, без какого-либо текста до или
после JSON, без markdown-обёрток:

{
  "score": <целое число 0-100, общая оценка ценности лида ИМЕННО ДЛЯ ЭТОГО ПОЛЬЗОВАТЕЛЯ>,
  "tags": ["hot"|"warm"|"cold", "small"|"medium"|"large", и т.п.],
  "summary": "одна-две фразы о бизнесе",
  "advice": "2-3 предложения: как этому пользователю зайти к этому клиенту, какую боль закрыть, на чём делать упор в питче с учётом его услуги",
  "strengths": ["что у клиента хорошо"],
  "weaknesses": ["что хромает — точки роста, которые может закрыть ИМЕННО этот пользователь своей услугой"],
  "red_flags": ["причины НЕ работать с этим клиентом, если есть"]
}

Критерии скоринга:
- 75-100 (hot): клиент релевантен услуге пользователя, у него виден бюджет, и есть слабые места, которые пользователь может закрыть
- 50-74 (warm): потенциально интересен, но требует прогрева или услуга пользователя не идеально подходит
- 0-49 (cold): нет сайта/контактов/активности, либо явно не целевой клиент для услуги пользователя

Пиши кратко и по делу. Используй русский язык."""


_BUSINESS_SIZE_LABEL = {
    "solo": "соло / фрилансер",
    "small": "малая команда (2–10 чел.)",
    "medium": "компания (10–50 чел.)",
    "large": "крупный бизнес (50+ чел.)",
}


def _format_user_profile(profile: dict[str, Any] | None) -> str:
    if not profile:
        return ""
    parts = ["\n\nПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ (кто спрашивает):"]
    if profile.get("display_name"):
        parts.append(f"- Имя: {profile['display_name']}")
    if profile.get("age_range"):
        parts.append(f"- Возраст: {profile['age_range']}")
    if profile.get("business_size"):
        label = _BUSINESS_SIZE_LABEL.get(
            profile["business_size"], profile["business_size"]
        )
        parts.append(f"- Формат бизнеса: {label}")
    if profile.get("profession"):
        parts.append(f"- Чем занимается / что продаёт: {profile['profession']}")
    if profile.get("home_region"):
        parts.append(f"- Базовый регион: {profile['home_region']}")
    if profile.get("niches"):
        niches = ", ".join(profile["niches"])
        parts.append(f"- Целевые ниши: {niches}")
    target_languages = profile.get("target_languages") or []
    if target_languages:
        codes = ", ".join(target_languages)
        parts.append(
            f"- Языковое требование к лидам: {codes}. Продажник работает "
            "только на этих языках. Если у конкретной компании нет признаков "
            "владения хотя бы одним из них (язык названия, отзывов, сайта, "
            "адреса) — резко снижай скор (макс 35), добавляй в "
            "weaknesses пункт «нет языкового совпадения», и явно указывай "
            "это в advice."
        )
    parts.append(
        "\nОценивай лида и давай советы ИМЕННО под услугу, масштаб и профиль "
        "этого пользователя. Учитывай что клиенты-гиганты не подходят соло-"
        "фрилансеру, а совсем мелкие точки — не приоритет для крупной команды."
    )
    return "\n".join(parts)


def _build_system_prompt(user_profile: dict[str, Any] | None) -> str:
    return SYSTEM_PROMPT_BASE + _format_user_profile(user_profile)


# Back-compat alias for existing tests/imports
SYSTEM_PROMPT = SYSTEM_PROMPT_BASE


def _build_lead_context(lead: dict[str, Any], niche: str, region: str) -> str:
    lines: list[str] = [
        f"Запрос пользователя: ищем клиентов для услуг в нише «{niche}», регион «{region}».",
        "",
        "ДАННЫЕ О КОМПАНИИ:",
        f"- Название: {lead.get('name') or '—'}",
        f"- Категория: {lead.get('category') or '—'}",
        f"- Адрес: {lead.get('address') or '—'}",
        f"- Телефон: {lead.get('phone') or '—'}",
        f"- Сайт: {lead.get('website') or '—'}",
        (
            "- Рейтинг Google: "
            f"{lead.get('rating') or '—'} ({lead.get('reviews_count') or 0} отзывов)"
        ),
    ]

    website = lead.get("website_meta")
    if website and website.get("ok"):
        lines.append("")
        lines.append("ИНФОРМАЦИЯ С САЙТА:")
        if website.get("title"):
            lines.append(f"- Title: {website['title']}")
        if website.get("description"):
            lines.append(f"- Описание: {website['description']}")
        lines.append(
            f"- Цены: {'есть' if website.get('has_pricing') else 'нет'}; "
            f"портфолио: {'есть' if website.get('has_portfolio') else 'нет'}; "
            f"блог: {'есть' if website.get('has_blog') else 'нет'}; "
            f"HTTPS: {'да' if website.get('is_https') else 'нет'}"
        )
        if website.get("emails"):
            lines.append(f"- Email с сайта: {', '.join(website['emails'][:3])}")
        if website.get("social_links"):
            lines.append(f"- Соцсети: {', '.join(website['social_links'].keys())}")
        if website.get("main_text"):
            snippet = website["main_text"][:1200]
            lines.append(f"- Текст с сайта (фрагмент):\n  {snippet}")
    else:
        err = (website or {}).get("error") if website else None
        lines.append("")
        lines.append(f"САЙТ: недоступен или не указан ({err or 'нет данных'}).")

    reviews = lead.get("reviews") or []
    if reviews:
        lines.append("")
        lines.append("ПОСЛЕДНИЕ ОТЗЫВЫ:")
        for r in reviews[:5]:
            text_obj = r.get("text") or r.get("originalText") or {}
            text = text_obj.get("text", "") if isinstance(text_obj, dict) else str(text_obj)
            rating = r.get("rating", "?")
            lines.append(f"- [{rating}/5] {text[:250]}")

    return "\n".join(lines)


def _extract_json(text: str) -> dict[str, Any]:
    """Extract JSON from a possibly wrapped LLM response."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"no JSON found in response: {text[:200]}")


_NICHE_MIN = 2
_NICHE_MAX = 60
_NICHE_LIMIT = 7

_AGE_RANGE_CODES = ["<18", "18-24", "25-34", "35-44", "45-54", "55+"]
_BUSINESS_SIZE_CODES = ["solo", "small", "medium", "large"]

# Short fillers we strip when a user types a sentence instead of a bare name
# (e.g. "меня зовут Алексей" → "Алексей"). Case-insensitive, whole-word.
_NAME_PREFIX_PATTERNS = [
    r"^\s*(?:меня\s+)?зовут\s+",
    r"^\s*зови(?:те)?\s+меня\s+",
    r"^\s*называй(?:те)?\s+меня\s+",
    r"^\s*я\s+",
    r"^\s*мо[её]\s+имя\s*[—-]?\s*",
    r"^\s*имя\s*[—-]?\s*",
    r"^\s*пусть\s+будет\s+",
    r"^\s*call\s+me\s+",
    r"^\s*my\s+name\s+is\s+",
]

_REGION_PREFIX_PATTERNS = [
    r"^\s*я\s+(?:из|живу\s+в|нахожусь\s+в)\s+",
    r"^\s*живу\s+в\s+",
    r"^\s*из\s+",
    r"^\s*в\s+",
    r"^\s*город\s+",
]

_BIZ_KEYWORDS: list[tuple[str, list[str]]] = [
    ("solo", ["соло", "фриланс", "один", "одиночка", "сам себе", "индивидуальн", "ип без сотруд"]),
    ("small", ["малая команда", "небольш", "пара человек", "несколько человек", "small team"]),
    ("medium", ["средн", "компани", "агентство", "digital-агент", "студи"]),
    ("large", ["крупн", "большая команда", "корпорац", "enterprise", "холдинг"]),
]


def _age_from_number(age: int) -> str | None:
    if age < 0 or age > 120:
        return None
    if age < 18:
        return "<18"
    if age <= 24:
        return "18-24"
    if age <= 34:
        return "25-34"
    if age <= 44:
        return "35-44"
    if age <= 54:
        return "45-54"
    return "55+"


def _biz_from_headcount(n: int) -> str:
    if n <= 1:
        return "solo"
    if n <= 10:
        return "small"
    if n <= 50:
        return "medium"
    return "large"


def _strip_patterns(text: str, patterns: list[str]) -> str:
    out = text
    for pat in patterns:
        new = re.sub(pat, "", out, count=1, flags=re.IGNORECASE)
        if new != out:
            out = new
            break
    return out.strip()


def _clean_niches(raw: Any) -> list[str]:
    """Normalise a list of niche strings from either the LLM or the heuristic."""
    if not raw:
        return []
    if isinstance(raw, str):
        raw = [raw]
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        cleaned = re.sub(r"\s+", " ", item).strip().strip(".,;:").lower()
        if not (_NICHE_MIN <= len(cleaned) <= _NICHE_MAX):
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
        if len(out) >= _NICHE_LIMIT:
            break
    return out


def _heuristic_intent(description: str) -> dict[str, Any]:
    """Fallback niche extraction when no LLM is available.

    Splits on commas / newlines / conjunctions and takes each chunk as a
    candidate niche. Region is left as None — the bot will ask for it
    explicitly.
    """
    # Split on common separators including Russian conjunctions.
    chunks = re.split(r"[,\n;]|\s+(?:и|или|а также)\s+", description, flags=re.I)
    niches = _clean_niches(chunks)
    if not niches:
        # Last resort: use the whole description as one niche if it's short.
        trimmed = description.strip()
        if _NICHE_MIN <= len(trimmed) <= _NICHE_MAX:
            niches = [trimmed.lower()]
    return {"niches": niches, "region": None, "error": None}


def _bucket_tag(score: int) -> str:
    if score >= 75:
        return "hot"
    if score >= 50:
        return "warm"
    return "cold"


def _trim_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "n/a", "—"}:
        return None
    return text


_PROFILE_FIELDS_BLOCK = (
    "Поля профиля, которыми ты можешь предлагать изменения:\n"
    "- display_name (string)\n"
    "- age_range (одно из: <18, 18-24, 25-34, 35-44, 45-54, 55+)\n"
    "- business_size (одно из: solo, small, medium, large)\n"
    "- service_description (свободный текст что продаёт)\n"
    "- home_region (string)\n"
    "- niches (массив строк, 1-7 штук)"
)


def _assistant_personal_system_prompt(
    user_profile: dict[str, Any] | None,
    awaiting_field: str | None = None,
    memories: list[dict[str, Any]] | None = None,
) -> str:
    """Personal-mode system prompt (floating widget on /app)."""
    profile_block = _format_user_profile(user_profile) if user_profile else ""
    awaiting_block = ""
    if awaiting_field:
        awaiting_block = (
            "\n\n=============================================="
            "\nКАКОЕ ПОЛЕ ТЫ ЖДЁШЬ ПРЯМО СЕЙЧАС"
            "\n=============================================="
            f"\nНа предыдущем ходу ты задал уточняющий вопрос про "
            f"поле «{awaiting_field}». Если короткий ответ юзера "
            "выглядит как ответ именно на этот вопрос — клади его "
            "в это поле и НИ В КАКОЕ другое. Если ответ не похож "
            "на ответ по этому полю (юзер сменил тему, задал "
            "встречный вопрос, ушёл в офтоп) — НЕ извлекай ничего "
            "и не предлагай правку профиля.\n"
        )

    surface = (
        "\n\n=============================================="
        "\nГДЕ ТЫ СЕЙЧАС РАБОТАЕШЬ — ЛИЧНЫЙ КОНТЕКСТ\n"
        "==============================================\n"
        "Это плавающий виджет внутри рабочей зоны юзера (/app).\n"
        "Юзер открыл тебя из любого экрана. Ты — главный консультант:\n"
        "1. Объясняешь продукт, скор, фичи Convioo (см. базу знаний выше).\n"
        "2. Даёшь B2B-sales-советы (ICP, сегментация, hot-rate, cold email).\n"
        "3. Помогаешь редактировать профиль когда юзер просит.\n\n"
        "Различай сценарии по сообщению юзера:\n"
        "- «что такое hot лид» / «как работает скор» → ВОПРОС, отвечаешь.\n"
        "  profile_suggestion = null.\n"
        "- «у меня все холодные, что делать» / «как описать ICP» → "
        "КОНСУЛЬТАЦИЯ. Копай детали (один вопрос за раз), потом "
        "конкретный совет. profile_suggestion = null.\n"
        "- «делаю SEO для стоматологий в Берлине» / «давай я опишу "
        "что продаю» → ПРАВКА ПРОФИЛЯ. См. блок ниже.\n"
    )

    profile_edit = (
        "\n\n=============================================="
        "\nКАК ПРАВИТЬ ПРОФИЛЬ ЮЗЕРА\n"
        "==============================================\n"
        "Только когда юзер ЯВНО описал что-то про свой бизнес или "
        "клиентов. Положи в profile_suggestion ТОЛЬКО те поля, что "
        "юзер реально упомянул (остальные — не указывай / null).\n\n"
        "ОБЯЗАТЕЛЬНОЕ ПОДТВЕРЖДЕНИЕ ПЕРЕД ЗАПИСЬЮ:\n"
        "- Не записывай молча. Сначала переформулируй своё понимание:\n"
        "  «Я правильно понял — продаёшь SEO для локальных подрядчиков "
        "в США? Записываю в профиль?»\n"
        "- profile_suggestion в этом же ответе содержит draft того что "
        "ты собираешься записать. UI покажет это юзеру как карточку, "
        "но РЕАЛЬНАЯ запись произойдёт только после подтверждения "
        "юзера в чате («да», «верно», «ок», «записывай», или явный "
        "клик).\n"
        "- Если юзер на следующем ходу пишет «нет», «не так», "
        "«поправь» — извинись коротко («Понял, переформулирую»), "
        "уточни вопросом и предложи новый вариант.\n"
        "- suggestion_summary — короткое резюме того что предлагаешь, "
        "1 предложение, на языке собеседника.\n\n"
        + _PROFILE_FIELDS_BLOCK
        + "\n\n"
        "Если юзер описывает целевой сегмент или ниши — niches это "
        "массив 1-7 коротких поисковых фраз. Не копируй всё сообщение "
        "целиком в одно поле."
    )

    json_format = (
        "\n\n=============================================="
        "\nФОРМАТ ОТВЕТА — СТРОГО ОДИН JSON БЕЗ MARKDOWN\n"
        "==============================================\n"
        'Ровно один JSON-объект без обёрток. Никаких ```json```.\n'
        '{"reply": "…", "profile_suggestion": null или объект, '
        '"suggestion_summary": "…|null", '
        '"awaiting_field": "display_name|age_range|business_size|'
        'service_description|home_region|niches|null"}'
    )

    system = (
        henry_core.base_block()
        + "\n\n"
        + henry_core.knowledge_block()
        + henry_core.memory_block(memories)
        + surface
        + profile_edit
        + json_format
    )
    if profile_block:
        system += "\n\n=============================================="
        system += "\nТЕКУЩИЙ ПРОФИЛЬ ЮЗЕРА (не выдумывай за пределами)\n"
        system += "==============================================\n"
        system += profile_block
    system += awaiting_block
    return system


def _assistant_team_system_prompt(
    team_context: dict[str, Any] | None,
    is_owner: bool,
    memories: list[dict[str, Any]] | None = None,
) -> str:
    """Team-mode system prompt.

    Same Henry persona as in personal mode — just with team context
    bolted on top. Owner additionally gets the team_suggestion shape.
    """
    ctx = team_context or {}
    team_name = ctx.get("name") or "—"
    team_description = ctx.get("description") or ""
    members: list[dict[str, Any]] = ctx.get("members") or []
    viewer_id = ctx.get("viewer_user_id")
    members_block = ""
    for m in members:
        name = m.get("name") or f"User {m.get('user_id')}"
        role = m.get("role") or "member"
        descr = m.get("description") or "(описания пока нет)"
        marker = " ← это вы" if m.get("user_id") == viewer_id else ""
        members_block += (
            f"\n- [{role}] {name}{marker} (id={m.get('user_id')}): {descr}"
        )

    team_block = (
        "\n\n=============================================="
        "\nКОМАНДНЫЙ КОНТЕКСТ\n"
        "==============================================\n"
        f"Сейчас ты в контексте команды «{team_name}».\n"
        f"Описание команды: {team_description or '(не задано)'}\n"
        f"Состав:{members_block or ' (только вы)'}\n"
        "Участников зовёшь по имени из списка выше — не путай user_id "
        "с ролью."
    )

    base = (
        henry_core.base_block()
        + "\n\n"
        + henry_core.knowledge_block()
        + henry_core.memory_block(memories)
        + team_block
    )

    if is_owner:
        owner_surface = (
            "\n\n=============================================="
            "\nТЫ ГОВОРИШЬ С OWNER-ОМ КОМАНДЫ\n"
            "==============================================\n"
            "Сценарии:\n"
            "1. ВОПРОС про продукт в командном контексте (как работает "
            "view-as-member, дедупликация лидов, роли). Отвечаешь.\n"
            "2. КОНСУЛЬТАЦИЯ по управлению — распределение ниш между "
            "участниками, как сформулировать описание команды, "
            "специализация конкретного человека.\n"
            "3. ПРАВКА ОПИСАНИЙ — owner описывает чем занимается команда "
            "или конкретный участник. Заполняешь team_suggestion.\n\n"
            "ОБЯЗАТЕЛЬНОЕ ПОДТВЕРЖДЕНИЕ ПЕРЕД ЗАПИСЬЮ:\n"
            "- Сначала переформулируй понимание: «Понял — Анна закрывает "
            "стоматологии в EU. Записать ей в описание?»\n"
            "- team_suggestion в этом ответе содержит draft. Реальная "
            "запись — только после подтверждения юзера в чате.\n\n"
            "team_suggestion поля:\n"
            "- description (string, ≤500 симв) — суть команды.\n"
            "- member_descriptions: массив "
            '{"user_id": int, "description": string ≤300 симв}. '
            "user_id строго из списка состава выше. Описание — что "
            "человек закрывает / в каких нишах / каких регионах.\n"
            "Заполняй ТОЛЬКО реально упомянутое в диалоге.\n\n"
            "ВАЖНО: личный профиль owner-а НЕ редактируется отсюда. "
            "Для этого у него есть Личное пространство — там отдельный "
            "Henry."
        )
        json_format = (
            "\n\n=============================================="
            "\nФОРМАТ ОТВЕТА — СТРОГО ОДИН JSON БЕЗ MARKDOWN\n"
            "==============================================\n"
            'Ровно один JSON-объект без обёрток.\n'
            '{"reply": "…", "team_suggestion": null или объект, '
            '"suggestion_summary": "…|null"}'
        )
        return base + owner_surface + json_format

    member_surface = (
        "\n\n=============================================="
        "\nТЫ ГОВОРИШЬ С УЧАСТНИКОМ КОМАНДЫ (не owner)\n"
        "==============================================\n"
        "Сценарии:\n"
        "1. ВОПРОС про продукт в командном контексте (что значит "
        "«лид уже взят коллегой», статусы, пометки).\n"
        "2. КОНСУЛЬТАЦИЯ по работе с лидами — конкретные советы "
        "по нише / outbound / follow-up.\n"
        "3. КООРДИНАЦИЯ — кто из коллег чем занят (опираясь на "
        "описания участников выше). Если описания нет — честно "
        "скажи «деталей по {Имя} нет, спроси у владельца команды».\n\n"
        "Личный профиль участника НЕ редактируется отсюда. Если просит "
        "обновить личные поля — отправь в Личное пространство (там "
        "отдельный Henry с правами на личный профиль). "
        "profile_suggestion = null."
    )
    json_format = (
        "\n\n=============================================="
        "\nФОРМАТ ОТВЕТА — СТРОГО ОДИН JSON БЕЗ MARKDOWN\n"
        "==============================================\n"
        'Ровно один JSON-объект без обёрток.\n'
        '{"reply": "…", "suggestion_summary": null}'
    )
    return base + member_surface + json_format


def _clean_profile_suggestion(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    allowed = {
        "display_name",
        "age_range",
        "business_size",
        "service_description",
        "home_region",
        "niches",
    }
    out: dict[str, Any] = {}
    for key in allowed:
        value = raw.get(key)
        if value is None:
            continue
        if key == "niches":
            if isinstance(value, list):
                cleaned = [
                    str(v).strip()
                    for v in value
                    if isinstance(v, str) and str(v).strip()
                ]
                if cleaned:
                    out[key] = cleaned[:7]
            continue
        text = str(value).strip()
        if text:
            out[key] = text
    return out or None


def _clean_team_suggestion(
    raw: Any, team_context: dict[str, Any] | None
) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    allowed_user_ids = {
        m.get("user_id")
        for m in (team_context or {}).get("members", [])
        if isinstance(m, dict) and isinstance(m.get("user_id"), int)
    }
    out: dict[str, Any] = {}
    description = _trim_or_none(raw.get("description"))
    if description:
        out["description"] = description[:500]
    md_raw = raw.get("member_descriptions")
    if isinstance(md_raw, list):
        cleaned: list[dict[str, Any]] = []
        for entry in md_raw:
            if not isinstance(entry, dict):
                continue
            uid = entry.get("user_id")
            descr = _trim_or_none(entry.get("description"))
            if (
                isinstance(uid, int)
                and uid in allowed_user_ids
                and descr
            ):
                cleaned.append({"user_id": uid, "description": descr[:300]})
        if cleaned:
            out["member_descriptions"] = cleaned
    return out or None


def _format_lead_for_email(lead: dict[str, Any]) -> str:
    """Compact bullet block describing a lead for the email prompt."""
    parts: list[str] = []
    if lead.get("name"):
        parts.append(f"- Название: {lead['name']}")
    if lead.get("category"):
        parts.append(f"- Категория: {lead['category']}")
    if lead.get("address"):
        parts.append(f"- Адрес: {lead['address']}")
    if lead.get("rating") is not None:
        rc = lead.get("reviews_count")
        rc_str = f" ({rc} отзывов)" if rc else ""
        parts.append(f"- Рейтинг: {lead['rating']}{rc_str}")
    if lead.get("website"):
        parts.append(f"- Сайт: {lead['website']}")
    if lead.get("score_ai") is not None:
        parts.append(f"- AI-скор: {lead['score_ai']}/100")
    if lead.get("summary"):
        parts.append(f"- Резюме: {lead['summary']}")
    if lead.get("strengths"):
        strengths = ", ".join(str(s) for s in lead["strengths"][:4])
        parts.append(f"- Сильные стороны: {strengths}")
    if lead.get("weaknesses"):
        weaknesses = ", ".join(str(s) for s in lead["weaknesses"][:4])
        parts.append(f"- Слабые стороны: {weaknesses}")
    if lead.get("advice"):
        parts.append(f"- Как презентовать (AI-совет): {lead['advice']}")
    return "\n".join(parts) if parts else "(данные о лиде минимальные)"


def _heuristic_email(
    lead: dict[str, Any],
    user_profile: dict[str, Any] | None,
    tone: str,
) -> dict[str, Any]:
    """Last-resort template for the no-API-key path.

    Generic enough to ship, specific enough that the user knows it
    came from the lead's row (name + their profession).
    """
    name = lead.get("name") or "ваша команда"
    profession = (user_profile or {}).get("profession") or "наши услуги"
    body = (
        f"Заметил {name} — выглядит интересно для нашего профиля.\n\n"
        f"Я работаю с похожими компаниями ({profession}) и хотел "
        "коротко спросить — есть ли смысл показать пример того что "
        "мы обычно делаем?\n\n"
        "Если интересно — отвечу одним сообщением, без созвонов."
    )
    return {
        "subject": f"{name} — короткое наблюдение",
        "body": body,
        "tone": tone,
    }


def _heuristic_consult(
    history: list[dict[str, str]],
    last_asked_slot: str | None = None,
) -> dict[str, Any]:
    """No-Anthropic fallback for the consultative chat.

    Slot-aware: when the previous turn asked for a specific slot
    (``last_asked_slot``), short replies are mapped only to that
    slot — never to a different one. Without that hint we keep the
    conservative behaviour of only extracting when the message is
    clearly shaped like ``<niche> in <region>``.
    """
    last_user = ""
    for message in reversed(history):
        if message["role"] == "user":
            last_user = message["content"]
            break

    text = last_user.strip()
    looks_like_question = text.endswith("?") or bool(
        re.match(
            r"^(а |и |как |что |почему |зачем |когда |где |кто |"
            r"why |how |what |when |where |who )",
            text,
            flags=re.I,
        )
    )

    niche: str | None = None
    region: str | None = None
    ideal: str | None = None
    exclusions: str | None = None

    if looks_like_question:
        # Counter-question — answer in reply, don't extract anything.
        reply = (
            "Хороший вопрос. По шагам: сначала зафиксируем нишу и "
            "город, потом уточним идеального клиента. С чего начнём?"
        )
        return {
            "reply": reply,
            "niche": None,
            "region": None,
            "ideal_customer": None,
            "exclusions": None,
            "ready": False,
            "last_asked_slot": last_asked_slot or "niche",
        }

    if last_asked_slot in {"niche", "region", "ideal_customer", "exclusions"}:
        # Slot-targeted reply: drop the whole user message into the
        # slot Henry was waiting on. Keeps the heuristic from filing
        # a region answer ("Берлин") into the niche slot.
        cleaned = text.strip(" .,!?;:")
        if cleaned:
            if last_asked_slot == "niche":
                niche = cleaned
            elif last_asked_slot == "region":
                region = cleaned
            elif last_asked_slot == "ideal_customer":
                ideal = cleaned
            elif last_asked_slot == "exclusions":
                exclusions = cleaned
    else:
        intent = _heuristic_intent(text)
        if intent["niches"]:
            niche = intent["niches"][0]
        region_match = re.search(
            r"\b(?:in|at|around|near|в)\s+([A-Za-zА-Яа-яЁё\-\s]{2,40})$",
            text,
            flags=re.I,
        )
        if region_match:
            region = region_match.group(1).strip()

    if niche and region:
        reply = (
            f"Понял — {niche} в {region}. Если хотите уточнить идеального "
            "клиента или кого исключить, напишите. Иначе можно запускать."
        )
        ready = True
        next_slot = "ideal_customer"
    elif niche:
        reply = f"Принял нишу «{niche}». В каком городе или регионе ищем?"
        ready = False
        next_slot = "region"
    elif region:
        reply = f"Регион — {region}. Какая ниша целевых клиентов?"
        ready = False
        next_slot = "niche"
    elif ideal:
        reply = "Принял описание идеального клиента. Что-то ещё уточнить?"
        ready = False
        next_slot = "exclusions"
    elif exclusions:
        reply = "Принял исключения. Можно запускать или уточнить ещё что-то?"
        ready = False
        next_slot = None
    else:
        reply = (
            "Опишите, кого ищете: ниша + город. Например: "
            "«стоматологии в Алматы»."
        )
        ready = False
        next_slot = "niche"

    return {
        "reply": reply,
        "niche": niche,
        "region": region,
        "ideal_customer": ideal,
        "exclusions": exclusions,
        "ready": ready,
        "last_asked_slot": next_slot,
    }


def _heuristic_analysis(lead: dict[str, Any]) -> LeadAnalysis:
    score = 20
    strengths: list[str] = []
    weaknesses: list[str] = []

    if lead.get("website"):
        score += 15
        strengths.append("Есть сайт — есть точка входа для аудита и предложений")
    else:
        weaknesses.append("Нет сайта или он не указан")

    if lead.get("phone"):
        score += 10
        strengths.append("Есть телефон для быстрого контакта")
    else:
        weaknesses.append("Нет телефона")

    social_links = lead.get("social_links") or {}
    if social_links:
        score += min(10, len(social_links) * 3)
        strengths.append("Есть активные соцсети")
    else:
        weaknesses.append("Не нашли соцсети")

    rating = float(lead.get("rating") or 0)
    reviews_count = int(lead.get("reviews_count") or 0)

    if rating >= 4.3:
        score += 15
        strengths.append("Высокий рейтинг в Google")
    elif 0 < rating < 3.8:
        weaknesses.append("Низкий рейтинг — можно предлагать репутационный маркетинг")

    if reviews_count >= 100:
        score += 20
        strengths.append("Много отзывов — высокий спрос и активный поток клиентов")
    elif reviews_count >= 30:
        score += 10
    elif reviews_count == 0:
        weaknesses.append("Нет отзывов — слабая репутационная витрина")

    website_meta = lead.get("website_meta") or {}
    if website_meta.get("has_pricing"):
        score += 5
    if website_meta.get("has_portfolio"):
        score += 5
    if website_meta.get("has_blog"):
        score += 5

    score = max(0, min(100, score))
    tag = _bucket_tag(score)

    advice = (
        "Начни с короткого аудита: сайт + отзывы + соцсети. "
        "Покажи 2-3 точки роста с конкретными шагами и прогнозом результата."
    )
    summary = (
        f"Компания в категории «{lead.get('category') or 'бизнес'}», "
        f"первичная оценка по открытым данным: {score}/100."
    )

    red_flags = []
    if not lead.get("website") and not lead.get("phone"):
        red_flags.append("Очень мало контактов — высокий риск низкой конверсии")

    return LeadAnalysis(
        score=score,
        tags=[tag, "heuristic"],
        summary=summary,
        advice=advice,
        strengths=strengths[:4],
        weaknesses=weaknesses[:4],
        red_flags=red_flags,
        error="anthropic_api_key_missing",
    )


class AIAnalyzer:
    """Async wrapper around the Anthropic Messages API with heuristic fallback."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        concurrency: int | None = None,
    ) -> None:
        _settings = get_settings()
        resolved_key = _settings.anthropic_api_key if api_key is None else api_key
        self.api_key = resolved_key.strip()
        # Explicit max_retries so transient 5xx / 429 / connection errors
        # bounce back automatically before we hit our own except branch.
        # Default SDK timeout is 10 minutes which is far too lenient for
        # an interactive chat — Henry has to feel snappy or look broken.
        self.client = (
            AsyncAnthropic(api_key=self.api_key, max_retries=2, timeout=45.0)
            if self.api_key
            else None
        )
        self.model = model or _settings.anthropic_model
        self._sem = asyncio.Semaphore(concurrency or _settings.enrich_concurrency)

    @staticmethod
    def _classify_anthropic_error(exc: BaseException) -> tuple[str, str]:
        """Map an Anthropic SDK exception to (slug, ru_label).

        slug feeds logs / metrics; ru_label is what we surface in the
        chat reply so the user sees something concrete instead of
        "не удалось получить ответ".
        """
        if isinstance(exc, RateLimitError):
            return ("rate_limit", "лимит запросов")
        if isinstance(exc, APITimeoutError):
            return ("timeout", "таймаут")
        if isinstance(exc, InternalServerError):
            return ("overloaded", "сервер AI перегружен")
        if isinstance(exc, APIConnectionError):
            return ("network", "проблема со связью")
        if isinstance(exc, APIStatusError):
            return (f"http_{exc.status_code}", f"ошибка {exc.status_code}")
        return ("unknown", "что-то пошло не так")

    async def analyze_lead(
        self,
        lead: dict[str, Any],
        niche: str,
        region: str,
        user_profile: dict[str, Any] | None = None,
    ) -> LeadAnalysis:
        if self.client is None:
            return _heuristic_analysis(lead)

        async with self._sem:
            try:
                context = _build_lead_context(lead, niche, region)
                system_prompt = _build_system_prompt(user_profile)
                msg = await self.client.messages.create(
                    model=self.model,
                    max_tokens=900,
                    system=system_prompt,
                    messages=[{"role": "user", "content": context}],
                )
                text = msg.content[0].text  # type: ignore[union-attr]
                data = _extract_json(text)
                return LeadAnalysis(
                    score=int(data.get("score", 0) or 0),
                    tags=[str(t) for t in (data.get("tags") or [])],
                    summary=str(data.get("summary") or ""),
                    advice=str(data.get("advice") or ""),
                    strengths=[str(s) for s in (data.get("strengths") or [])],
                    weaknesses=[str(s) for s in (data.get("weaknesses") or [])],
                    red_flags=[str(s) for s in (data.get("red_flags") or [])],
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("AI analyze_lead failed for %s", lead.get("name"))
                heuristic = _heuristic_analysis(lead)
                heuristic.error = str(exc)
                return heuristic

    async def analyze_batch(
        self,
        leads: list[dict[str, Any]],
        niche: str,
        region: str,
        user_profile: dict[str, Any] | None = None,
        progress_callback: Any = None,
    ) -> list[LeadAnalysis]:
        if not leads:
            return []

        async def indexed(i: int, ctx: dict[str, Any]) -> tuple[int, LeadAnalysis]:
            result = await self.analyze_lead(
                ctx, niche, region, user_profile=user_profile
            )
            return i, result

        tasks = [asyncio.create_task(indexed(i, c)) for i, c in enumerate(leads)]
        results: list[LeadAnalysis | None] = [None] * len(leads)
        total = len(leads)
        for done, coro in enumerate(asyncio.as_completed(tasks), start=1):
            i, result = await coro
            results[i] = result
            if progress_callback is not None:
                try:
                    await progress_callback(done, total)
                except Exception:  # noqa: BLE001
                    logger.exception("analyze_batch progress_callback raised")
        return [r for r in results if r is not None]

    async def _short_completion(self, system: str, user_text: str, max_tokens: int = 60) -> str | None:
        """Small helper for single-field extraction prompts.

        Returns the stripped response text, or ``None`` if the LLM is
        unavailable or the call fails. Callers decide how to interpret the
        result (strict match vs. best-effort).
        """
        if self.client is None:
            return None
        try:
            async with self._sem:
                msg = await self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user_text}],
                )
                out = "".join(getattr(block, "text", "") for block in msg.content).strip()
                return out or None
        except Exception:  # noqa: BLE001
            logger.exception("short-completion call failed")
            return None

    async def parse_name(self, text: str) -> str | None:
        """Extract a display name from free-form text.

        Examples:
        - ``"Саша"`` → ``"Саша"``
        - ``"меня зовут Алексей"`` → ``"Алексей"``
        - ``"называй меня Марк пожалуйста"`` → ``"Марк"``
        """
        text = (text or "").strip()
        if not text:
            return None

        # Fast path: bare name or very short input — use as-is (trimmed).
        stripped = _strip_patterns(text, _NAME_PREFIX_PATTERNS)
        # Trim trailing politeness: "Марк пожалуйста" → "Марк"
        stripped = re.sub(r"[,\s]*(пожалуйста|плиз|please|спасибо)\.?\s*$", "", stripped, flags=re.IGNORECASE).strip()
        if 2 <= len(stripped) <= 40 and " " not in stripped.strip(".,!?;:"):
            return stripped.strip(".,!?;:")

        # Slow path: ask Claude for the actual name.
        system = (
            "Извлеки из сообщения пользователя имя, которым он просит его "
            "называть. Верни ТОЛЬКО имя: без кавычек, без пояснений, без "
            "префиксов «имя:» и т.п. Если имя не указано — верни слово null. "
            "Максимум 40 символов."
        )
        ai = await self._short_completion(system, text, max_tokens=40)
        if ai:
            candidate = ai.strip().strip('"\'«»').strip(".,!?;:")
            if candidate and candidate.lower() != "null" and 1 <= len(candidate) <= 40:
                return candidate

        # Final fallback: truncate the original input.
        return text[:40] if text else None

    async def parse_age(self, text: str) -> str | None:
        """Extract an age-range code ('<18' / '18-24' / ... / '55+') from text.

        Returns ``None`` if the text doesn't plausibly express an age.
        """
        text = (text or "").strip()
        if not text:
            return None

        # Fast path: an explicit number.
        match = re.search(r"\b(\d{1,3})\b", text)
        if match:
            code = _age_from_number(int(match.group(1)))
            if code:
                return code

        # Direct range string match.
        for code in _AGE_RANGE_CODES:
            if code in text:
                return code

        # LLM fallback.
        system = (
            "Определи возраст или возрастную группу человека из текста. "
            "Верни СТРОГО один из кодов без кавычек и пояснений: "
            "<18, 18-24, 25-34, 35-44, 45-54, 55+. "
            "Если возраст неясен или пользователь отказался — верни слово null."
        )
        ai = await self._short_completion(system, text, max_tokens=10)
        if ai:
            code = ai.strip().strip(".,!?").lower()
            if code in _AGE_RANGE_CODES:
                return code
        return None

    async def parse_business_size(self, text: str) -> str | None:
        """Extract a business-size code (solo/small/medium/large) from text."""
        text = (text or "").strip()
        if not text:
            return None
        low = text.lower()

        # Number-of-people heuristic.
        match = re.search(r"\b(\d{1,5})\s*(?:чел|сотр|person|people|human)", low)
        if match:
            return _biz_from_headcount(int(match.group(1)))
        # Direct small number implies headcount when context hints at "team"
        if re.search(r"\b(команд|team|компани)", low):
            num = re.search(r"\b(\d{1,5})\b", low)
            if num:
                return _biz_from_headcount(int(num.group(1)))

        # Keyword match (order matters — longer phrases first).
        for code, keywords in _BIZ_KEYWORDS:
            if any(kw in low for kw in keywords):
                return code

        # Direct code match.
        for code in _BUSINESS_SIZE_CODES:
            if low == code or low.startswith(code):
                return code

        # LLM fallback.
        system = (
            "Определи размер бизнеса пользователя из текста. Верни СТРОГО "
            "один из кодов без кавычек: solo (соло/фрилансер, 1 чел), "
            "small (малая команда 2–10 чел), medium (компания 10–50 чел), "
            "large (крупный бизнес 50+ чел). Если размер неясен — null."
        )
        ai = await self._short_completion(system, text, max_tokens=10)
        if ai:
            code = ai.strip().strip(".,!?").lower()
            if code in _BUSINESS_SIZE_CODES:
                return code
        return None

    async def parse_region(self, text: str) -> str | None:
        """Extract a city/region/country name from free-form text."""
        text = (text or "").strip()
        if not text:
            return None

        stripped = _strip_patterns(text, _REGION_PREFIX_PATTERNS)
        # Short token after stripping → use directly.
        if 2 <= len(stripped) <= 60 and stripped.count(" ") <= 3:
            return stripped.rstrip(".,!?;:")

        # Ask Claude to normalise a longer sentence.
        system = (
            "Извлеки из текста название города, региона или страны, в котором "
            "человек ищет клиентов. Верни ТОЛЬКО название без предлогов, "
            "без пояснений, без кавычек. Максимум 80 символов. "
            "Если несколько мест — основное. Если нет — слово null."
        )
        ai = await self._short_completion(system, text, max_tokens=30)
        if ai:
            candidate = ai.strip().strip('"\'«»').strip(".,!?;:")
            if candidate and candidate.lower() != "null" and 2 <= len(candidate) <= 100:
                return candidate

        # Fallback: truncated original.
        return text[:100] if text else None

    async def normalize_profession(self, text: str) -> str:
        """Rewrite a user's self-description into a tight, well-formed sentence.

        The user might type something like
        "Мы им начинающее агентство Seventy Times мы разрабатываем сайты
        настраиваем таргетированную рекламу создаем и ботов и автоматизации
        для процессов бизнеса" — we persist this as-is in
        ``service_description`` (user's own words) but use the normalised
        version as ``profession`` in every AI prompt. Cleaner input →
        tighter AI output → better lead recommendations.

        Without an Anthropic key we return the trimmed original — the rest
        of the pipeline is designed to survive raw text anyway.
        """
        text = (text or "").strip()
        if not text:
            return text

        if self.client is None:
            return text

        system = (
            "Ты — редактор. Тебе приходит описание профессии или услуги, "
            "которое пользователь написал сам — часто со сбитой грамматикой "
            "и пунктуацией. Перепиши этот текст в 1–2 чёткие предложения, "
            "сохранив ВСЕ детали: название компании/бренда, конкретные "
            "услуги, формат работы. Не добавляй того, чего нет в оригинале, "
            "не убирай суть. Пиши на том же языке, что и оригинал. "
            "Верни ТОЛЬКО переписанный текст, без пояснений, без кавычек, "
            "без префиксов «вот переписанное:» и т.п."
        )
        rewritten = await self._short_completion(system, text, max_tokens=300)
        if not rewritten:
            return text
        # Trim common wrapping artefacts.
        cleaned = rewritten.strip().strip('"\'«»').strip()
        if not cleaned:
            return text
        # Guard against the model ignoring instructions and returning a blob.
        if len(cleaned) > len(text) * 2 + 100:
            return text
        return cleaned

    async def extract_search_intent(self, description: str) -> dict[str, Any]:
        """Parse a free-form user description into structured search niches + region.

        Returns ``{"niches": [...], "region": str | None, "error": str | None}``.
        Always returns at least one niche if the description is non-empty,
        falling back to a heuristic comma/newline split when the LLM is
        unavailable.
        """
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
            # Model returned empty list — fall back to heuristic rather than
            # leaving the user stuck.
            return _heuristic_intent(text)
        return {"niches": niches, "region": region, "error": None}

    async def consult_search(
        self,
        history: list[dict[str, str]],
        user_profile: dict[str, Any] | None = None,
        current_state: dict[str, Any] | None = None,
        last_asked_slot: str | None = None,
    ) -> dict[str, Any]:
        """One turn of a consultative dialogue for the search composer.

        ``history`` is the full ordered conversation so far. Each item
        ``{"role": "user" | "assistant", "content": "..."}``.

        ``current_state`` carries the slot values the frontend already
        shows in the form (so Claude doesn't re-extract from scratch
        and accidentally clobber a settled answer with stray phrases
        from the latest user reply). Keys: niche, region,
        ideal_customer, exclusions.

        ``last_asked_slot`` is the slot Henry's previous turn was
        waiting on (echoed by the client). Used to map a short reply
        to the correct slot instead of guessing — and to keep the
        heuristic fallback from misfiling a region as a niche.

        Returns the next assistant message + the up-to-date best
        guess for every slot + a ``ready`` flag (niche AND region
        known) + the new ``last_asked_slot`` for the next turn.
        """
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
            return {
                "reply": (
                    "Привет — расскажите, кого ищете: какая ниша, "
                    "в каком городе или регионе, и что именно делает "
                    "идеального клиента для вас."
                ),
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
            # Don't let the heuristic blank out values the user
            # already confirmed earlier in the dialogue.
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
            "ОСИ КОТОРЫЕ НУЖНО ПРОЯСНИТЬ:\n"
            "1. niche — конкретный тип бизнеса (2-5 слов). Не «B2B», "
            "не «малый бизнес». «Стоматологическая клиника», "
            "«барбершоп».\n"
            "2. region — конкретный город. «Берлин», «Stamford, CT». "
            "Не страна, не «вся Европа». Если дают страну — переспроси "
            "первый город для старта.\n"
            "3. ideal_customer — 1-3 предложения с конкретикой "
            "(размер бизнеса, ценовой сегмент, рейтинг, цифровая "
            "зрелость, триггеры покупки).\n"
            "4. exclusions — кого не нужно (сети, франшизы, "
            "уже отработанный сегмент).\n\n"
            "ХОРОШИЙ FLOW:\n"
            "Юзер: «Я ищу стоматологии».\n"
            "Ты: «Понял. В каком городе стартуем — и какой типичный "
            "успешный клиент у вас был, премиум или средний?» "
            "(last_asked_slot=region)\n"
            "Юзер: «Берлин, премиум».\n"
            "Ты: «Принял — премиум-стоматология в Берлине. По чему "
            "лид считается горячим: рейтинг 4.5+, активный сайт, "
            "соцсети — что важно? И кого избегаем — сети, франшизы?» "
            "(last_asked_slot=ideal_customer)\n"
            "Юзер: «А что значит горячий лид?»\n"
            "Ты: «Лид с AI-скором ≥75 — сравниваем сайт, отзывы, "
            "соцсети с вашим профилем. Так что важно для вас — "
            "рейтинг, размер, что-то ещё?» "
            "(slots не трогаем, last_asked_slot остаётся "
            "ideal_customer)\n\n"
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
            return _heuristic_consult(clean_history)

        # Belt-and-braces: never let a turn drop a slot the user
        # already confirmed. Even with the explicit prompt rule above,
        # Claude occasionally returns null on a settled field — we
        # carry the previous value forward instead of clearing it.
        next_niche = _trim_or_none(data.get("niche")) or carried_niche
        next_region = _trim_or_none(data.get("region")) or carried_region
        next_ideal = (
            _trim_or_none(data.get("ideal_customer")) or carried_ideal
        )
        next_exclusions = (
            _trim_or_none(data.get("exclusions")) or carried_exclusions
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
        """One round-trip of the floating in-product assistant chat.

        Two distinct modes driven by ``team_context``:

        - **Personal** (``team_context`` is None) — Henry helps the
          user with their personal profile and product questions.
          Returns ``profile_suggestion`` when applicable.
        - **Team** (``team_context`` populated) — Henry takes on a
          team-coordinator persona. He knows the team's purpose +
          every member's role description and helps the caller work
          inside the team. Personal-profile editing is disabled here
          (members keep their own personal workspace for that).
          Owners additionally get ``team_suggestion`` so they can
          fill in / refine the team and member descriptions.
        """
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
            system = _assistant_team_system_prompt(
                team_context, is_owner, memories=memories
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
                # team_context can be None in personal mode; use a safe lookup
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
        """Distill a recent dialogue into one summary + 0-5 facts.

        Output shape: ``{"summary": str | None, "facts": list[str]}``.
        Both are bounded so a single noisy session can't blow up the
        memory store. Empty / no-API-key path returns no-ops.
        """
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

    async def generate_cold_email(
        self,
        lead: dict[str, Any],
        user_profile: dict[str, Any] | None = None,
        tone: str = "professional",
        extra_context: str | None = None,
    ) -> dict[str, Any]:
        """Draft a personalised cold email for one lead.

        Returns ``{"subject": str, "body": str, "tone": str}``. The
        prompt is a senior B2B copywriter — short, value-first, one
        soft CTA, no clichés. Heuristic fallback returns a generic
        template so the UI doesn't break when the API key is missing.
        """
        clean_tone = (tone or "professional").strip().lower()
        if clean_tone not in {"professional", "casual", "bold"}:
            clean_tone = "professional"

        if self.client is None:
            return _heuristic_email(lead, user_profile, clean_tone)

        profile_block = _format_user_profile(user_profile) if user_profile else ""
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
            "6. Язык письма = язык/локализация лида и продажника. "
            "Если профиль продажника по-русски и лид в русскоязычном "
            "регионе — пиши по-русски. Если лид в Берлине и "
            "профиль не русскоязычный — пиши по-английски (это "
            "стандарт для DACH B2B).\n"
            f"7. {tone_hint}\n\n"
            "==============================================\n"
            "ФОРМАТ ОТВЕТА — СТРОГО JSON БЕЗ MARKDOWN\n"
            "==============================================\n"
            '{"subject": "…", "body": "…"}'
        )
        if profile_block:
            system += "\n\nПРОФИЛЬ ПРОДАЖНИКА:\n" + profile_block
        system += "\n\nЛИД:\n" + lead_block + extra_block

        try:
            async with self._sem:
                msg = await self.client.messages.create(
                    model=self.model,
                    max_tokens=600,
                    system=system,
                    messages=[
                        {
                            "role": "user",
                            "content": (
                                "Напиши письмо для этого лида. "
                                "Отвечай только JSON-ом."
                            ),
                        }
                    ],
                )
                raw = msg.content[0].text  # type: ignore[union-attr]
                data = _extract_json(raw) or {}
        except Exception:  # noqa: BLE001
            logger.exception("generate_cold_email failed")
            return _heuristic_email(lead, user_profile, clean_tone)

        subject = _trim_or_none(data.get("subject")) or ""
        body = _trim_or_none(data.get("body")) or ""
        if not subject or not body:
            return _heuristic_email(lead, user_profile, clean_tone)
        return {"subject": subject, "body": body, "tone": clean_tone}

    async def base_insights(
        self,
        analysed_leads: list[dict[str, Any]],
        niche: str,
        region: str,
        user_profile: dict[str, Any] | None = None,
    ) -> str:
        """Produce a high-level analytical summary over the entire base."""
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
