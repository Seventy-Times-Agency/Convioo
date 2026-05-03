"""Module-level helpers and constants shared by AIAnalyzer mixins.

Extracted from the original monolithic ``ai_analyzer.py`` so each
mixin file (parsers / scoring / tagging / advice / research /
email_drafting) can import these without circular dependencies.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "LeadAnalysis",
    "_extract_json",
    "_NICHE_MIN",
    "_NICHE_MAX",
    "_NICHE_LIMIT",
    "_AGE_RANGE_CODES",
    "_BUSINESS_SIZE_CODES",
    "_NAME_PREFIX_PATTERNS",
    "_REGION_PREFIX_PATTERNS",
    "_BIZ_KEYWORDS",
    "_age_from_number",
    "_biz_from_headcount",
    "_strip_patterns",
    "_clean_niches",
    "_heuristic_intent",
    "_bucket_tag",
    "_trim_or_none",
    "_clean_profile_suggestion",
    "_clean_team_suggestion",
    "_format_lead_for_email",
    "_heuristic_email",
    "_heuristic_consult",
    "_heuristic_analysis",
]


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
    """Fallback niche extraction when no LLM is available."""
    chunks = re.split(r"[,\n;]|\s+(?:и|или|а также)\s+", description, flags=re.I)
    niches = _clean_niches(chunks)
    if not niches:
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
    """Last-resort template for the no-API-key path."""
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
    """No-Anthropic fallback for the consultative chat."""
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
