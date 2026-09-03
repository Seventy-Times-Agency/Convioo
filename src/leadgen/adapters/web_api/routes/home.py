"""Home screen data, shaped per role — `docs/design/mockups/*Home*.dc.html`.

The three approved home mockups are three different screens, not one
dashboard with hidden rows:

* ``OwnerHome.dc.html``  — цели, деньги, затраты платформы, недельный
  график, лента событий компании.
* ``MgrHome.dc.html``   — наборы отдела, цели воронок, свободные лиды,
  строка на каждого селза.
* ``Home.dc.html``      — очередь селза, ближайший перезвон, его личный
  счёт за день.

One endpoint serves all three: the caller's role in the team decides
which payload comes back, so the frontend never asks for numbers the
role is not allowed to see. Sales never receives money fields — the
same rule the rest of the API enforces.

Numbers in the mockups (58 целей, $4 600, 412 наборов) are
illustrative. Everything here is computed from the team's own rows;
an empty team returns zeros, not placeholders.

Two mockup figures have no source in the data model and are therefore
absent rather than invented:

* «46 оплачено» — the model records that a goal was reached
  (``Lead.goal_reached_at``), not that it was paid. There is no
  payment record to join against.
* «Разговоры 2+ мин» — call duration needs telephony, which is not
  wired yet. Only outcomes are recorded.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.routes._helpers import membership
from leadgen.core.services.team_permissions import (
    is_sales,
    normalize_role,
)
from leadgen.db.models import (
    Funnel,
    Lead,
    LeadActivity,
    SearchQuery,
    Team,
    TeamMembership,
    User,
)
from leadgen.db.session import session_factory

router = APIRouter(tags=["home"])

HOT_SCORE = 75.0
WEEKS_BACK = 12


class Tile(BaseModel):
    """One KPI card: big number plus the line under it."""

    key: str
    label: str
    value: str
    hint: str


class WeekPoint(BaseModel):
    label: str
    count: int


class MemberRow(BaseModel):
    user_id: int
    name: str
    dials: int
    goals: int
    lagging: bool


class EventRow(BaseModel):
    at: str
    text: str


class CallbackRow(BaseModel):
    lead_id: uuid.UUID
    lead_name: str
    at: datetime | None = None
    hint: str | None = None
    overdue: bool = False


class ReactionRow(BaseModel):
    lead_id: uuid.UUID
    lead_name: str
    category: str
    preview: str
    at: datetime
    has_draft: bool = False


class HomeResponse(BaseModel):
    role: str
    scope: str
    tiles: list[Tile]
    weekly: list[WeekPoint] = []
    members: list[MemberRow] = []
    events: list[EventRow] = []
    queue_total: int = 0
    next_callback_at: datetime | None = None
    free_leads: int = 0
    # Шапка экрана прозвона: «Наборы · Разговоры · Цели».
    # «Разговоры» — набор, где кто-то снял трубку: любой исход, кроме
    # недозвона и неверного номера. Длительности у нас нет (нужна
    # телефония), поэтому «2+ мин» из макета здесь не считается.
    dials_today: int = 0
    conversations_today: int = 0
    goals_today: int = 0
    # Экран селза (Home.dc): приветствие, план на сейчас, реакция.
    first_name: str = ""
    letters_pending: int = 0
    callbacks: list[CallbackRow] = []
    reactions: list[ReactionRow] = []


def _money(v: float) -> str:
    return f"${v:,.0f}".replace(",", " ") if v >= 100 else f"${v:.2f}"


async def _team_lead_ids(session, team_id: uuid.UUID) -> list[uuid.UUID]:
    rows = (
        await session.execute(
            select(Lead.id)
            .join(SearchQuery, SearchQuery.id == Lead.query_id)
            .where(SearchQuery.team_id == team_id)
            .where(Lead.deleted_at.is_(None))
        )
    ).scalars()
    return list(rows)


@router.get("/api/v1/teams/{team_id}/home", response_model=HomeResponse)
async def team_home(
    team_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> HomeResponse:
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff30 = now - timedelta(days=30)

    async with session_factory() as session:
        ms = await membership(session, team_id, current_user.id)
        if ms is None:
            raise HTTPException(status_code=403, detail="not a team member")
        role = normalize_role(ms.role)
        team = await session.get(Team, team_id)

        base = (
            select(Lead)
            .join(SearchQuery, SearchQuery.id == Lead.query_id)
            .where(SearchQuery.team_id == team_id)
            .where(Lead.deleted_at.is_(None))
            .where(Lead.archived_at.is_(None))
        )

        # ── sales: his own queue, nothing about the department ──
        if is_sales(role):
            mine = (
                (
                    await session.execute(
                        base.where(Lead.owner_user_id == current_user.id)
                        .where(Lead.goal_reached_at.is_(None))
                    )
                )
                .scalars()
                .all()
            )
            due = [
                lead.next_touch_at
                for lead in mine
                if lead.next_touch_at is not None
            ]
            next_cb = min(due) if due else None
            hot = sum(
                1 for lead in mine if (lead.score_ai or 0) >= HOT_SCORE
            )
            acts = (
                (
                    await session.execute(
                        select(LeadActivity)
                        .where(LeadActivity.team_id == team_id)
                        .where(LeadActivity.user_id == current_user.id)
                        .where(LeadActivity.kind == "call")
                        .where(LeadActivity.created_at >= day_start)
                    )
                )
                .scalars()
                .all()
            )
            goals_today = sum(
                1
                for a in acts
                if (a.payload or {}).get("outcome") == "goal"
            )
            talked = sum(
                1
                for a in acts
                if (a.payload or {}).get("outcome")
                not in ("no_answer", "wrong_number")
            )
            # «Сейчас по плану»: ближайшие касания очереди — просрочка
            # первой, дальше по времени.
            upcoming = sorted(
                (
                    lead
                    for lead in mine
                    if lead.next_touch_at is not None
                ),
                key=lambda lead: lead.next_touch_at.replace(
                    tzinfo=lead.next_touch_at.tzinfo or timezone.utc
                ),
            )[:3]
            callbacks = [
                CallbackRow(
                    lead_id=lead.id,
                    lead_name=lead.name,
                    at=lead.next_touch_at,
                    hint=(
                        f"попытка {lead.no_answer_count + 1}"
                        if (lead.no_answer_count or 0) > 0
                        else None
                    ),
                    overdue=lead.next_touch_at.replace(
                        tzinfo=lead.next_touch_at.tzinfo or timezone.utc
                    )
                    <= now,
                )
                for lead in upcoming
            ]

            # Письма-догревы, которые ждут одобрения (ручной email-шаг
            # воронки) — то же правило, что на экране «Письма».
            letters_pending = await _letters_pending(
                session, team_id, current_user.id
            )

            # «Требует реакции»: свежие разобранные ответы по своим
            # лидам — интерес и встречи первыми.
            reactions = await _own_reactions(
                session, team_id, current_user.id
            )

            feed = await _recent_events(
                session, team_id, only_user_id=current_user.id
            )

            return HomeResponse(
                role=role,
                scope=team.name if team else "",
                first_name=(
                    (current_user.display_name or "").split()[0]
                    if current_user.display_name
                    else ""
                ),
                queue_total=len(mine),
                next_callback_at=next_cb,
                dials_today=len(acts),
                conversations_today=talked,
                goals_today=goals_today,
                letters_pending=letters_pending,
                callbacks=callbacks,
                reactions=reactions,
                events=feed,
                tiles=[
                    Tile(
                        key="queue",
                        label="В очереди",
                        value=str(len(mine)),
                        hint=f"горячих {hot}",
                    ),
                    Tile(
                        key="dials",
                        label="Наборы сегодня",
                        value=str(len(acts)),
                        hint="исходы записаны",
                    ),
                    Tile(
                        key="goals",
                        label="Цели сегодня",
                        value=str(goals_today),
                        hint="зелёная кнопка",
                    ),
                ],
            )

        # ── manager and up: the whole team base ──
        leads = (await session.execute(base)).scalars().all()
        goals30 = [
            lead
            for lead in leads
            if lead.goal_reached_at is not None
            and lead.goal_reached_at.replace(tzinfo=timezone.utc)
            >= cutoff30
        ]
        free = sum(1 for lead in leads if lead.owner_user_id is None)

        acts30 = (
            (
                await session.execute(
                    select(LeadActivity)
                    .where(LeadActivity.team_id == team_id)
                    .where(LeadActivity.kind == "call")
                    .where(LeadActivity.created_at >= cutoff30)
                )
            )
            .scalars()
            .all()
        )
        dials_today = [a for a in acts30 if a.created_at >= day_start]

        # Per-rep row: dials and goals for today, as in the mockup's
        # «Команда · сегодня» panel.
        members = (
            (
                await session.execute(
                    select(TeamMembership, User)
                    .join(User, User.id == TeamMembership.user_id)
                    .where(TeamMembership.team_id == team_id)
                )
            )
            .all()
        )
        rows: list[MemberRow] = []
        for m, u in members:
            if normalize_role(m.role) not in ("sales", "manager"):
                continue
            mine_today = [a for a in dials_today if a.user_id == u.id]
            g = sum(
                1
                for a in mine_today
                if (a.payload or {}).get("outcome") == "goal"
            )
            rows.append(
                MemberRow(
                    user_id=u.id,
                    name=(u.display_name or u.first_name or f"#{u.id}"),
                    dials=len(mine_today),
                    goals=g,
                    lagging=(g == 0 and len(mine_today) == 0),
                )
            )
        rows.sort(key=lambda r: (-r.goals, -r.dials))

        # Weekly goal counts, oldest first — the mockup's bar chart.
        weekly: list[WeekPoint] = []
        for i in range(WEEKS_BACK, 0, -1):
            start = now - timedelta(weeks=i)
            end = start + timedelta(weeks=1)
            weekly.append(
                WeekPoint(
                    label=f"н{WEEKS_BACK - i + 1}",
                    count=sum(
                        1
                        for lead in goals30
                        if start
                        <= lead.goal_reached_at.replace(tzinfo=timezone.utc)
                        < end
                    ),
                )
            )

        events = await _recent_events(session, team_id)

        if role == "manager":
            funnels_n = (
                await session.execute(
                    select(func.count(Funnel.id)).where(
                        Funnel.team_id == team_id
                    )
                )
            ).scalar_one()
            return HomeResponse(
                role=role,
                scope=team.name if team else "",
                free_leads=free,
                members=rows,
                weekly=weekly,
                events=events,
                tiles=[
                    Tile(
                        key="dials",
                        label="Наборы отдела",
                        value=str(len(dials_today)),
                        hint=f"{len(rows)} на линии",
                    ),
                    Tile(
                        key="goals",
                        label="Цели за 30 дней",
                        value=str(len(goals30)),
                        hint="по всем воронкам",
                    ),
                    Tile(
                        key="funnels",
                        label="Воронок",
                        value=str(funnels_n),
                        hint="активных сценариев",
                    ),
                    Tile(
                        key="free",
                        label="Свободных лидов",
                        value=str(free),
                        hint="ждут раздачи",
                    ),
                ],
            )

        # owner / admin — money included
        from leadgen.core.services.cost_control import get_team_cost_status

        cost = await get_team_cost_status(session, team_id)
        revenue = 0.0
        funnel_price: dict[uuid.UUID, float] = {}
        for f in (
            (
                await session.execute(
                    select(Funnel).where(Funnel.team_id == team_id)
                )
            )
            .scalars()
            .all()
        ):
            funnel_price[f.id] = float(f.goal_price or 0)
        for lead in goals30:
            if lead.funnel_id is not None:
                revenue += funnel_price.get(lead.funnel_id, 0.0)

        per_goal = (
            cost.month_cost_usd / len(goals30) if goals30 else 0.0
        )
        cap_hint = (
            f"добыча · потолок {_money(cost.cap_usd)}"
            if cost.cap_usd
            else "добыча · потолок не задан"
        )

        return HomeResponse(
            role=role,
            scope="вся компания",
            free_leads=free,
            members=rows,
            weekly=weekly,
            events=events,
            tiles=[
                Tile(
                    key="goals",
                    label="Цели за 30 дней",
                    value=str(len(goals30)),
                    hint=f"из {len(leads)} лидов в базе",
                ),
                Tile(
                    key="revenue",
                    label="Оплаты целей",
                    value=_money(revenue),
                    hint="сумма цен целей воронок",
                ),
                Tile(
                    key="cost",
                    label="Затраты платформы",
                    value=_money(cost.month_cost_usd),
                    hint=cap_hint,
                ),
                Tile(
                    key="per_goal",
                    label="Стоимость цели",
                    value=_money(per_goal),
                    hint="затраты / цели",
                ),
            ],
        )


def _events_stmt(team_id: uuid.UUID, only_user_id: int | None):
    stmt = (
        select(LeadActivity, Lead)
        .join(Lead, Lead.id == LeadActivity.lead_id)
        .where(LeadActivity.team_id == team_id)
        .order_by(LeadActivity.created_at.desc())
        .limit(12)
    )
    if only_user_id is not None:
        stmt = stmt.where(Lead.owner_user_id == only_user_id)
    return stmt


async def _letters_pending(
    session, team_id: uuid.UUID, user_id: int
) -> int:
    """Сколько ручных email-шагов ждёт одобрения у этого селза —
    то же правило разделения очередей, что на экране «Письма»."""
    from sqlalchemy.orm import selectinload

    from leadgen.db.models import Funnel

    rows = (
        await session.execute(
            select(Lead, Funnel)
            .join(SearchQuery, SearchQuery.id == Lead.query_id)
            .join(Funnel, Funnel.id == Lead.funnel_id)
            .options(selectinload(Funnel.steps))
            .where(SearchQuery.team_id == team_id)
            .where(Lead.owner_user_id == user_id)
            .where(Lead.deleted_at.is_(None))
            .where(Lead.archived_at.is_(None))
            .where(Lead.goal_reached_at.is_(None))
            .where(Lead.funnel_id.is_not(None))
        )
    ).all()
    count = 0
    for lead, funnel in rows:
        steps = sorted(funnel.steps, key=lambda st: st.order_index)
        if lead.funnel_step >= len(steps):
            continue
        step = steps[lead.funnel_step]
        if step.kind == "email" and not step.auto:
            count += 1
    return count


_HOT_CATEGORIES = ("interested", "meeting_request")


async def _own_reactions(
    session, team_id: uuid.UUID, user_id: int
) -> list[ReactionRow]:
    """Свежие разобранные ответы по лидам селза, интерес первым."""
    rows = (
        await session.execute(
            select(LeadActivity, Lead)
            .join(Lead, Lead.id == LeadActivity.lead_id)
            .where(LeadActivity.team_id == team_id)
            .where(LeadActivity.kind == "email_replied")
            .where(Lead.owner_user_id == user_id)
            .where(Lead.deleted_at.is_(None))
            .order_by(LeadActivity.created_at.desc())
            .limit(10)
        )
    ).all()
    out: list[ReactionRow] = []
    for a, lead in rows:
        p: dict[str, Any] = a.payload or {}
        out.append(
            ReactionRow(
                lead_id=lead.id,
                lead_name=lead.name,
                category=str(p.get("category") or "other"),
                preview=str(p.get("preview") or p.get("summary") or ""),
                at=a.created_at,
                has_draft=bool(p.get("suggested_reply")),
            )
        )
    out.sort(
        key=lambda r: (r.category not in _HOT_CATEGORIES, r.at),
    )
    return out[:3]


async def _recent_events(
    session, team_id: uuid.UUID, only_user_id: int | None = None
) -> list[EventRow]:
    """«События компании» — the last dozen things that happened."""
    acts = (
        (
            await session.execute(
                _events_stmt(team_id, only_user_id)
            )
        )
        .all()
    )
    # Ярлыки статусов команды: «contacted» в ленте — это баг, а не
    # событие. Незнакомый ключ показываем с большой буквы, не сырым.
    from leadgen.db.models import LeadStatus

    labels = dict(
        (
            await session.execute(
                select(LeadStatus.key, LeadStatus.label).where(
                    LeadStatus.team_id == team_id
                )
            )
        ).all()
    )
    _fallback = {
        "new": "Новый",
        "contacted": "В работе",
        "replied": "Ответил",
        "won": "Клиент",
        "archived": "Архив",
    }

    def _status_label(key: str) -> str:
        return labels.get(key) or _fallback.get(key) or key.capitalize()

    out: list[EventRow] = []
    for a, lead in acts:
        payload: dict[str, Any] = a.payload or {}
        if a.kind == "call":
            outcome = payload.get("outcome")
            titles = {
                "goal": "Цель достигнута",
                "callback": "Назначен перезвон",
                "no_answer": "Недозвон",
                "refused": "Отказ",
                "thinking": "Думает",
                "wrong_number": "Неверный номер",
            }
            text = f"{titles.get(outcome, 'Звонок')} — {lead.name}"
        elif a.kind == "status":
            to = payload.get("to") or payload.get("status")
            text = (
                f"Статус → {_status_label(str(to))} — {lead.name}"
                if to
                else f"Смена статуса — {lead.name}"
            )
        else:
            # Один словарь вместо цепочки elif: виды активностей
            # заводятся в разных местах кодовой базы, и незнакомый
            # вид не должен протекать в интерфейс сырым слагом.
            titles = {
                "funnel_email_sent": "Письмо воронки отправлено",
                "funnel_email_due": "Письмо воронки запланировано",
                "assigned": "Лид назначен",
                "notes": "Заметка",
                "email_replied": "Ответ на письмо",
                "task": "Задача",
                "tag": "Метка",
            }
            text = f"{titles.get(a.kind, 'Событие')} — {lead.name}"
        out.append(
            EventRow(at=a.created_at.strftime("%H:%M"), text=text)
        )
    return out
