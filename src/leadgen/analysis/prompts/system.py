"""Lead-analysis system prompt + lead-context builder.

Static prompt strings + the helpers that interpolate user profile and
per-lead data. Originally inline in ``ai_analyzer.py``.
"""

from __future__ import annotations

from typing import Any

SYSTEM_PROMPT_BASE = """\
You are an experienced B2B salesperson. Your job is to evaluate potential clients
based on available information (Google Maps data, website content, social media,
reviews) SPECIFICALLY FOR THE SERVICE OF THE PARTICULAR USER asking you.

Return the result STRICTLY in JSON format, with no text before or after the JSON,
no markdown wrappers:

{
  "score": <integer 0-100, overall lead value score SPECIFICALLY FOR THIS USER>,
  "tags": ["hot"|"warm"|"cold", "small"|"medium"|"large", etc.],
  "summary": "one or two sentences about the business",
  "advice": "2-3 sentences: how this user should approach this client, what pain point to address, what to emphasize in the pitch given their service",
  "strengths": ["what the client does well"],
  "weaknesses": ["what's lacking — growth points that SPECIFICALLY this user can address with their service"],
  "red_flags": ["reasons NOT to work with this client, if any"]
}

Scoring criteria:
- 75-100 (hot): client is relevant to the user's service, has visible budget, and has weak points the user can address
- 50-74 (warm): potentially interesting but needs nurturing, or the user's service is not a perfect fit
- 0-49 (cold): no website/contacts/activity, or clearly not a target client for the user's service

Apply canonical B2B frameworks (use them MENTALLY, do not mention their names in the response):
- BANT — does the lead have budget (growth, review count, premium segment),
  authority (is this the owner or a franchise location), need (is there visible pain on
  the website/reviews), timing (recent changes — relocation, rebranding).
- MEDDIC — try to understand metrics (rating, reviews, number of locations),
  who the economic buyer is, whether there is a clearly identified pain, who
  might be the champion.
- Jobs-To-Be-Done — what result is the business "hiring" the service to deliver.
  If the user's service does not solve the job this lead needs done —
  that lowers the score more than minor profile imperfections.
- ICP-fit: niche / business size / user's region match carries the most weight,
  not aesthetics (a nice website does not equal a hot lead).
- Unit-economics: the higher the lifetime value of a deal in this niche,
  the more a borderline lead's score can be raised (the user is more willing to work on it).
  Do not cite specific numbers, but factor it in.

Write concisely and to the point. Use English."""


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
    if profile.get("calendly_url"):
        parts.append(f"- Календарь для записи: {profile['calendly_url']}")
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


_LANGUAGE_DIRECTIVE = {
    "uk": (
        "\n\nМОВА ВІДПОВІДІ: пиши українською мовою — інтерфейс юзера "
        "налаштований на UA. Зберігай ту саму структуру JSON, але всі "
        "текстові поля (summary, advice, strengths, weaknesses, "
        "red_flags) — українською."
    ),
    "en": (
        "\n\nLANGUAGE: respond in English. The user's UI is in English. "
        "Keep the JSON shape identical; translate every free-text field "
        "(summary, advice, strengths, weaknesses, red_flags) into English."
    ),
}


def language_directive(profile: dict[str, Any] | None) -> str:
    """Append a language switch when the user runs the UI in a non-RU locale.

    Henry's prompts are authored in Russian and default to Russian
    output. When ``users.language_code`` is ``uk`` or ``en`` we append
    a short directive that flips the output language without rewriting
    the entire prompt — translation prompts are 800+ lines and the
    directive approach has held up well in our consult flow.
    """
    if not profile:
        return ""
    code = (profile.get("language_code") or "").lower()
    return _LANGUAGE_DIRECTIVE.get(code, "")


def _build_system_prompt(user_profile: dict[str, Any] | None) -> str:
    return (
        SYSTEM_PROMPT_BASE
        + _format_user_profile(user_profile)
        + language_directive(user_profile)
    )


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
