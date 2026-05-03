"""Lead-analysis system prompt + lead-context builder.

Static prompt strings + the helpers that interpolate user profile and
per-lead data. Originally inline in ``ai_analyzer.py``.
"""

from __future__ import annotations

from typing import Any

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

Опирайся на канонические B2B-фреймворки (используй их МЫСЛЕННО, не упоминай
названия в ответе):
- BANT — есть ли у лида бюджет (рост, кол-во отзывов, премиум-сегмент),
  authority (это владелец или сетевая точка), need (видна ли боль на
  сайте/в отзывах), timing (свежие изменения — переезд, ребрендинг).
- MEDDIC — пробуй понять метрики (рейтинг, отзывы, число локаций),
  кто экономический покупатель, есть ли явная identified pain, кто
  потенциальный champion.
- Jobs-To-Be-Done — какой результат бизнес «нанимает» услугу решать.
  Если услуга юзера не решает работу, которая болит у этого лида —
  это снижает скор сильнее, чем шероховатости профиля.
- ICP-fit: вес сильнее всего у совпадения ниши / размера бизнеса /
  региона юзера, а не у косметики (красивый сайт ≠ горячий лид).
- Unit-economics: чем больше lifetime value одной сделки в этой нише,
  тем выше можно поднять скор пограничного лида (юзер больше готов
  поработать над ним). Не пиши конкретные цифры, но учитывай.

Пиши кратко и по делу. Используй русский язык."""


_BUSINESS_SIZE_LABEL = {
    "solo": "соло / фрилансер",
    "small": "малая команда (2–10 чел.)",
    "medium": "компания (10–50 чел.)",
    "large": "крупный бизнес (50+ чел.)",
}


_PROFILE_FIELDS_BLOCK = (
    "Поля профиля, которыми ты можешь предлагать изменения:\n"
    "- display_name (string)\n"
    "- age_range (одно из: <18, 18-24, 25-34, 35-44, 45-54, 55+)\n"
    "- business_size (одно из: solo, small, medium, large)\n"
    "- service_description (свободный текст что продаёт)\n"
    "- home_region (string)\n"
    "- niches (массив строк, 1-7 штук)"
)


def _format_user_profile(profile: dict[str, Any] | None) -> str:
    if not profile:
        return ""
    parts = ["\n\nПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ (кто спрашивает):"]
    if profile.get("display_name"):
        parts.append(f"- Имя: {profile['display_name']}")
    if profile.get("age_range"):
        parts.append(f"- Возраст: {profile['age_range']}")
    gender = profile.get("gender")
    if gender == "male":
        parts.append(
            "- Пол: мужской → обращайся в мужском роде "
            "(он, готов, увидел, сказал, добавил)."
        )
    elif gender == "female":
        parts.append(
            "- Пол: женский → обращайся в женском роде "
            "(она, готова, увидела, сказала, добавила)."
        )
    elif gender == "other":
        parts.append(
            "- Пол: не определён → используй гендерно-нейтральные "
            "формулировки (избегай родовых окончаний; «вы», «у вас», "
            "«можно», «стоит» вместо «готов/готова»)."
        )
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
