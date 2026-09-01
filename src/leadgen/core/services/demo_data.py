"""Demo dataset for the first-version demo mode.

``ensure_demo_data(session)`` idempotently creates the demo team —
four users (owner/admin/manager/sales, password ``demo1234``), the
«Аудит-первый» funnel with a touch path, and ten leads with a live
call queue — and returns ``{role: user_id}``. Used by the
``/api/v1/auth/demo`` one-click login and by
``python -m leadgen.scripts.seed_demo``.

Demo data never ships to production: the endpoint mounts only when
``settings.demo_active`` is true (zero-config SQLite run without a
Google key, or an explicit DEMO_MODE=1).
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.core.services.funnel_engine import attach_lead
from leadgen.db.models import (
    Funnel,
    FunnelStep,
    Lead,
    SearchQuery,
    Team,
    TeamMembership,
    User,
)

DEMO_PASSWORD = "demo1234"
DEMO_TEAM_NAME = "Отдел продаж (демо)"

DEMO_USERS: list[tuple[int, str, str, str]] = [
    (-910001, "owner@demo.local", "Максим", "owner"),
    (-910002, "admin@demo.local", "Роман", "admin"),
    (-910003, "manager@demo.local", "Мария", "manager"),
    (-910004, "sales@demo.local", "Денис", "sales"),
]

DEMO_LEADS = [
    ("Golden Touch Beauty Salon", "Салон красоты", "Sunny Isles Beach, FL", 87, "ru", "+13055550187"),
    ("Kyiv Style Barbershop", "Барбершоп", "Miami, FL", 91, "uk", "+13055550121"),
    ("Odessa Bakery Miami", "Пекарня", "Miami, FL", 84, "ru", "+13055550143"),
    ("Slavic Market Deli", "Магазин", "Sunny Isles Beach, FL", 88, "ru", "+13055550166"),
    ("Lviv Dental Studio", "Стоматология", "Aventura, FL", 79, "uk", "+13055550178"),
    ("Dnipro Auto Glass", "Автосервис", "Hollywood, FL", 84, "uk", "+13055550190"),
    ("ProClean Services", "Клининг", "Miami, FL", 81, "ru", "+13055550111"),
    ("Sunrise Nails Spa", "Ногтевой сервис", "Hallandale, FL", 64, "ru", "+13055550132"),
    ("Alex Auto Repair", "Автосервис", "North Miami, FL", 58, None, "+13055550154"),
    ("Brooklyn Bagels South", "Кафе", "Boca Raton, FL", 72, "ru", "+13055550176"),
]


async def ensure_demo_data(session: AsyncSession) -> dict[str, int]:
    """Create the demo team if absent; return {role: user_id}."""
    from argon2 import PasswordHasher

    hasher = PasswordHasher()
    now = datetime.now(timezone.utc)

    for uid, email, name, _role in DEMO_USERS:
        existing = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                User(
                    id=uid,
                    email=email,
                    first_name=name,
                    display_name=name,
                    password_hash=hasher.hash(DEMO_PASSWORD),
                    email_verified_at=now,
                    language_code="ru",
                    queries_limit=100000,
                    onboarded_at=now,
                )
            )
    await session.flush()

    team = (
        await session.execute(
            select(Team).where(Team.name == DEMO_TEAM_NAME)
        )
    ).scalar_one_or_none()
    if team is None:
        team = Team(
            id=uuid.uuid4(),
            name=DEMO_TEAM_NAME,
            plan="free",
            monthly_cost_cap_usd=150,
        )
        session.add(team)
        await session.flush()
        for uid, _e, _n, role in DEMO_USERS:
            session.add(
                TeamMembership(team_id=team.id, user_id=uid, role=role)
            )

    funnel = (
        await session.execute(
            select(Funnel)
            .where(Funnel.team_id == team.id)
            .where(Funnel.name == "Аудит-первый")
        )
    ).scalar_one_or_none()
    if funnel is None:
        funnel = Funnel(
            id=uuid.uuid4(),
            team_id=team.id,
            name="Аудит-первый",
            status="active",
            goal_name="Платный аудит",
            goal_price=100,
            goal_action="payment_calendar",
            script=(
                "Представиться: имя и агентство, 15 секунд, без «как дела»\n"
                "Зацеп из захода: отзывы отличные — новые клиенты не находят\n"
                "Вопрос квалификации: откуда сейчас приходят клиенты?\n"
                "Оффер: предложить платный аудит за $100 и назначить дату"
            ),
            objections=[
                {
                    "objection": "Дорого",
                    "answer": (
                        "окупается одним удержанным клиентом; "
                        "называем цифру потерь"
                    ),
                },
                {
                    "objection": "Нам хватает",
                    "answer": (
                        "хватает сегодня; конкурент уже забирает район"
                    ),
                },
                {
                    "objection": "Пришлите на почту",
                    "answer": (
                        "пришлём после двух вопросов, "
                        "чтобы письмо было по делу"
                    ),
                },
            ],
            no_answer_attempts=3,
            no_answer_pause_days=14,
            created_by_user_id=-910003,
        )
        funnel.steps = [
            FunnelStep(order_index=0, kind="call", day_offset=0,
                       note="скрипт: холодный заход v2"),
            FunnelStep(order_index=1, kind="email", day_offset=1,
                       auto=True, note="догрев после «думает»"),
            FunnelStep(order_index=2, kind="call", day_offset=3,
                       note="повторный заход"),
            FunnelStep(order_index=3, kind="email", day_offset=7,
                       auto=False, note="письмо-кейс ниши"),
        ]
        session.add(funnel)
        await session.flush()

    sq = (
        await session.execute(
            select(SearchQuery)
            .where(SearchQuery.team_id == team.id)
            .where(SearchQuery.niche == "салоны и сервисы (демо)")
        )
    ).scalar_one_or_none()
    if sq is None:
        sq = SearchQuery(
            id=uuid.uuid4(),
            user_id=-910003,
            team_id=team.id,
            niche="салоны и сервисы (демо)",
            region="Miami, FL",
            status="done",
            source="web",
        )
        session.add(sq)
        await session.flush()

        rng = random.Random(7)
        for i, (name, cat, addr, score, lang, phone) in enumerate(DEMO_LEADS):
            lead = Lead(
                id=uuid.uuid4(),
                query_id=sq.id,
                name=name,
                category=cat,
                address=addr,
                phone=phone,
                source="google_places",
                source_id=f"demo-{i}",
                lead_status="new",
                score_ai=float(score),
                enriched=True,
                rating=round(rng.uniform(4.2, 4.9), 1),
                reviews_count=rng.randint(40, 260),
                business_language=lang,
                business_language_confidence="likely" if lang else None,
                summary=(
                    f"{cat} в {addr}. Живёт на сарафане: рейтинг "
                    "высокий, платного трафика не видно."
                ),
                advice=(
                    "Начни с «клиенты вас хвалят, но новые вас не "
                    "находят» — и переведи на платный аудит."
                ),
            )
            if i < 6:
                attach_lead(lead, funnel, now=now)
                lead.owner_user_id = -910004
                lead.next_touch_at = (
                    now - timedelta(hours=1)
                    if i == 0
                    else now + timedelta(days=1)
                )
            session.add(lead)

        await session.flush()

    # Добавочные части засева живут отдельно от создания команды.
    # Раньше они лежали внутри «если команды ещё нет», и любая новая
    # демо-сущность не доезжала до уже существующей демо-команды —
    # ровно это случилось с токенами и разобранными ответами на
    # боевом стенде. Каждая часть проверяет себя сама.
    await _ensure_tokens(session, team.id)
    await _ensure_replies(session, team.id, now)
    await _ensure_letter_queue(session, team.id, now)
    await _ensure_journal(session, team.id, now)

    await session.commit()
    return {role: uid for uid, _e, _n, role in DEMO_USERS}


async def _ensure_tokens(session: AsyncSession, team_id) -> None:
    """Стартовый пакет — один раз на команду."""
    from leadgen.core.services import tokens as _tokens
    from leadgen.db.models import TokenLedger

    already = (
        await session.execute(
            select(TokenLedger.id).where(TokenLedger.team_id == team_id).limit(1)
        )
    ).scalar_one_or_none()
    if already is None:
        await _tokens.grant(
            session, team_id, 1000, reason="стартовый пакет демо"
        )


async def _ensure_replies(session: AsyncSession, team_id, now) -> None:
    """Разобранные ответы — если их ещё нет ни одного."""
    from leadgen.db.models import LeadActivity

    already = (
        await session.execute(
            select(LeadActivity.id)
            .where(LeadActivity.team_id == team_id)
            .where(LeadActivity.kind == "email_replied")
            .limit(1)
        )
    ).scalar_one_or_none()
    if already is not None:
        return

    leads = (
        (
            await session.execute(
                select(Lead)
                .join(SearchQuery, SearchQuery.id == Lead.query_id)
                .where(SearchQuery.team_id == team_id)
                .order_by(Lead.score_ai.desc().nullslast())
                .limit(8)
            )
        )
        .scalars()
        .all()
    )
    if leads:
        _seed_replies(session, team_id, list(leads), now)


# Разобранные ответы клиентов для экрана «Входящие». В демо почта не
# подключена, писем никто не отправлял — значит и ответов быть не может.
# Без них экран честно пуст, но пустой экран ничего не показывает, а
# демо существует ровно для показа. Форма записей повторяет ту, что
# пишет email_reply_tracker после разбора настоящего ответа.
_DEMO_REPLIES: tuple[tuple[int, str, str, str, str, str], ...] = (
    (
        0,
        "interested",
        "positive",
        "Да, расскажите подробнее про аудит — сколько это стоит и что "
        "мы получим в итоге? У нас сейчас всё через Instagram, но "
        "заявок мало.",
        "Интерес к аудиту, спрашивает цену и результат.",
        "Здравствуйте! Аудит стоит $100 и занимает 3-4 дня. Разберём, "
        "почему Instagram даёт мало заявок, посчитаем, сколько клиентов "
        "теряется без поиска и рекламы, и дадим план — что чинить "
        "первым. Итог разберём на созвоне за 20 минут. Удобно в "
        "четверг или пятницу?",
    ),
    (
        1,
        "objection",
        "neutral",
        "А какие гарантии, что это сработает у нас?",
        "Возражение: сомневается в результате.",
        "Гарантия простая: аудит показывает цифры, а не обещания — "
        "сколько заявок вы теряете сейчас и откуда их можно взять. "
        "Если после разбора решите, что делать нечего, вы просто "
        "останетесь с этими цифрами.",
    ),
    (
        2,
        "meeting_request",
        "positive",
        "Можно созвон в четверг после обеда?",
        "Просит встречу в четверг.",
        "Да, четверг после обеда подходит. Предложу 15:00 — "
        "созвон на 20 минут, покажу разбор на экране.",
    ),
    (
        3,
        "unsubscribe",
        "negative",
        "Отпишите меня, пожалуйста.",
        "Просит отписку — адрес добавлен в список исключений.",
        "",
    ),
)


def _seed_replies(session, team_id, leads: list, now) -> None:
    """Положить разобранные ответы на первые лиды демо-команды."""
    from leadgen.db.models import LeadActivity

    for idx, category, sentiment, preview, summary, draft in _DEMO_REPLIES:
        if idx >= len(leads):
            continue
        lead = leads[idx]
        session.add(
            LeadActivity(
                lead_id=lead.id,
                user_id=-910004,
                team_id=team_id,
                kind="email_replied",
                payload={
                    "category": category,
                    "sentiment": sentiment,
                    "confidence": "high",
                    "preview": preview,
                    "summary": summary,
                    "suggested_reply": draft,
                    "from": f"client{idx}@example.com",
                },
                created_at=now - timedelta(hours=idx * 3 + 1),
            )
        )


async def _ensure_letter_queue(session: AsyncSession, team_id, now) -> None:
    """Поставить часть лидов на почтовые касания — экран «Письма».

    В демо все лиды стоят на первом шаге воронки, а он звонок, поэтому
    обе очереди писем пусты. Здесь несколько лидов продвигаются на
    шаги-письма: одни на ручное касание (ждут одобрения), другие на
    авто (уйдут по расписанию). Ровно так их расставил бы движок
    воронки после исходов звонков.
    """
    funnel = (
        await session.execute(
            select(Funnel)
            .where(Funnel.team_id == team_id)
            .where(Funnel.name == "Аудит-первый")
        )
    ).scalar_one_or_none()
    if funnel is None:
        return

    steps = sorted(
        (
            await session.execute(
                select(FunnelStep).where(FunnelStep.funnel_id == funnel.id)
            )
        )
        .scalars()
        .all(),
        key=lambda s: s.order_index,
    )
    email_steps = [s.order_index for s in steps if s.kind == "email"]
    if not email_steps:
        return

    # В макете второе касание помечено «авто». Воронка могла быть
    # создана раньше этой правки, поэтому флаг выставляем здесь, а не
    # только при создании — иначе очередь «уйдут автоматом» на уже
    # работающем стенде навсегда останется пустой.
    for st in steps:
        if st.kind == "email" and st.order_index == email_steps[0]:
            st.auto = True

    # Уже стоит кто-то на письме — второй раз не расставляем.
    on_email = (
        await session.execute(
            select(Lead.id)
            .join(SearchQuery, SearchQuery.id == Lead.query_id)
            .where(SearchQuery.team_id == team_id)
            .where(Lead.funnel_id == funnel.id)
            .where(Lead.funnel_step.in_(email_steps))
            .limit(1)
        )
    ).scalar_one_or_none()
    if on_email is not None:
        return

    candidates = (
        (
            await session.execute(
                select(Lead)
                .join(SearchQuery, SearchQuery.id == Lead.query_id)
                .where(SearchQuery.team_id == team_id)
                .where(Lead.funnel_id == funnel.id)
                .order_by(Lead.score_ai.desc().nullslast())
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    for i, lead in enumerate(candidates):
        lead.funnel_step = email_steps[i % len(email_steps)]
        lead.next_touch_at = now + timedelta(hours=i + 1)


async def _ensure_journal(session: AsyncSession, team_id, now) -> None:
    """Лента журнала действий — если она ещё пуста."""
    from leadgen.db.models import TeamActionLog
    from leadgen.db.models.journal import (
        JK_BATCH_ASSIGNED,
        JK_COST_CAP_CHANGED,
        JK_FUNNEL_UPDATED,
        JK_MEMBER_INVITED,
        JK_SEARCH_FINISHED,
    )

    already = (
        await session.execute(
            select(TeamActionLog.id)
            .where(TeamActionLog.team_id == team_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if already is not None:
        return

    rows = [
        (
            JK_BATCH_ASSIGNED,
            -910003,
            "Мария",
            "manager",
            {"count": 6, "assignee": "Денис", "funnel": "Платный аудит"},
            timedelta(hours=2),
        ),
        (
            JK_FUNNEL_UPDATED,
            -910002,
            "Роман",
            "admin",
            {"name": "Платный аудит"},
            timedelta(hours=4),
        ),
        (
            JK_SEARCH_FINISHED,
            None,
            None,
            None,
            {
                "leads": 12,
                "tokens": 12,
                "niche": "салоны красоты",
                "region": "Майами",
            },
            timedelta(hours=5),
        ),
        (
            JK_MEMBER_INVITED,
            -910002,
            "Роман",
            "admin",
            {"role": "sales"},
            timedelta(days=1, hours=3),
        ),
        (
            JK_COST_CAP_CHANGED,
            -910001,
            "Максим",
            "owner",
            {"from": 100.0, "to": 150.0},
            timedelta(days=2),
        ),
    ]
    for kind, actor_id, actor_name, actor_role, payload, ago in rows:
        session.add(
            TeamActionLog(
                team_id=team_id,
                actor_id=actor_id,
                actor_name=actor_name,
                actor_role=actor_role,
                kind=kind,
                payload=payload,
                created_at=now - ago,
            )
        )
