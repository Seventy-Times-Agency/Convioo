"""``/api/v1/work/*`` — the sales rep's call-mode surface (Wave 1).

The queue orders the rep's assigned leads the way the mockup reads:
перезвоны (due callbacks) → горячие (score ≥ 75) → остальные. The
one-button outcome endpoint applies the funnel engine's rules (
no-answer rule, callback scheduling, goal stamping) and writes the
timeline activity, so the screen's three states stay thin clients.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.routes._helpers import membership
from leadgen.core.services.funnel_engine import (
    CALL_OUTCOMES,
    apply_call_outcome,
)
from leadgen.core.services.team_permissions import is_sales
from leadgen.db.models import (
    Funnel,
    Lead,
    LeadActivity,
    SearchQuery,
    User,
)
from leadgen.db.session import session_factory

router = APIRouter(tags=["work"])

HOT_SCORE = 75.0


class QueueLead(BaseModel):
    id: uuid.UUID
    name: str
    phone: str | None
    score: float | None
    bucket: str  # callback | hot | rest
    next_touch_at: datetime | None
    lead_status: str
    funnel_id: uuid.UUID | None
    business_language: str | None = None


class WorkQueueResponse(BaseModel):
    callbacks: list[QueueLead]
    hot: list[QueueLead]
    rest: list[QueueLead]
    total: int


class CallOutcomeRequest(BaseModel):
    outcome: str
    callback_at: datetime | None = None
    note: str | None = Field(default=None, max_length=4000)


class CallOutcomeResponse(BaseModel):
    ok: bool = True
    result: dict[str, Any]


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes even for timezone=True columns —
    normalise to UTC before comparing."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _auto_status_for(outcome: str, current: str | None) -> str | None:
    """CRM двигается сама: куда исход звонка ведёт карточку.

    Ключи — стандартной палитры (мигрируются каждой команде); если
    команда выкинула колонку, карточка остаётся на месте — доска
    важнее принудительного порядка.
    """
    if outcome == "goal":
        return "won"
    if outcome in ("refused", "wrong_number"):
        return "lost"
    if outcome in ("callback", "thinking") and (current in (None, "new")):
        return "contacted"
    return None


def _bucket_of(lead: Lead, now: datetime) -> str:
    due = _aware(lead.next_touch_at)
    if due is not None and due <= now:
        return "callback"
    if (lead.score_ai or 0) >= HOT_SCORE:
        return "hot"
    return "rest"


@router.get("/api/v1/work/queue", response_model=WorkQueueResponse)
async def work_queue(
    team_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=300),
    current_user: User = Depends(get_current_user),
) -> WorkQueueResponse:
    """The caller's call queue inside a team: their assigned,
    unfinished leads bucketed перезвоны → горячие → остальные."""
    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        ms = await membership(session, team_id, current_user.id)
        if ms is None:
            raise HTTPException(status_code=403, detail="not a team member")
        rows = (
            (
                await session.execute(
                    select(Lead)
                    .join(SearchQuery, SearchQuery.id == Lead.query_id)
                    .where(SearchQuery.team_id == team_id)
                    .where(Lead.owner_user_id == current_user.id)
                    .where(Lead.deleted_at.is_(None))
                    .where(Lead.archived_at.is_(None))
                    .where(Lead.goal_reached_at.is_(None))
                    .order_by(
                        Lead.next_touch_at.asc().nullslast(),
                        Lead.score_ai.desc().nullslast(),
                    )
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )

    buckets: dict[str, list[QueueLead]] = {
        "callback": [],
        "hot": [],
        "rest": [],
    }
    for lead in rows:
        b = _bucket_of(lead, now)
        buckets[b].append(
            QueueLead(
                id=lead.id,
                name=lead.name,
                phone=lead.phone,
                score=lead.score_ai,
                bucket=b,
                next_touch_at=lead.next_touch_at,
                lead_status=lead.lead_status,
                funnel_id=lead.funnel_id,
                business_language=lead.business_language,
            )
        )
    buckets["callback"].sort(key=lambda q: _aware(q.next_touch_at) or now)
    return WorkQueueResponse(
        callbacks=buckets["callback"],
        hot=buckets["hot"],
        rest=buckets["rest"],
        total=len(rows),
    )


@router.post(
    "/api/v1/leads/{lead_id}/call-outcome",
    response_model=CallOutcomeResponse,
)
async def call_outcome(
    lead_id: uuid.UUID,
    body: CallOutcomeRequest,
    current_user: User = Depends(get_current_user),
) -> CallOutcomeResponse:
    """One-button outcome from call mode. Applies the funnel rules
    (no-answer → 3 tries → pause → free pool; callback; thinking →
    next touch; goal → stamp + goal config back) and writes the
    ``call`` activity with the rep's note."""
    if body.outcome not in CALL_OUTCOMES:
        raise HTTPException(
            status_code=400,
            detail=f"outcome must be one of {', '.join(CALL_OUTCOMES)}",
        )
    async with session_factory() as session:
        lead = await session.get(Lead, lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="lead not found")
        search = await session.get(SearchQuery, lead.query_id)
        allowed = search is not None and search.user_id == current_user.id
        team_id = search.team_id if search is not None else None
        if not allowed and team_id is not None:
            ms = await membership(session, team_id, current_user.id)
            allowed = ms is not None and (
                not is_sales(ms.role)
                or lead.owner_user_id == current_user.id
            )
        if not allowed:
            raise HTTPException(status_code=404, detail="lead not found")

        funnel: Funnel | None = None
        if lead.funnel_id is not None:
            funnel = (
                await session.execute(
                    select(Funnel)
                    .where(Funnel.id == lead.funnel_id)
                    .options(selectinload(Funnel.steps))
                )
            ).scalar_one_or_none()

        result = apply_call_outcome(
            lead,
            funnel,
            body.outcome,
            callback_at=body.callback_at,
        )
        if body.note:
            result["note"] = True

        # Доска показывает реальную картину: исход сам двигает
        # карточку по колонкам, без ручного перетаскивания.
        desired = _auto_status_for(body.outcome, lead.lead_status)
        if desired and desired != lead.lead_status:
            allowed_keys: set[str]
            if team_id is None:
                from leadgen.adapters.web_api.routes._helpers import (
                    LEGACY_LEAD_STATUS_KEYS,
                )

                allowed_keys = set(LEGACY_LEAD_STATUS_KEYS)
            else:
                from leadgen.db.models import LeadStatus

                allowed_keys = set(
                    (
                        await session.execute(
                            select(LeadStatus.key).where(
                                LeadStatus.team_id == team_id
                            )
                        )
                    ).scalars()
                )
            if desired in allowed_keys:
                lead.lead_status = desired
                result["status_to"] = desired

        session.add(
            LeadActivity(
                lead_id=lead.id,
                user_id=current_user.id,
                team_id=team_id,
                kind="call",
                payload={
                    "outcome": body.outcome,
                    "note": (body.note or None),
                    **{
                        k: v
                        for k, v in result.items()
                        if k not in ("outcome", "note")
                    },
                },
            )
        )
        await session.commit()

        # Цель достигнута → менеджерам отдела (Wave 1, события).
        if body.outcome == "goal" and team_id is not None:
            try:
                from leadgen.core.services.team_events import goal_reached

                rep_name = (
                    current_user.display_name
                    or " ".join(
                        filter(
                            None,
                            [current_user.first_name, current_user.last_name],
                        )
                    )
                    or None
                )
                await goal_reached(
                    session,
                    lead=lead,
                    team_id=team_id,
                    funnel=funnel,
                    rep_name=rep_name,
                )
            except Exception:  # noqa: BLE001 — уведомление не роняет исход
                pass
        return CallOutcomeResponse(ok=True, result=result)


class LetterRow(BaseModel):
    lead_id: uuid.UUID
    lead_name: str
    funnel_name: str | None = None
    step_index: int
    steps_total: int
    note: str | None = None
    due_at: datetime | None = None


class LettersResponse(BaseModel):
    """Экран «Письма» — Letters.dc.html.

    Две очереди: то, что ждёт одобрения человека, и то, что уйдёт
    автоматом. Разделяет их флаг ``auto`` у шага воронки — то же
    поле, по которому решает воркер, так что экран показывает ровно
    то, что произойдёт, а не свою версию правды.

    «Прогрев домена, день N» из макета — это разгон лимита отправки
    (20 писем в первый день, дальше по нарастающей до 200). Величина
    настоящая, берётся из того же расчёта, что и при реальной отправке.
    """

    cap: int
    sent_today: int
    warmup_day: int
    pending_approval: list[LetterRow]
    scheduled: list[LetterRow]


@router.get("/api/v1/work/letters", response_model=LettersResponse)
async def work_letters(
    team_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> LettersResponse:
    from leadgen.core.services.send_quota import (
        _days_connected,
        warmup_cap,
    )
    from leadgen.db.models import EmailDailySend

    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        ms = await membership(session, team_id, current_user.id)
        if ms is None:
            raise HTTPException(status_code=403, detail="not a team member")

        days, _provider = await _days_connected(session, current_user.id, now)
        cap = warmup_cap(days)
        row = (
            await session.execute(
                select(EmailDailySend)
                .where(EmailDailySend.user_id == current_user.id)
                .where(EmailDailySend.send_date == now.date())
            )
        ).scalar_one_or_none()
        sent = int(row.sent_count) if row is not None else 0

        stmt = (
            select(Lead, Funnel)
            .join(SearchQuery, SearchQuery.id == Lead.query_id)
            .join(Funnel, Funnel.id == Lead.funnel_id)
            .options(selectinload(Funnel.steps))
            .where(SearchQuery.team_id == team_id)
            .where(Lead.deleted_at.is_(None))
            .where(Lead.archived_at.is_(None))
            .where(Lead.goal_reached_at.is_(None))
            .where(Lead.funnel_id.is_not(None))
        )
        # Селз видит только свои — то же правило, что в очереди звонков.
        if is_sales(ms.role):
            stmt = stmt.where(Lead.owner_user_id == current_user.id)
        rows = (await session.execute(stmt)).all()

    pending: list[LetterRow] = []
    scheduled: list[LetterRow] = []
    for lead, funnel in rows:
        steps = sorted(funnel.steps, key=lambda s: s.order_index)
        idx = lead.funnel_step
        if idx >= len(steps):
            continue
        step = steps[idx]
        if step.kind != "email":
            continue
        item = LetterRow(
            lead_id=lead.id,
            lead_name=lead.name,
            funnel_name=funnel.name,
            step_index=idx + 1,
            steps_total=len(steps),
            note=step.note,
            due_at=lead.next_touch_at,
        )
        (scheduled if step.auto else pending).append(item)

    pending.sort(key=lambda r: _aware(r.due_at) or now)
    scheduled.sort(key=lambda r: _aware(r.due_at) or now)
    return LettersResponse(
        cap=cap,
        sent_today=sent,
        warmup_day=days,
        pending_approval=pending,
        scheduled=scheduled,
    )


# ── пульт прозвона для руководителя ────────────────────────────────────


class WorkOverviewRow(BaseModel):
    user_id: int
    name: str
    role: str
    squad_name: str | None = None
    dials: int = 0
    talks: int = 0
    goals: int = 0
    overdue_callbacks: int = 0
    queue_total: int = 0
    last_call_at: datetime | None = None


class WorkOverviewResponse(BaseModel):
    rows: list[WorkOverviewRow]
    dials: int = 0
    talks: int = 0
    goals: int = 0


@router.get(
    "/api/v1/teams/{team_id}/work/overview",
    response_model=WorkOverviewResponse,
)
async def work_overview(
    team_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> WorkOverviewResponse:
    """Живая картина прозвона по каждому сотруднику — за сегодня.

    Владелец и РОП видят всех, тимлид — свою команду. Селзу пульт
    не отдаётся: его экран — собственная очередь.
    """
    from leadgen.core.services.squads import visible_member_ids
    from leadgen.core.services.team_permissions import (
        PERM_VIEW_ANALYTICS,
        has_permission,
        normalize_role,
    )
    from leadgen.db.models import LeadActivity, TeamMembership, TeamSquad

    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    async with session_factory() as session:
        ms = await membership(session, team_id, current_user.id)
        if ms is None or not has_permission(ms.role, PERM_VIEW_ANALYTICS):
            raise HTTPException(
                status_code=403,
                detail="your role can't view the calling overview",
            )
        scope_ids = await visible_member_ids(session, team_id, current_user.id)

        members = (
            await session.execute(
                select(TeamMembership, User)
                .join(User, User.id == TeamMembership.user_id)
                .where(TeamMembership.team_id == team_id)
            )
        ).all()
        squads = {
            sq.id: sq.name
            for sq in (
                await session.execute(
                    select(TeamSquad).where(TeamSquad.team_id == team_id)
                )
            ).scalars()
        }

        acts = (
            (
                await session.execute(
                    select(LeadActivity)
                    .where(LeadActivity.team_id == team_id)
                    .where(LeadActivity.kind == "call")
                    .where(LeadActivity.created_at >= day_start)
                )
            )
            .scalars()
            .all()
        )

        leads = (
            (
                await session.execute(
                    select(Lead)
                    .join(SearchQuery, SearchQuery.id == Lead.query_id)
                    .where(SearchQuery.team_id == team_id)
                    .where(Lead.deleted_at.is_(None))
                    .where(Lead.archived_at.is_(None))
                    .where(Lead.goal_reached_at.is_(None))
                    .where(Lead.owner_user_id.is_not(None))
                )
            )
            .scalars()
            .all()
        )

    def _aware(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    rows: list[WorkOverviewRow] = []
    for mem, u in members:
        if scope_ids is not None and u.id not in scope_ids:
            continue
        role = normalize_role(mem.role)
        mine_acts = [a for a in acts if a.user_id == u.id]
        mine_leads = [lead for lead in leads if lead.owner_user_id == u.id]
        # Пульт про тех, кто звонит: селзы и тимлиды всегда в списке,
        # РОП и владелец — только если сегодня сами брали трубку или
        # держат лидов.
        if role in ("owner", "admin") and not mine_acts and not mine_leads:
            continue
        talks = sum(
            1
            for a in mine_acts
            if (a.payload or {}).get("outcome")
            not in ("no_answer", "wrong_number")
        )
        goals = sum(
            1
            for a in mine_acts
            if (a.payload or {}).get("outcome") == "goal"
        )
        overdue = sum(
            1
            for lead in mine_leads
            if lead.next_touch_at is not None
            and _aware(lead.next_touch_at) <= now
        )
        last = max(
            (a.created_at for a in mine_acts), default=None
        )
        rows.append(
            WorkOverviewRow(
                user_id=u.id,
                name=u.display_name or u.first_name or f"#{u.id}",
                role=role,
                squad_name=squads.get(mem.squad_id),
                dials=len(mine_acts),
                talks=talks,
                goals=goals,
                overdue_callbacks=overdue,
                queue_total=len(mine_leads),
                last_call_at=_aware(last),
            )
        )
    rows.sort(key=lambda r: (-r.goals, -r.dials, r.name))
    scoped_uids = {r.user_id for r in rows}
    scoped_acts = [a for a in acts if a.user_id in scoped_uids]
    return WorkOverviewResponse(
        rows=rows,
        dials=len(scoped_acts),
        talks=sum(
            1
            for a in scoped_acts
            if (a.payload or {}).get("outcome")
            not in ("no_answer", "wrong_number")
        ),
        goals=sum(
            1
            for a in scoped_acts
            if (a.payload or {}).get("outcome") == "goal"
        ),
    )
