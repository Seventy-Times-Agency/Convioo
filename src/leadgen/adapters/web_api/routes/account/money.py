"""``/api/v1/teams/{id}/money`` — вкладка «Деньги и токены».

Только владелец. Бюджет в $ → лимит в токенах, баланс, остановка на
нуле, ручное начисление, расход за месяц (по дням, по типу, по людям)
и история операций.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.routes._helpers import membership
from leadgen.core.services.account import budget as _budget
from leadgen.core.services.account import team_journal
from leadgen.core.services.account import tokens as _tokens
from leadgen.core.services.account.team_permissions import has_full_access
from leadgen.db.models import (
    KIND_HOLD,
    KIND_REFUND,
    KIND_SPEND,
    SearchQuery,
    Team,
    TokenLedger,
    User,
)
from leadgen.db.models.journal import JK_COST_CAP_CHANGED
from leadgen.db.session import session_factory

router = APIRouter(tags=["money"])

SPEND_KINDS = (KIND_HOLD, KIND_REFUND, KIND_SPEND)


class MoneyDay(BaseModel):
    date: str
    tokens: int


class MoneyPerson(BaseModel):
    user_id: int | None
    name: str
    tokens: int


class MoneyOut(BaseModel):
    budget_usd: float | None
    token_price_usd: float
    allowance: int
    balance: int
    spent_month: int
    stop_at_zero: bool
    month: str
    by_day: list[MoneyDay]
    by_kind: dict[str, int]
    by_person: list[MoneyPerson]


class MoneyUpdate(BaseModel):
    budget_usd: float | None = Field(default=None, ge=0, le=1_000_000)
    stop_at_zero: bool | None = None
    #: Явно сбросить бюджет (``budget_usd`` = null без этого флага
    #: означает «не менять»).
    clear_budget: bool = False


class GrantIn(BaseModel):
    tokens: int = Field(ge=1, le=1_000_000)
    reason: str | None = Field(default=None, max_length=200)


class LedgerRow(BaseModel):
    at: str
    kind: str
    amount: int
    balance_after: int
    reason: str | None


async def _owner_team(session, team_id: uuid.UUID, user: User) -> Team:
    team = await session.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")
    ms = await membership(session, team_id, user.id)
    if ms is None or not has_full_access(ms.role):
        raise HTTPException(status_code=403, detail="only the owner or tech manages money")
    return team


async def _snapshot(session, team: Team) -> MoneyOut:
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = (
        await session.execute(
            select(TokenLedger, SearchQuery.user_id, SearchQuery.find_decision_makers)
            .outerjoin(SearchQuery, SearchQuery.id == TokenLedger.search_id)
            .where(TokenLedger.team_id == team.id)
            .where(TokenLedger.kind.in_(SPEND_KINDS))
            .where(TokenLedger.created_at >= month_start)
        )
    ).all()
    by_day: dict[str, int] = defaultdict(int)
    by_user: dict[int | None, int] = defaultdict(int)
    leads = dm = 0
    for led, uid, find_dm in rows:
        spent = -int(led.amount)
        created = led.created_at if led.created_at.tzinfo else led.created_at.replace(tzinfo=timezone.utc)
        by_day[created.date().isoformat()] += spent
        by_user[uid if uid is not None else led.user_id] += spent
        if find_dm:
            half = spent // 2
            dm += half
            leads += spent - half
        else:
            leads += spent
    spent_month = sum(by_day.values())

    ids = [u for u in by_user if u is not None]
    names: dict[int, str] = {}
    if ids:
        for u in (await session.execute(select(User).where(User.id.in_(ids)))).scalars():
            names[u.id] = u.display_name or " ".join(filter(None, [u.first_name, u.last_name])) or f"User {u.id}"
    people = sorted(
        (MoneyPerson(user_id=u, name=names.get(u, "—") if u else "система", tokens=v) for u, v in by_user.items() if v),
        key=lambda p: -p.tokens,
    )
    days = []
    for d in range(1, now.day + 1):
        key = month_start.replace(day=d).date().isoformat()
        days.append(MoneyDay(date=key, tokens=max(0, by_day.get(key, 0))))

    return MoneyOut(
        budget_usd=float(team.monthly_cost_cap_usd) if team.monthly_cost_cap_usd is not None else None,
        token_price_usd=_budget.token_price_usd(),
        allowance=_budget.allowance(team.monthly_cost_cap_usd),
        balance=int(team.token_balance),
        spent_month=spent_month,
        stop_at_zero=bool(team.token_stop_at_zero),
        month=_budget.month_key(now),
        by_day=days,
        by_kind={"leads": leads, "decision_makers": dm},
        by_person=people,
    )


@router.get("/api/v1/teams/{team_id}/money", response_model=MoneyOut)
async def get_money(team_id: uuid.UUID, current_user: User = Depends(get_current_user)) -> MoneyOut:
    async with session_factory() as session:
        team = await _owner_team(session, team_id, current_user)
        if await _budget.ensure_refill(session, team):
            await session.commit()
            await session.refresh(team)
        return await _snapshot(session, team)


@router.patch("/api/v1/teams/{team_id}/money", response_model=MoneyOut)
async def update_money(
    team_id: uuid.UUID, body: MoneyUpdate, current_user: User = Depends(get_current_user)
) -> MoneyOut:
    async with session_factory() as session:
        team = await _owner_team(session, team_id, current_user)
        if body.clear_budget or body.budget_usd is not None:
            new = None if body.clear_budget or not body.budget_usd else float(body.budget_usd)
            old = float(team.monthly_cost_cap_usd) if team.monthly_cost_cap_usd is not None else None
            if new != old:
                await team_journal.record(
                    session,
                    team.id,
                    JK_COST_CAP_CHANGED,
                    actor=current_user,
                    actor_role=(await membership(session, team.id, current_user.id)).role,
                    payload={"from": old, "to": new},
                )
                await _budget.change_budget(session, team, new, user_id=current_user.id)
        if body.stop_at_zero is not None:
            team.token_stop_at_zero = body.stop_at_zero
        await session.commit()
        await session.refresh(team)
        return await _snapshot(session, team)


@router.post("/api/v1/teams/{team_id}/money/grant", response_model=MoneyOut)
async def grant_tokens(
    team_id: uuid.UUID, body: GrantIn, current_user: User = Depends(get_current_user)
) -> MoneyOut:
    async with session_factory() as session:
        team = await _owner_team(session, team_id, current_user)
        await _tokens.topup(
            session,
            team.id,
            body.tokens,
            user_id=current_user.id,
            reason=body.reason or "добавлено владельцем",
        )
        await session.commit()
        await session.refresh(team)
        return await _snapshot(session, team)


@router.get("/api/v1/teams/{team_id}/money/ledger", response_model=list[LedgerRow])
async def money_ledger(team_id: uuid.UUID, current_user: User = Depends(get_current_user)) -> list[LedgerRow]:
    async with session_factory() as session:
        await _owner_team(session, team_id, current_user)
        rows = (
            await session.execute(
                select(TokenLedger)
                .where(TokenLedger.team_id == team_id)
                .order_by(TokenLedger.created_at.desc())
                .limit(100)
            )
        ).scalars()
        return [
            LedgerRow(
                at=r.created_at.isoformat(),
                kind=r.kind,
                amount=int(r.amount),
                balance_after=int(r.balance_after),
                reason=r.reason,
            )
            for r in rows
        ]
