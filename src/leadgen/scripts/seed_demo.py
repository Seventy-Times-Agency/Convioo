"""Seed a demo team for the zero-config first run.

Usage:
    python -m leadgen.scripts.seed_demo

Creates (idempotently — re-running skips what exists):

* four users, password ``demo1234`` for all:
  owner@demo.local / admin@demo.local / manager@demo.local / sales@demo.local
* team «Отдел продаж» with the four roles;
* funnel «Аудит-первый» (goal: Платный аудит · $100 · оплата+календарь,
  4-step touch path, no-answer rule 3×/14д);
* 10 демо-лидов (RU/UA labels, scores, phones), 6 из них назначены
  селзу в воронку — очередь «Работы» сразу живая.

This is DEMO data for looking at the first version — never run it on
the production database. The product itself still starts empty.
"""

from __future__ import annotations

import asyncio
import random
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

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
from leadgen.db.session import dispose_engine, get_session

DEMO_PASSWORD = "demo1234"

USERS = [
    (-910001, "owner@demo.local", "Максим", "owner"),
    (-910002, "admin@demo.local", "Роман", "admin"),
    (-910003, "manager@demo.local", "Мария", "manager"),
    (-910004, "sales@demo.local", "Денис", "sales"),
]

LEADS = [
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


async def _run() -> int:
    from argon2 import PasswordHasher

    hasher = PasswordHasher()
    now = datetime.now(timezone.utc)

    async with get_session() as session:
        # users
        for uid, email, name, _role in USERS:
            existing = (
                await session.execute(
                    select(User).where(User.email == email)
                )
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
                    )
                )
        await session.flush()

        # team + memberships
        team = (
            await session.execute(
                select(Team).where(Team.name == "Отдел продаж (демо)")
            )
        ).scalar_one_or_none()
        if team is None:
            team = Team(
                id=uuid.uuid4(),
                name="Отдел продаж (демо)",
                plan="free",
                monthly_cost_cap_usd=150,
            )
            session.add(team)
            await session.flush()
            for uid, _e, _n, role in USERS:
                session.add(
                    TeamMembership(
                        team_id=team.id, user_id=uid, role=role
                    )
                )

        # funnel
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
                    "Холодный заход v2\n"
                    "1. «Клиенты вас хвалят, но новые вас не находят…»\n"
                    "2. Один факт из досье (отзывы / сайт / реклама).\n"
                    "3. Предложить платный аудит за $100 с зачётом."
                ),
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

        # search + leads
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
            for i, (name, cat, addr, score, lang, phone) in enumerate(LEADS):
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
                    business_language_confidence=(
                        "likely" if lang else None
                    ),
                    summary=(
                        f"{cat} в {addr}. Живёт на сарафане: рейтинг "
                        "высокий, платного трафика не видно."
                    ),
                    advice=(
                        "Начни с «клиенты вас хвалят, но новые вас не "
                        "находят» — и переведи на платный аудит."
                    ),
                )
                # первые 6 — селзу в воронку, очередь сразу живая:
                # один просроченный перезвон, остальные по скорингу
                # раскладываются в «горячие»/«остальные».
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

    print("Демо-данные готовы. Логины (пароль demo1234):")
    for _uid, email, name, role in USERS:
        print(f"  {email:<22} {name:<7} {role}")
    return 0


async def _main() -> int:
    try:
        return await _run()
    finally:
        await dispose_engine()


def main() -> None:
    raise SystemExit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
