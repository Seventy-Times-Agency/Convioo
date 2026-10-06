"""``/api/v1/teams/{id}/sales-analytics`` — аналитика отдела продаж.

Один запрос — все срезы страницы «Аналитика → Продажи»: числа сверху,
выводы (правилами), по дням, воронка, исходы и возражения, карта
дозвона по часам, письма, конверсия по оценке ИИ и по нишам, люди.
Считается по ``LeadActivity`` (исходы из режима «Работа»), ``Call``
(разборы ИИ) и ``Lead`` (статусы, суммы, касания).
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.routes._helpers import membership
from leadgen.core.services.account.team_permissions import (
    PERM_VIEW_ANALYTICS,
    ROLE_MANAGER,
    has_permission,
    normalize_role,
)
from leadgen.core.services.sales.funnel_engine import TALK_OUTCOMES
from leadgen.db.models import (
    Call,
    Lead,
    LeadActivity,
    SearchQuery,
    TeamMembership,
    User,
)
from leadgen.db.session import session_factory

router = APIRouter(tags=["sales-analytics"])

PERIOD_DAYS = {"week": 7, "month": 30, "quarter": 90}
OUTCOME_KEYS = ("goal", "callback", "thinking", "refused", "no_answer", "wrong_number")
HOT = 75.0
WARM = 50.0


class Kpi(BaseModel):
    goals: int
    goals_prev: int
    goals_plan: int | None
    dials: int
    dials_prev: int
    dials_plan: int | None
    talks: int
    reach_rate: float | None
    quality_avg: float | None
    quality_n: int
    talk_avg_sec: int | None
    money_in_work: float
    money_closed: float
    closed_count: int
    days_to_first_call: float | None
    overdue_callbacks: int
    cooling_leads: int


class Insight(BaseModel):
    kind: str  # up | warn | bad | info
    text: str


class DayPoint(BaseModel):
    date: str
    dials: int
    talks: int
    goals: int


class FunnelStep(BaseModel):
    key: str
    count: int
    #: доля к предыдущему шагу, None у первого
    rate: float | None


class Bucket(BaseModel):
    key: str
    count: int
    share: float


class HeatCell(BaseModel):
    weekday: int  # 0 = пн
    hour: int
    dials: int
    talks: int


class Emails(BaseModel):
    sent: int
    replied: int
    hot: int


class TempRow(BaseModel):
    temp: str
    talks: int
    goals: int
    rate: float | None


class NicheRow(BaseModel):
    niche: str
    talks: int
    goals: int
    rate: float | None


class MemberRow(BaseModel):
    user_id: int
    name: str
    role: str
    avatar_url: str | None = None
    dials: int
    dials_plan: int | None
    talks: int
    reach_rate: float | None
    goals: int
    goals_plan: int | None
    quality_avg: float | None
    talk_avg_sec: int | None
    overdue: int
    hot_leads: int


class SalesAnalytics(BaseModel):
    period: str
    period_from: str
    period_to: str
    kpi: Kpi
    insights: list[Insight]
    by_day: list[DayPoint]
    funnel: list[FunnelStep]
    outcomes: list[Bucket]
    objections: list[Bucket]
    heatmap: list[HeatCell]
    best_window: str | None
    emails: Emails
    by_temp: list[TempRow]
    by_niche: list[NicheRow]
    members: list[MemberRow]


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _temp(score: float | None) -> str:
    if score is None:
        return "cold"
    if score >= HOT:
        return "hot"
    if score >= WARM:
        return "warm"
    return "cold"


@router.get("/api/v1/teams/{team_id}/sales-analytics", response_model=SalesAnalytics)
async def sales_analytics(
    team_id: uuid.UUID,
    period: str = Query(default="month", pattern="^(week|month|quarter)$"),
    squad_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
) -> SalesAnalytics:
    now = datetime.now(timezone.utc)
    days = PERIOD_DAYS[period]
    since = now - timedelta(days=days)
    prev_since = since - timedelta(days=days)

    async with session_factory() as session:
        ms = await membership(session, team_id, current_user.id)
        if ms is None or not has_permission(ms.role, PERM_VIEW_ANALYTICS):
            raise HTTPException(status_code=403, detail="your role can't view analytics")
        # Тимлид видит только свою подкоманду — как в панели команды.
        if normalize_role(ms.role) == ROLE_MANAGER:
            squad_id = ms.squad_id

        rows = (
            await session.execute(
                select(TeamMembership, User)
                .join(User, User.id == TeamMembership.user_id)
                .where(TeamMembership.team_id == team_id)
                .order_by(TeamMembership.created_at)
            )
        ).all()
        if squad_id is not None:
            rows = [(m, u) for m, u in rows if m.squad_id == squad_id or m.user_id == current_user.id]
        member_ids = {u.id for _m, u in rows}

        acts = (
            (
                await session.execute(
                    select(LeadActivity)
                    .where(LeadActivity.team_id == team_id)
                    .where(LeadActivity.kind.in_(["call", "email_sent", "email_replied"]))
                    .where(LeadActivity.created_at >= prev_since)
                )
            )
            .scalars()
            .all()
        )
        calls = (
            (
                await session.execute(
                    select(Call)
                    .where(Call.team_id == team_id)
                    .where(Call.created_at >= since)
                )
            )
            .scalars()
            .all()
        )
        leads = (
            (
                await session.execute(
                    select(Lead, SearchQuery.niche)
                    .join(SearchQuery, SearchQuery.id == Lead.query_id)
                    .where(SearchQuery.team_id == team_id)
                    .where(Lead.deleted_at.is_(None))
                )
            )
            .all()
        )

    # ── подготовка ───────────────────────────────────────────────────
    lead_by_id: dict[uuid.UUID, Lead] = {}
    niche_by_lead: dict[uuid.UUID, str] = {}
    for lead, niche in leads:
        lead_by_id[lead.id] = lead
        niche_by_lead[lead.id] = niche or ""

    def in_scope(a: LeadActivity) -> bool:
        return a.user_id in member_ids if squad_id is not None else True

    cur_calls = [
        a for a in acts if a.kind == "call" and _utc(a.created_at) >= since and in_scope(a)
    ]
    prev_calls = [
        a for a in acts if a.kind == "call" and _utc(a.created_at) < since and in_scope(a)
    ]
    outcome_of = lambda a: (a.payload or {}).get("outcome")  # noqa: E731
    is_talk = lambda a: outcome_of(a) in TALK_OUTCOMES  # noqa: E731
    is_goal = lambda a: outcome_of(a) == "goal"  # noqa: E731

    dials = len(cur_calls)
    talks = sum(1 for a in cur_calls if is_talk(a))
    goals = sum(1 for a in cur_calls if is_goal(a))
    dials_prev = len(prev_calls)
    goals_prev = sum(1 for a in prev_calls if is_goal(a))

    # План: суммы по людям в периоде (рабочие дни ≈ 5/7).
    workdays = max(1, round(days * 5 / 7))
    weeks = max(1, round(days / 7))
    dials_plan = sum((m.target_calls_day or 0) for m, _u in rows) * workdays or None
    goals_plan = sum((m.target_goals_week or 0) for m, _u in rows) * weeks or None

    # Качество и длительность — из разборов ИИ.
    q_vals: list[float] = []
    talk_secs: list[int] = []
    objections: Counter[str] = Counter()
    q_by_user: dict[int, list[float]] = defaultdict(list)
    talk_by_user: dict[int, list[int]] = defaultdict(list)
    for c in calls:
        if squad_id is not None and c.user_id not in member_ids:
            continue
        a = c.analysis or {}
        q = a.get("quality_score")
        if isinstance(q, (int, float)):
            q_vals.append(float(q))
            if c.user_id is not None:
                q_by_user[c.user_id].append(float(q))
        if c.talk_sec:
            talk_secs.append(int(c.talk_sec))
            if c.user_id is not None:
                talk_by_user[c.user_id].append(int(c.talk_sec))
        for o in a.get("objections") or []:
            if isinstance(o, str) and o.strip():
                objections[o.strip().lower()] += 1

    # Деньги, просрочки, остывающие, скорость до первого звонка.
    money_in_work = 0.0
    money_closed = 0.0
    closed_count = 0
    overdue = 0
    overdue_by_user: Counter[int] = Counter()
    cooling = 0
    hot_by_user: Counter[int] = Counter()
    first_call_days: list[float] = []
    first_call_by_lead: dict[uuid.UUID, datetime] = {}
    for a in sorted(cur_calls, key=lambda x: x.created_at):
        first_call_by_lead.setdefault(a.lead_id, _utc(a.created_at))
    for lead in lead_by_id.values():
        if lead.archived_at is not None:
            continue
        owner = lead.owner_user_id
        if squad_id is not None and owner not in member_ids:
            continue
        status = lead.lead_status
        if status == "won":
            if lead.deal_value:
                money_closed += float(lead.deal_value)
            closed_count += 1
        elif owner is not None and status != "lost" and lead.deal_value:
            money_in_work += float(lead.deal_value)
        if owner is not None and lead.next_touch_at and _utc(lead.next_touch_at) < now and lead.goal_reached_at is None:
            overdue += 1
            overdue_by_user[owner] += 1
        if (
            owner is not None
            and status not in ("won", "lost")
            and lead.goal_reached_at is None
            and (lead.last_touched_at is None or _utc(lead.last_touched_at) < now - timedelta(days=7))
            and _utc(lead.created_at) < now - timedelta(days=7)
        ):
            cooling += 1
        if owner is not None and (lead.score_ai or 0) >= HOT:
            hot_by_user[owner] += 1
        fc = first_call_by_lead.get(lead.id)
        if fc is not None:
            first_call_days.append(max(0.0, (fc - _utc(lead.created_at)).total_seconds() / 86400))

    kpi = Kpi(
        goals=goals,
        goals_prev=goals_prev,
        goals_plan=goals_plan,
        dials=dials,
        dials_prev=dials_prev,
        dials_plan=dials_plan,
        talks=talks,
        reach_rate=_rate(talks, dials),
        quality_avg=round(sum(q_vals) / len(q_vals), 1) if q_vals else None,
        quality_n=len(q_vals),
        talk_avg_sec=round(sum(talk_secs) / len(talk_secs)) if talk_secs else None,
        money_in_work=round(money_in_work, 2),
        money_closed=round(money_closed, 2),
        closed_count=closed_count,
        days_to_first_call=round(sum(first_call_days) / len(first_call_days), 1) if first_call_days else None,
        overdue_callbacks=overdue,
        cooling_leads=cooling,
    )

    # ── по дням ──────────────────────────────────────────────────────
    day_map: dict[str, DayPoint] = {}
    for i in range(days):
        d = (since + timedelta(days=i + 1)).date().isoformat()
        day_map[d] = DayPoint(date=d, dials=0, talks=0, goals=0)
    for a in cur_calls:
        d = _utc(a.created_at).date().isoformat()
        p = day_map.get(d)
        if p is None:
            continue
        p.dials += 1
        if is_talk(a):
            p.talks += 1
        if is_goal(a):
            p.goals += 1

    # ── воронка ──────────────────────────────────────────────────────
    scoped_leads = [
        lead
        for lead in lead_by_id.values()
        if lead.archived_at is None and (squad_id is None or lead.owner_user_id in member_ids)
    ]
    found = sum(1 for lead in scoped_leads if _utc(lead.created_at) >= since)
    in_work = sum(1 for lead in scoped_leads if lead.owner_user_id is not None)
    deals = sum(1 for lead in scoped_leads if lead.lead_status == "won" and _utc(lead.created_at) >= since)
    steps_raw = [("found", found), ("in_work", in_work), ("dials", dials), ("talks", talks), ("goals", goals), ("deals", deals)]
    funnel: list[FunnelStep] = []
    prev: int | None = None
    for key, cnt in steps_raw:
        funnel.append(FunnelStep(key=key, count=cnt, rate=None if prev is None else _rate(cnt, prev)))
        prev = cnt

    # ── исходы и возражения ──────────────────────────────────────────
    oc = Counter(outcome_of(a) for a in cur_calls if outcome_of(a))
    outcomes = [Bucket(key=k, count=oc.get(k, 0), share=round(oc.get(k, 0) / dials, 3) if dials else 0.0) for k in OUTCOME_KEYS]
    n_analyzed = max(1, len(q_vals))
    objections_out = [
        Bucket(key=k, count=v, share=round(v / n_analyzed, 3)) for k, v in objections.most_common(5)
    ]

    # ── карта дозвона по часам (локальное время не знаем — UTC) ──────
    heat: dict[tuple[int, int], list[int]] = defaultdict(lambda: [0, 0])
    for a in cur_calls:
        t = _utc(a.created_at)
        cell = heat[(t.weekday(), t.hour)]
        cell[0] += 1
        if is_talk(a):
            cell[1] += 1
    heatmap = [HeatCell(weekday=w, hour=h, dials=v[0], talks=v[1]) for (w, h), v in sorted(heat.items())]
    best_window: str | None = None
    best = [(c.talks / c.dials, c) for c in heatmap if c.dials >= 5]
    if best:
        best.sort(key=lambda x: -x[0])
        r, c = best[0]
        best_window = f"{c.weekday}:{c.hour}:{round(r * 100)}"

    # ── письма ───────────────────────────────────────────────────────
    sent = sum(1 for a in acts if a.kind == "email_sent" and _utc(a.created_at) >= since and in_scope(a))
    replied_acts = [a for a in acts if a.kind == "email_replied" and _utc(a.created_at) >= since and in_scope(a)]
    hot_replies = sum(
        1 for a in replied_acts if (a.payload or {}).get("category") in ("interested", "meeting_request")
    )
    emails = Emails(sent=sent, replied=len(replied_acts), hot=hot_replies)

    # ── конверсия по оценке ИИ и по нишам ────────────────────────────
    temp_t: Counter[str] = Counter()
    temp_g: Counter[str] = Counter()
    niche_t: Counter[str] = Counter()
    niche_g: Counter[str] = Counter()
    for a in cur_calls:
        if not is_talk(a):
            continue
        lead = lead_by_id.get(a.lead_id)
        tkey = _temp(lead.score_ai if lead else None)
        nkey = niche_by_lead.get(a.lead_id, "")
        temp_t[tkey] += 1
        niche_t[nkey] += 1
        if is_goal(a):
            temp_g[tkey] += 1
            niche_g[nkey] += 1
    by_temp = [TempRow(temp=k, talks=temp_t[k], goals=temp_g[k], rate=_rate(temp_g[k], temp_t[k])) for k in ("hot", "warm", "cold")]
    by_niche = sorted(
        (NicheRow(niche=k or "—", talks=v, goals=niche_g[k], rate=_rate(niche_g[k], v)) for k, v in niche_t.items()),
        key=lambda r: (-(r.rate or 0), -r.talks),
    )[:6]

    # ── люди ─────────────────────────────────────────────────────────
    d_by_user: Counter[int] = Counter()
    t_by_user: Counter[int] = Counter()
    g_by_user: Counter[int] = Counter()
    for a in cur_calls:
        if a.user_id is None:
            continue
        d_by_user[a.user_id] += 1
        if is_talk(a):
            t_by_user[a.user_id] += 1
        if is_goal(a):
            g_by_user[a.user_id] += 1
    members: list[MemberRow] = []
    for m, u in rows:
        name = u.display_name or " ".join(filter(None, [u.first_name, u.last_name])) or f"User {u.id}"
        qs = q_by_user.get(u.id, [])
        ts = talk_by_user.get(u.id, [])
        members.append(
            MemberRow(
                user_id=u.id,
                name=name,
                role=m.role,
                avatar_url=u.avatar_url,
                dials=d_by_user[u.id],
                dials_plan=(m.target_calls_day or 0) * workdays or None,
                talks=t_by_user[u.id],
                reach_rate=_rate(t_by_user[u.id], d_by_user[u.id]),
                goals=g_by_user[u.id],
                goals_plan=(m.target_goals_week or 0) * weeks or None,
                quality_avg=round(sum(qs) / len(qs), 1) if qs else None,
                talk_avg_sec=round(sum(ts) / len(ts)) if ts else None,
                overdue=overdue_by_user[u.id],
                hot_leads=hot_by_user[u.id],
            )
        )

    # ── выводы правилами ─────────────────────────────────────────────
    insights: list[Insight] = []
    if goals_prev or goals:
        diff = goals - goals_prev
        top = max(members, key=lambda r: r.goals, default=None)
        who = f" — за счёт {top.name}" if top and top.goals and diff > 0 else ""
        if diff > 0:
            insights.append(Insight(kind="up", text=f"Целей +{diff} к прошлому периоду{who}."))
        elif diff < 0:
            insights.append(Insight(kind="bad", text=f"Целей {diff} к прошлому периоду."))
    laggards = [r for r in members if r.dials_plan and r.dials / r.dials_plan < 0.5]
    for r in laggards[:2]:
        pct = round(r.dials / (r.dials_plan or 1) * 100)
        tail = f", {r.overdue} просроченных перезвонов" if r.overdue else ""
        insights.append(Insight(kind="warn", text=f"{r.name} — {pct}% плана по наборам{tail}."))
    if objections_out and objections_out[0].share >= 0.2:
        o = objections_out[0]
        insights.append(Insight(kind="info", text=f"«{o.key}» — возражение №1, {round(o.share * 100)}% разобранных разговоров."))
    if overdue and not laggards:
        insights.append(Insight(kind="bad", text=f"{overdue} перезвонов просрочены."))
    if kpi.reach_rate is not None and dials >= 20 and kpi.reach_rate < 0.4:
        insights.append(Insight(kind="warn", text=f"Дозвон {round(kpi.reach_rate * 100)}% — проверить время звонков и номера."))
    if cooling >= 10:
        insights.append(Insight(kind="info", text=f"{cooling} лидов в работе без касания 7+ дней — вернуть в очередь."))
    if not insights:
        insights.append(Insight(kind="info", text="Мало данных за период: выводы появятся после первых звонков."))

    return SalesAnalytics(
        period=period,
        period_from=since.isoformat(),
        period_to=now.isoformat(),
        kpi=kpi,
        insights=insights[:4],
        by_day=list(day_map.values()),
        funnel=funnel,
        outcomes=outcomes,
        objections=objections_out,
        heatmap=heatmap,
        best_window=best_window,
        emails=emails,
        by_temp=by_temp,
        by_niche=by_niche,
        members=members,
    )
