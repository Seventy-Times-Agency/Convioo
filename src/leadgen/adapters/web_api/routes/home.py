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
            return HomeResponse(
                role=role,
                scope=team.name if team else "",
                queue_total=len(mine),
                next_callback_at=next_cb,
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


async def _recent_events(session, team_id: uuid.UUID) -> list[EventRow]:
    """«События компании» — the last dozen things that happened."""
    acts = (
        (
            await session.execute(
                select(LeadActivity, Lead)
                .join(Lead, Lead.id == LeadActivity.lead_id)
                .where(LeadActivity.team_id == team_id)
                .order_by(LeadActivity.created_at.desc())
                .limit(12)
            )
        )
        .all()
    )
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
                f"Статус → {to} — {lead.name}"
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
