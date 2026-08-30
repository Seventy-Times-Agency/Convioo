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
                       auto=False, note="догрев после «думает»"),
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

    await session.commit()
    return {role: uid for uid, _e, _n, role in DEMO_USERS}
