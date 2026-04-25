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

from anthropic import AsyncAnthropic

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
) -> str:
    profile_block = _format_user_profile(user_profile) if user_profile else ""
    system = (
        "Ты — Henry, встроенный консультант сервиса Convioo. "
        "Веди себя как живой человек: профессионально, по-деловому, "
        "коротко. Никогда не упоминай что ты ИИ.\n\n"
        "Что входит в твою зону ответственности:\n"
        "1. Подбор B2B-клиентов из Google Maps: ниши, регионы, "
        "критерии оценки лидов.\n"
        "2. Помощь с заполнением рабочего профиля пользователя: "
        "имя, возрастная категория, размер бизнеса, что он продаёт, "
        "домашний регион, целевые ниши.\n"
        "3. Объяснение продукта: hot/warm/cold-скоры, как работает "
        "анализ, что такое сессия, что делает команда.\n\n"
        "Жёсткие рамки:\n"
        "- Не обсуждай ничего вне Convioo-контекста (погода, политика, "
        "программирование, личная жизнь, общая болтовня). Коротко "
        "вежливо откажись и верни диалог к делу.\n"
        "- Не запрашивай конфиденциальные данные (паспорт, банковские "
        "реквизиты, пароли, телефон, точный адрес). Профиль — "
        "бизнес-описание, не персональные данные.\n"
        "- Не выдумывай. Если деталей не хватает — спроси.\n"
        "- Один уточняющий вопрос за раз. 1–4 предложения. Язык "
        "собеседника. Без markdown, без эмодзи.\n\n"
        "Когда из разговора стало ясно, какое значение пользователь "
        "хочет видеть в одном или нескольких полях профиля — "
        "положи их в ``profile_suggestion`` (только реально обозначенные "
        "поля, остальное — null). Пользователь увидит карточку "
        "«Применить» и подтвердит. ``suggestion_summary`` — короткое "
        "описание изменений на языке собеседника.\n\n"
        + _PROFILE_FIELDS_BLOCK
        + "\n\nФормат ответа — СТРОГО JSON без markdown:\n"
        '{"reply": "…", "profile_suggestion": null или объект с '
        'указанными выше полями, "suggestion_summary": "…|null"}'
    )
    if profile_block:
        system += "\n\nТекущий профиль пользователя:\n" + profile_block
    return system


def _assistant_team_system_prompt(
    team_context: dict[str, Any] | None,
    is_owner: bool,
) -> str:
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

    base = (
        f"Ты — Henry, встроенный консультант сервиса Convioo. "
        "Веди себя как живой человек: профессионально, по-деловому, "
        "коротко. Никогда не упоминай что ты ИИ.\n\n"
        f"Сейчас ты работаешь в контексте команды «{team_name}».\n"
        f"Описание команды: {team_description or '(описание команды ещё не задано)'}\n"
        f"Состав команды:{members_block or ' (членов кроме вас пока нет)'}\n\n"
    )

    if is_owner:
        return base + (
            "Вы говорите с владельцем команды. Ваши задачи:\n"
            "1. Помогать организовывать работу команды: какие ниши кому "
            "поручить, как объяснить роли, как описать команду, чтобы "
            "новые участники сразу понимали зачем она.\n"
            "2. Предлагать апдейты для team.description и описаний "
            "конкретных участников через ``team_suggestion``.\n"
            "3. Объяснять как работает командный CRM, дедупликация лидов "
            "(один лид = один член команды), и view-as-member.\n\n"
            "Жёсткие рамки:\n"
            "- Никаких изменений личного профиля владельца (для этого у "
            "него отдельное Личное пространство). В команде ты работаешь "
            "только с командными полями.\n"
            "- Не обсуждай ничего вне темы Convioo.\n"
            "- Не запрашивай конфиденциальные данные участников.\n"
            "- Один уточняющий вопрос за раз. 1–4 предложения. Язык "
            "собеседника. Без markdown, без эмодзи.\n\n"
            "Когда из разговора понятно как стоит обновить описание "
            "команды или описание конкретных участников — положи их в "
            "``team_suggestion``. Поля:\n"
            "- description (string) — короткое описание команды (до 500 "
            "символов).\n"
            "- member_descriptions (массив объектов "
            '{"user_id": int, "description": string}) — короткие '
            "описания участников (до 300 символов каждое). user_id — "
            "из списка состава команды выше.\n"
            "Пользователь увидит карточку «Применить» и сам подтвердит. "
            "``suggestion_summary`` — короткое резюме изменений.\n\n"
            "Формат ответа — СТРОГО JSON без markdown:\n"
            '{"reply": "…", "team_suggestion": null или объект, '
            '"suggestion_summary": "…|null"}'
        )

    return base + (
        "Вы говорите с участником команды (не владельцем). Ваши задачи:\n"
        "1. Помогать с рабочими вопросами в контексте этой команды: "
        "как лучше отработать сегмент, кого из коллег спросить, какие "
        "ниши уже закрыты другими.\n"
        "2. Объяснять продукт: hot/warm/cold, как работает оценка, "
        "что такое сессия, как использовать пометки и статусы.\n"
        "3. Поддерживать координацию: подсказывать кому в команде "
        "поручены смежные задачи (опираясь на описания участников выше).\n\n"
        "Жёсткие рамки:\n"
        "- Личный профиль участника НЕ редактируется в командном режиме. "
        "Если участник просит обновить личные поля — скажи, что для "
        "этого есть Личное пространство, и предложи переключиться.\n"
        "- Не обсуждай ничего вне темы Convioo.\n"
        "- Не выдумывай факты о коллегах сверх того что в описаниях выше.\n"
        "- Не запрашивай конфиденциальные данные.\n"
        "- Один уточняющий вопрос за раз. 1–4 предложения. Язык "
        "собеседника. Без markdown, без эмодзи.\n\n"
        "Формат ответа — СТРОГО JSON без markdown:\n"
        '{"reply": "…", "suggestion_summary": null}'
    )


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


def _heuristic_consult(history: list[dict[str, str]]) -> dict[str, Any]:
    """No-Anthropic fallback for the consultative chat.

    Pulls the latest user message through ``_heuristic_intent`` to
    grab a niche, looks for an "in <region>" pattern, and returns a
    plain assistant prompt asking for whatever's still missing.
    """
    last_user = ""
    for message in reversed(history):
        if message["role"] == "user":
            last_user = message["content"]
            break

    intent = _heuristic_intent(last_user)
    niche = intent["niches"][0] if intent["niches"] else None
    region: str | None = None
    region_match = re.search(
        r"\b(?:in|at|around|near|в)\s+([A-Za-zА-Яа-яЁё\-\s]{2,40})$",
        last_user.strip(),
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
    elif niche:
        reply = (
            f"Принял нишу «{niche}». В каком городе или регионе ищем?"
        )
        ready = False
    elif region:
        reply = (
            f"Регион — {region}. Какая ниша целевых клиентов?"
        )
        ready = False
    else:
        reply = (
            "Опишите, кого ищете: ниша + город. Например: "
            "«стоматологии в Алматы»."
        )
        ready = False

    return {
        "reply": reply,
        "niche": niche,
        "region": region,
        "ideal_customer": None,
        "exclusions": None,
        "ready": ready,
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
        self.client = AsyncAnthropic(api_key=self.api_key) if self.api_key else None
        self.model = model or _settings.anthropic_model
        self._sem = asyncio.Semaphore(concurrency or _settings.enrich_concurrency)

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
    ) -> dict[str, Any]:
        """One turn of a consultative dialogue for the search composer.

        ``history`` is the full ordered conversation so far. Each item
        ``{"role": "user" | "assistant", "content": "..."}``.

        ``current_state`` carries the slot values the frontend already
        shows in the form (so Claude doesn't re-extract from scratch
        and accidentally clobber a settled answer with stray phrases
        from the latest user reply). Keys: niche, region,
        ideal_customer, exclusions.

        Returns the next assistant message + the up-to-date best
        guess for every slot + a ``ready`` flag (niche AND region
        known). Heuristic fallback covers the no-API-key case.
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
            }

        if self.client is None:
            fallback = _heuristic_consult(clean_history)
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
            "\n\nТЕКУЩЕЕ СОСТОЯНИЕ ФОРМЫ (уже извлечено и видно "
            "пользователю справа):\n"
            f"- niche: {carried_niche or 'null'}\n"
            f"- region: {carried_region or 'null'}\n"
            f"- ideal_customer: {carried_ideal or 'null'}\n"
            f"- exclusions: {carried_exclusions or 'null'}\n"
            "Эти значения УЖЕ записаны в форме. Не перезаписывай их, "
            "если пользователь явно не поправляет соответствующее поле. "
            "Если поле уже заполнено и пользователь не упоминает его — "
            "верни тот же текст что в текущем состоянии (не null).\n"
        )
        system = (
            "Ты — Henry, AI-консультант сервиса Convioo. "
            "Веди себя как живой человек: профессионально, по-деловому, "
            "но без формальностей. Никогда не упоминай что ты ИИ. "
            "Помогаешь B2B-продажнику собрать поисковый запрос для "
            "Google Maps: короткий живой диалог, по одному вопросу за раз. "
            "Цель — вытянуть нишу клиентов, регион и важные детали о "
            "том, кто идеальный лид и кого исключить.\n\n"
            "Жёсткие рамки:\n"
            "- Ты строго в теме лидогенерации и подбора B2B-клиентов "
            "из Google Maps. Если пользователь начинает говорить о чём-то "
            "вне темы (погода, политика, общие вопросы, программирование, "
            "анекдоты, личная жизнь, что угодно за пределами подбора "
            "лидов) — коротко, вежливо, по-человечески откажи и верни "
            "разговор к настройке поиска. Не вступай в обсуждение.\n"
            "- Не выдумывай факты о пользователе. Если деталей нет — "
            "просто спроси.\n\n"
            "КАК РАЗБИРАТЬ ОТВЕТЫ ПОЛЬЗОВАТЕЛЯ (важно):\n"
            "- Помни какой вопрос ты только что задал. Если в твоей "
            "последней реплике ты спросил про регион — ответ "
            "пользователя относится к региону, не к нише. Аналогично "
            "для ideal_customer и exclusions.\n"
            "- Если пользователь говорит «давай для примера город "
            "Х» / «возьмём город Х» / «начнём с Х» — это явное "
            "указание региона = X. Извлекай именно конкретный город, "
            "не абстрактный охват «вся Европа».\n"
            "- niche должен быть КОРОТКИМ, в форме поискового запроса "
            "Google Maps (например «full-stack marketing agency», "
            "«стоматология», «кофейня»). Не вставляй в niche целое "
            "сообщение пользователя дословно. Извлеки СУТЬ.\n"
            "- region — конкретный город или регион (например "
            '"Stamford, Connecticut" или "Berlin"). Не «вся Европа», '
            "не «вся Америка» — это слишком абстрактно для Google Maps. "
            "Если пользователь даёт большой охват — переспроси конкретный "
            "город для старта.\n"
            "- НИКОГДА не клади в niche текст-ответ на вопрос про регион "
            "(или наоборот). Когда сомневаешься — оставь поле как есть "
            "в текущем состоянии формы.\n\n"
            "Правила диалога:\n"
            "- Веди себя как опытный консультант, не как форма. Задавай "
            "по одному уточняющему вопросу за раз, реагируй на ответы.\n"
            "- 1–3 предложения за реплику. Без markdown, без эмодзи.\n"
            "- Используй язык собеседника (русский / английский / "
            "украинский — что писал пользователь).\n"
            "- Если уже понятна и ниша и регион — спроси про идеального "
            "клиента (размер, ценовой сегмент, на что обратить внимание) "
            "или про исключения. Когда деталей хватает, кратко резюмируй "
            "и предложи запустить поиск.\n"
            "- ready=true ставишь только когда есть И ниша, И регион "
            "(конкретный город/регион, не размытый континент). "
            "ideal_customer и exclusions — приветствуются, но не "
            "обязательны.\n\n"
            "Формат ответа — СТРОГО JSON, без префиксов и markdown.\n"
            "Возвращай ВСЕ четыре слота на каждом ходу: если поле уже "
            "было заполнено в текущем состоянии и пользователь его не "
            "трогал — повтори то же значение, не ставь null.\n"
            '{"reply": "…", "niche": "…|null", "region": "…|null", '
            '"ideal_customer": "…|null", "exclusions": "…|null", '
            '"ready": true|false}'
        )
        system += state_block
        if profile_block:
            system += "\nПрофиль продавца, под которого подбираем лидов:\n"
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
        }

    async def assistant_chat(
        self,
        history: list[dict[str, str]],
        user_profile: dict[str, Any] | None = None,
        team_context: dict[str, Any] | None = None,
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

        empty_response: dict[str, Any] = {
            "reply": "",
            "mode": mode,
            "profile_suggestion": None,
            "team_suggestion": None,
            "suggestion_summary": None,
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
            system = _assistant_team_system_prompt(team_context, is_owner)
        else:
            system = _assistant_personal_system_prompt(user_profile)

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
        except Exception:  # noqa: BLE001
            logger.exception("assistant_chat failed")
            return {
                "reply": "Не удалось получить ответ. Попробуйте ещё раз.",
                "mode": mode,
                "profile_suggestion": None,
                "team_suggestion": None,
                "suggestion_summary": None,
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

        return {
            "reply": str(data.get("reply") or "").strip()
            or "Расскажите подробнее, чтобы я мог помочь.",
            "mode": mode,
            "profile_suggestion": profile_suggestion,
            "team_suggestion": team_suggestion,
            "suggestion_summary": _trim_or_none(data.get("suggestion_summary")),
        }

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
