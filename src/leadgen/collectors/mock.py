"""Mock collector for demo mode (муляж парсера).

When the first version runs without API keys, «Добыча» still has to
be testable end-to-end: запуск → прогресс → лиды → «обогащение» →
скоринг → раздача в воронку. This module fabricates plausible
businesses for any niche/region: RU/UA/EN name mix, phones,
ratings, some without a website, and a ready-made demo analysis
payload the enrichment stage copies onto the lead instead of calling
real APIs.

Deterministic per (niche, region): повторный запуск того же запроса
даёт другие названия только за счёт счётчика в suffix — дедуп не
душит повторные демо-поиски.
"""

from __future__ import annotations

import hashlib
import random
import time

from leadgen.collectors.google_places import RawLead

_RU_FIRST = [
    "Golden", "Royal", "Elite", "Diamond", "Lux", "Star", "Crystal",
    "Magic", "Perfect", "Prime", "Family", "Sunny",
]
_SLAVIC_MARK = [
    "Kyiv", "Odessa", "Lviv", "Dnipro", "Slavic", "Kharkiv", "Karpaty",
    "Dnieper", "Taras", "Bereza",
]
_EN_MARK = [
    "Miami", "Ocean", "Palm", "Bay", "Coastal", "Harbor", "Metro",
    "Central", "Premier", "Skyline",
]

_OWNERS = [
    ("Ирина К.", "ru"), ("Оксана П.", "uk"), ("Сергей М.", "ru"),
    ("Андрій Т.", "uk"), ("Наталья В.", "ru"), ("John D.", None),
    ("Олег С.", "ru"), ("Emily R.", None), ("Тарас Ш.", "uk"),
]

_WEAK = [
    "Сайта нет — новые клиенты не находят",
    "Сайт устаревший, без мобильной версии",
    "Реклама не крутится, живут на сарафане",
    "Instagram заброшен с прошлого года",
    "Нет онлайн-записи — теряют заявки вечером",
]
_STRONG = [
    "Высокий рейтинг и живые отзывы",
    "Стабильный поток постоянных клиентов",
    "Хорошая локация с трафиком",
    "Отвечают на отзывы — владелец вовлечён",
]


def demo_leads(
    niche: str, region: str, limit: int = 20
) -> list[RawLead]:
    """Fabricate ``limit`` plausible leads for niche/region."""
    seed_src = f"{niche.lower().strip()}|{region.lower().strip()}"
    # Счётчик времени в соли: повторный запуск того же запроса даёт
    # новые source_id → дедуп не съедает демо-результаты.
    salt = int(time.time()) // 60
    rng = random.Random(
        int(hashlib.sha1(seed_src.encode()).hexdigest()[:8], 16) + salt
    )
    raw_noun = (niche.strip().split() or ["Business"])[0]
    # Латиницу приводим к единственному числу (bakeries → bakery);
    # кириллицу оставляем как есть — обрезка даёт уродливые формы
    # («пекарни» → «Пекарн»), а вывеска «Star Пекарни» читается.
    if raw_noun.isascii():
        if len(raw_noun) > 4 and raw_noun.lower().endswith("ies"):
            raw_noun = raw_noun[:-3] + "y"
        elif len(raw_noun) > 3 and raw_noun.lower().endswith("s"):
            raw_noun = raw_noun[:-1]
    noun = (raw_noun.capitalize() or "Business")[:24]
    city = (region.split(",")[0].strip() or "Miami")[:32]

    leads: list[RawLead] = []
    used: set[str] = set()
    for i in range(max(1, min(limit, 60))):
        lang_roll = rng.random()
        if lang_roll < 0.45:
            mark, lang = rng.choice(_SLAVIC_MARK), rng.choice(["ru", "uk"])
        elif lang_roll < 0.75:
            mark, lang = rng.choice(_RU_FIRST), "ru"
        else:
            mark, lang = rng.choice(_EN_MARK), None
        name = f"{mark} {noun}"
        if name in used:
            name = f"{name} {rng.choice(['Studio', 'Pro', 'Plus', city])}"
        used.add(name)

        owner, owner_lang = rng.choice(_OWNERS)
        if lang is None and owner_lang:
            lang = owner_lang
        score = rng.randint(48, 94)
        has_site = rng.random() > 0.45
        weak = rng.sample(_WEAK, k=2)
        strong = rng.sample(_STRONG, k=2)
        rating = round(rng.uniform(4.0, 4.9), 1)
        reviews = rng.randint(25, 320)

        leads.append(
            RawLead(
                source="google_places",
                source_id=f"demo-{salt}-{i}-{abs(hash(name)) % 99999}",
                name=name,
                website=(
                    f"https://{mark.lower()}{noun.lower()}.example.com"
                    if has_site
                    else None
                ),
                phone=f"+1305555{rng.randint(1000, 9999)}",
                address=f"{rng.randint(100, 9899)} {rng.choice(['Collins Ave', 'Ocean Dr', 'Biscayne Blvd', 'Harding Ave'])}, {city}, FL",
                category=noun,
                rating=rating,
                reviews_count=reviews,
                raw={
                    "demo": {
                        "score": score,
                        "business_language": lang,
                        "owner": owner,
                        "summary": (
                            f"{noun} в {city}. Рейтинг {rating} при "
                            f"{reviews} отзывах. {weak[0]}."
                        ),
                        "advice": (
                            f"Заход через {weak[0].lower()}: "
                            "«клиенты вас хвалят, но новые вас не "
                            "находят». Дальше — платный аудит."
                        ),
                        "strengths": strong,
                        "weaknesses": weak,
                        "tags": (["RU/UA"] if lang else [])
                        + (["Нет сайта"] if not has_site else []),
                    }
                },
            )
        )
    # Горячие сверху — как отдал бы настоящий скоринг.
    leads.sort(
        key=lambda r: r.raw["demo"]["score"], reverse=True
    )
    return leads
