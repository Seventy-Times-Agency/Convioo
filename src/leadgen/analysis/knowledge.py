"""Structured product / sales knowledge Henry leans on.

Each fact Henry should know about Convioo lives as a ``FeatureDoc``
in the registry below — easier to add a new entry when a feature
ships than to surgery a giant string. ``all_blocks()`` rewinds the
registry into a single prompt fragment for the system prompt, so
existing call sites (``_assistant_personal_system_prompt`` etc.)
keep working unchanged.

When you ship a feature in any PR, drop a ``FeatureDoc`` here. Henry
picks it up on the next request without redeploying anything else.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FeatureDoc:
    """One thing Henry knows about Convioo.

    ``id`` is a snake_case key for cross-referencing (we'll wire it
    to slash commands later so ``/explain dedup`` returns the
    matching block). ``section`` groups the registry into the four
    classical buckets (features, scoring, sales principles, workflow);
    Henry mentions sections when the user asks a meta question.
    """

    id: str
    section: str  # one of features / scoring / principles / workflow
    title: str
    bullets: tuple[str, ...] = field(default_factory=tuple)


# ── Product features ────────────────────────────────────────────────
_FEATURES: tuple[FeatureDoc, ...] = (
    FeatureDoc(
        id="search_pipeline",
        section="features",
        title="Поиск B2B-лидов",
        bullets=(
            "Юзер задаёт нишу + регион. Convioo находит компании из "
            "Google Places (текстовый поиск) и обогащает каждую — сайт, "
            "отзывы Google, соцсети, рейтинг.",
            "Выбор объёма: 5 / 10 / 20 / 30 / 50 лидов на поиск; чем "
            "меньше — тем дешевле по AI-кредитам и быстрее.",
            "Можно задать целевой язык лида (en/ru/uk/de/fr/es/pl и др.) — "
            "Convioo фильтрует выдачу по скрипту и просит у Google "
            "результаты на нужном языке + правильном region-биасе.",
        ),
    ),
    FeatureDoc(
        id="niche_autocomplete",
        section="features",
        title="Подсказки ниш",
        bullets=(
            "В поле «ниша» работает автокомплит из курируемой "
            "таксономии (~70 распространённых B2B-ниш с переводами "
            "на ru/uk/en/de и алиасами).",
            "Юзер всё ещё может ввести любую free-form нишу — "
            "комбобокс не блокирует ввод.",
        ),
    ),
    FeatureDoc(
        id="dedup",
        section="features",
        title="Дедупликация лидов",
        bullets=(
            "Один и тот же лид не появится дважды: дедуп по Google "
            "place_id ИЛИ нормализованному телефону ИЛИ корню домена.",
            "Generic-домены (facebook, instagram, yelp, google maps) "
            "не считаются дедуп-ключами — они дают ложные совпадения.",
            "В команде хард-дедуп: один лид никогда не попадает в "
            "CRM двух участников разом.",
        ),
    ),
    FeatureDoc(
        id="lead_lifecycle",
        section="features",
        title="Жизненный цикл лида",
        bullets=(
            "В CRM (`/app/leads`) — статусы new / contacted / replied "
            "/ won / archived, заметки на лид, цветные пометки "
            "(видны только владельцу), таски, custom fields.",
            "Удаление лида: «убрать из CRM» (мягкое — может всплыть "
            "при будущем поиске по похожему запросу) или «удалить и "
            "больше не показывать» (записывает в seen-leads, лид не "
            "вернётся в новых поисках).",
        ),
    ),
    FeatureDoc(
        id="teams",
        section="features",
        title="Команды",
        bullets=(
            "Несколько юзеров делят общий CRM, дедуп лидов и квоту.",
            "Одна и та же связка niche+region не запускается дважды "
            "в одной команде — сразу подскажем кто и когда искал.",
        ),
    ),
    FeatureDoc(
        id="account_recovery",
        section="features",
        title="Восстановление доступа",
        bullets=(
            "«Забыли пароль» отправляет ссылку на сброс на email "
            "аккаунта; ссылка действует 1 час, одноразовая.",
            "«Забыли email» — если у юзера задан резервный email в "
            "Настройках → Безопасность, мы пришлём напоминание о "
            "привязанном основном адресе.",
            "После сброса пароля все остальные сессии завершаются "
            "автоматически — на старом устройстве придётся залогиниться "
            "заново.",
            "В Настройках → Безопасность видны все активные сессии "
            "(IP, устройство, последняя активность) с кнопкой "
            "завершения.",
        ),
    ),
    FeatureDoc(
        id="cold_email",
        section="features",
        title="Cold-email черновики",
        bullets=(
            "В каждом лиде есть AI-черновик письма: тон "
            "(professional / casual / bold), персонализация под "
            "конкретный сайт + отзывы, плюс краткий «как презентовать» "
            "под услугу юзера.",
        ),
    ),
)


# ── Scoring ─────────────────────────────────────────────────────────
_SCORING: tuple[FeatureDoc, ...] = (
    FeatureDoc(
        id="ai_score",
        section="scoring",
        title="Как считается AI-score",
        bullets=(
            "Каждый лид прогоняется через Claude Haiku — на вход "
            "идёт сайт, отзывы Google, рейтинг, соцсети, описание "
            "категории + профиль юзера (что продаёт, ниши, регион, "
            "размер бизнеса).",
            "Hot (≥75): высокая совместимость + признаки готовности "
            "к разговору (рабочий сайт, активные соцсети, рейтинг 4+, "
            "30+ отзывов).",
            "Warm (50-74): релевантен, но что-то слабое — устаревший "
            "сайт, мало отзывов, сегмент чуть шире целевого.",
            "Cold (<50): низкая совместимость или явные red flags "
            "(нет сайта, нет контактов, плохой рейтинг).",
        ),
    ),
    FeatureDoc(
        id="frameworks",
        section="scoring",
        title="Какие фреймворки учитывает скорер",
        bullets=(
            "BANT (Budget/Authority/Need/Timing) — оценивается по "
            "косвенным сигналам с Google и сайта.",
            "MEDDIC — для крупных сделок (метрики, экономический "
            "покупатель, identified pain, champion).",
            "Jobs-To-Be-Done — какую «работу» бизнес-лид нанимает "
            "услугу юзера выполнить.",
            "ICP-fit — самый сильный сигнал: ниша / размер / регион.",
            "Unit-economics — чем выше LTV в нише, тем больше веса "
            "у пограничных лидов.",
        ),
    ),
)


# ── Sales principles ────────────────────────────────────────────────
_PRINCIPLES: tuple[FeatureDoc, ...] = (
    FeatureDoc(
        id="icp",
        section="principles",
        title="ICP",
        bullets=(
            "ICP — не «B2B вообще», а конкретный тип бизнеса + размер "
            "+ цифровая зрелость + триггер покупки.",
            "Лучше 50 точно подходящих лидов, чем 500 «всех подряд».",
        ),
    ),
    FeatureDoc(
        id="personalisation",
        section="principles",
        title="Персонализация и outreach",
        bullets=(
            "Первое касание ссылается на что-то конкретное у лида "
            "(последний пост, новая локация, особенность сайта).",
            "Один soft CTA на касание. Никаких «давайте созвонимся "
            "завтра в 14:00 со скидкой 20%».",
            "Outbound-метрики: hot-rate <15% значит размытый ICP; "
            "reply-rate <5% — слабая подача; conversion <10% — не та "
            "оферта.",
        ),
    ),
    FeatureDoc(
        id="niche_specificity",
        section="principles",
        title="Ниша и регион",
        bullets=(
            "Ниша — что бизнес делает, а не индустрия: «барбершоп», "
            "«стоматологическая клиника», «юр.фирма по корп.праву».",
            "Регион — конкретный город, не страна и не «вся Европа».",
        ),
    ),
)


# ── Workflow ────────────────────────────────────────────────────────
_WORKFLOW: tuple[FeatureDoc, ...] = (
    FeatureDoc(
        id="end_to_end",
        section="workflow",
        title="End-to-end сценарий работы",
        bullets=(
            "1. Заполняет профиль (что продаёт + ниши + регион + "
            "размер бизнеса). Чем точнее профиль — тем точнее скор.",
            "2. Запускает поиск: niche + region + (опционально) "
            "идеальный клиент, exclusions, целевые языки, размер "
            "выборки. Henry помогает уточнить параметры в чате.",
            "3. Получает лиды через 60-120 секунд. Сортирует по "
            "hot/warm/cold.",
            "4. Открывает hot-лиды, изучает summary/strengths/"
            "weaknesses, читает AI-совет «как презентовать», "
            "копирует cold-email черновик.",
            "5. В CRM ведёт статусы и заметки. Удаляет лида насовсем "
            "если не подошёл, чтобы он не всплыл в следующем поиске.",
        ),
    ),
)


REGISTRY: tuple[FeatureDoc, ...] = (
    *_FEATURES,
    *_SCORING,
    *_PRINCIPLES,
    *_WORKFLOW,
)


def find(feature_id: str) -> FeatureDoc | None:
    fid = feature_id.strip().lower()
    for doc in REGISTRY:
        if doc.id == fid:
            return doc
    return None


def by_section(section: str) -> tuple[FeatureDoc, ...]:
    return tuple(d for d in REGISTRY if d.section == section)


_SECTION_HEADERS: dict[str, str] = {
    "features": "Что умеет Convioo",
    "scoring": "Как работает AI-скор",
    "principles": "B2B-sales принципы которыми ты опираешься как консультант",
    "workflow": "Как юзер обычно работает с Convioo",
}


def _render_doc(doc: FeatureDoc) -> str:
    lines = [f"- {doc.title}:"]
    for bullet in doc.bullets:
        lines.append(f"  · {bullet}")
    return "\n".join(lines)


def _render_section(section: str) -> str:
    header = _SECTION_HEADERS.get(section, section.title())
    docs = by_section(section)
    if not docs:
        return ""
    body = "\n".join(_render_doc(d) for d in docs)
    return f"{header}:\n{body}"


def all_blocks() -> str:
    """Concatenate every section into a single prompt fragment.

    Preserves the four-section layout the legacy strings used so the
    LLM gets the same shape it was tuned against.
    """
    sections = ["features", "scoring", "principles", "workflow"]
    parts = [_render_section(s) for s in sections]
    return "\n\n".join(p for p in parts if p)


# ── Back-compat constants ──────────────────────────────────────────
# A few callers (and tests) still import the old uppercase blocks.
# Re-export them as derived strings so any lingering reference keeps
# working without churn.

PRODUCT_FEATURES = _render_section("features")
SCORING_EXPLAINED = _render_section("scoring")
SALES_PRINCIPLES = _render_section("principles")
WORKFLOW_TIPS = _render_section("workflow")
