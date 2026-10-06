"""Месячный бюджет команды в долларах — он же лимит токенов.

Владелец вводит сумму в $. Сумма переводится в токены по себестоимости
лида (1 лид = 1 токен), и 1-го числа баланс пополняется до этого
количества. Это связывает два счётчика, которые раньше жили отдельно:
долларовый потолок затрат и токены, уходившие в минус.

Пополнение ленивое: срабатывает при первом обращении в новом месяце
(экран «Деньги и токены» или запуск поиска), поэтому отдельный крон
не нужен. ``Team.tokens_refill_month`` не даёт пополнить дважды.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.core.services.account import tokens as _tokens
from leadgen.core.services.search.cost_control import COST_PER_ENRICHED_LEAD_USD
from leadgen.db.models import Team


def token_price_usd() -> float:
    """Сколько стоит один токен — себестоимость одного базового лида."""
    return float(COST_PER_ENRICHED_LEAD_USD)


def allowance(budget_usd: float | Decimal | None) -> int:
    """Сколько токенов даёт бюджет. ``None`` — бюджета нет."""
    if not budget_usd:
        return 0
    return int(math.floor(float(budget_usd) / token_price_usd()))


def month_key(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


async def ensure_refill(session: AsyncSession, team: Team, *, now: datetime | None = None) -> bool:
    """Пополнить баланс до бюджета, если в этом месяце ещё не пополняли.

    Остаток сверх бюджета не срезаем — он мог прийти ручным начислением.
    Возвращает ``True``, если что-то изменилось (нужен коммит).
    """
    if not team.monthly_cost_cap_usd:
        return False
    key = month_key(now)
    if team.tokens_refill_month == key:
        return False
    target = allowance(team.monthly_cost_cap_usd)
    current = int(team.token_balance)
    if target > current:
        await _tokens.grant(
            session,
            team.id,
            target - current,
            reason=f"бюджет {key}: пополнение до {target}",
        )
    team.tokens_refill_month = key
    return True


async def change_budget(
    session: AsyncSession,
    team: Team,
    new_budget_usd: float | None,
    *,
    user_id: int | None = None,
) -> None:
    """Сменить бюджет посреди месяца.

    Если в этом месяце уже пополняли — добавляем/убираем разницу между
    новым и старым количеством токенов, чтобы бюджет сразу стал лимитом.
    Если не пополняли — обычное пополнение до нового бюджета.
    """
    old_allow = allowance(team.monthly_cost_cap_usd)
    refilled = team.tokens_refill_month == month_key()
    team.monthly_cost_cap_usd = (
        Decimal(str(new_budget_usd)) if new_budget_usd is not None else None
    )
    if new_budget_usd is None:
        team.tokens_refill_month = None
        return
    if not refilled:
        await ensure_refill(session, team)
        return
    delta = allowance(new_budget_usd) - old_allow
    if delta > 0:
        await _tokens.topup(
            session, team.id, delta, user_id=user_id, reason=f"бюджет увеличен: +{delta}"
        )
    elif delta < 0:
        await _tokens.adjust(session, team.id, delta, reason=f"бюджет уменьшен: {delta}")
