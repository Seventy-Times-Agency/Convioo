"""Учёт токенов команды: сколько стоит запуск и как списывается.

Правило, от которого всё считается: **один базовый лид — один токен**.
Базовый лид это компания, найденная и оценённая. Всё, что дороже,
добавляется сверху отдельными надбавками.

Цены в токенах и цена самого токена — разные вопросы. Здесь только
первое. Сколько стоит токен в деньгах, решается позже, когда наберётся
статистика по настоящей себестоимости (она считается в долларах в
``cost_control``). Поэтому надбавки ниже вынесены в один блок и
помечены как черновые: менять их — правка одной строки, а не поход по
коду.

Списание идёт в два шага, и это принципиально:

1. **Резерв** при запуске — по заказанному числу лидов.
2. **Расчёт** при завершении — по фактически доставленным, остаток
   резерва возвращается.

Поиск почти всегда приносит меньше, чем заказано: часть компаний
отсеивается дедупликацией, часть не проходит фильтры. Списание вперёд
по заказу означало бы регулярно брать с команды за лидов, которых она
не получила.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.db.models import (
    KIND_ADJUST,
    KIND_GRANT,
    KIND_HOLD,
    KIND_REFUND,
    KIND_SPEND,
    KIND_TOPUP,
    Team,
    TokenLedger,
)

# ─── Тарификация ───────────────────────────────────────────────────
# ЧЕРНОВИК. Значения держатся здесь, пока не назначена цена токена.
# Менять только тут: всё остальное считает через quote().

#: Базовый лид: найден, обогащён, оценён.
TOKENS_PER_LEAD: int = 1
#: Надбавка за поиск контакта руководителя. Отдельные платные запросы
#: наружу, и по части компаний контакт не находится вовсе.
TOKENS_PER_DECISION_MAKER: int = 1


@dataclass(frozen=True, slots=True)
class Quote:
    leads: int
    per_lead: int
    total: int
    #: Из чего сложилось — чтобы интерфейс объяснил цифру, а не
    #: показывал итог без разбора.
    breakdown: dict[str, int]


def quote(leads: int, *, find_decision_makers: bool = False) -> Quote:
    """Сколько токенов стоит запуск на ``leads`` лидов."""
    leads = max(0, int(leads))
    per_lead = TOKENS_PER_LEAD
    breakdown = {"leads": leads * TOKENS_PER_LEAD}
    if find_decision_makers:
        per_lead += TOKENS_PER_DECISION_MAKER
        breakdown["decision_makers"] = leads * TOKENS_PER_DECISION_MAKER
    return Quote(
        leads=leads,
        per_lead=per_lead,
        total=leads * per_lead,
        breakdown=breakdown,
    )


async def balance(session: AsyncSession, team_id: uuid.UUID) -> int:
    team = await session.get(Team, team_id)
    return int(team.token_balance) if team is not None else 0


async def _move(
    session: AsyncSession,
    team_id: uuid.UUID,
    *,
    kind: str,
    amount: int,
    search_id: uuid.UUID | None = None,
    user_id: int | None = None,
    reason: str | None = None,
) -> int:
    """Записать движение и обновить кэш баланса в одной транзакции.

    Возвращает баланс после операции. Коммит остаётся за вызывающим —
    движение токенов почти всегда часть более крупного действия
    (запуск поиска, закрытие сессии) и должно жить с ним в одной
    транзакции, иначе баланс разойдётся с реальностью при сбое.
    """
    team = await session.get(Team, team_id)
    if team is None:
        raise ValueError(f"team {team_id} not found")
    new_balance = int(team.token_balance) + int(amount)
    team.token_balance = new_balance
    session.add(
        TokenLedger(
            team_id=team_id,
            kind=kind,
            amount=int(amount),
            balance_after=new_balance,
            search_id=search_id,
            user_id=user_id,
            reason=reason,
        )
    )
    return new_balance


async def grant(
    session: AsyncSession,
    team_id: uuid.UUID,
    amount: int,
    *,
    reason: str | None = None,
) -> int:
    """Начисление по подписке."""
    return await _move(
        session, team_id, kind=KIND_GRANT, amount=abs(amount), reason=reason
    )


async def topup(
    session: AsyncSession,
    team_id: uuid.UUID,
    amount: int,
    *,
    user_id: int | None = None,
    reason: str | None = None,
) -> int:
    """Докупка сверх тарифа. Доступна на любом тарифе — это заложено
    с самого начала, чтобы не переделывать биллинг позже."""
    return await _move(
        session,
        team_id,
        kind=KIND_TOPUP,
        amount=abs(amount),
        user_id=user_id,
        reason=reason,
    )


async def adjust(
    session: AsyncSession,
    team_id: uuid.UUID,
    amount: int,
    *,
    reason: str,
) -> int:
    """Ручная правка админом платформы. Причина обязательна."""
    return await _move(
        session, team_id, kind=KIND_ADJUST, amount=int(amount), reason=reason
    )


async def hold(
    session: AsyncSession,
    team_id: uuid.UUID,
    search_id: uuid.UUID,
    amount: int,
    *,
    user_id: int | None = None,
    reason: str | None = None,
) -> int:
    """Занять токены под запущенный поиск."""
    return await _move(
        session,
        team_id,
        kind=KIND_HOLD,
        amount=-abs(amount),
        search_id=search_id,
        user_id=user_id,
        reason=reason,
    )


async def settle(
    session: AsyncSession,
    team_id: uuid.UUID,
    search_id: uuid.UUID,
    *,
    actual_leads: int,
    find_decision_makers: bool = False,
    reason: str | None = None,
) -> int:
    """Закрыть резерв по факту доставленных лидов.

    Резерв ищется в журнале, факт считается тем же ``quote``, разница
    возвращается. Если фактических лидов больше заказанных (так не
    бывает, но пусть код это переживает), доберём недостающее —
    уходить в минус не даём.
    """
    held = (
        await session.execute(
            select(TokenLedger)
            .where(TokenLedger.search_id == search_id)
            .where(TokenLedger.kind == KIND_HOLD)
        )
    ).scalars().all()
    reserved = sum(-row.amount for row in held)
    if reserved == 0:
        return await balance(session, team_id)

    fact = quote(
        actual_leads, find_decision_makers=find_decision_makers
    ).total
    fact = min(fact, reserved)

    # Резерв «превращается» в расход: возвращаем всё занятое и списываем
    # факт. Две строки вместо одной, зато в журнале видно и то, и другое.
    await _move(
        session,
        team_id,
        kind=KIND_REFUND,
        amount=reserved,
        search_id=search_id,
        reason="возврат резерва",
    )
    return await _move(
        session,
        team_id,
        kind=KIND_SPEND,
        amount=-fact,
        search_id=search_id,
        reason=reason or f"поиск: {actual_leads} лидов",
    )


async def release(
    session: AsyncSession,
    team_id: uuid.UUID,
    search_id: uuid.UUID,
    *,
    reason: str = "поиск не состоялся",
) -> int:
    """Вернуть резерв целиком — поиск упал и ничего не принёс."""
    return await settle(
        session, team_id, search_id, actual_leads=0, reason=reason
    )
