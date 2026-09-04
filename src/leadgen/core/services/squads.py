"""Команды внутри компании: правила видимости.

Одна функция отвечает на главный вопрос — «чьих лидов этому
пользователю можно показывать». Тимлид с командой видит своих людей
и свободный пул; РОП, владелец и тимлид без команды видят всё —
компания без деления работает ровно как раньше.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.core.services.team_permissions import (
    ROLE_MANAGER,
    normalize_role,
)
from leadgen.db.models import TeamMembership


async def visible_member_ids(
    session: AsyncSession, team_id: uuid.UUID, user_id: int
) -> list[int] | None:
    """Ids людей, чьих лидов пользователю можно показывать.

    ``None`` — без ограничения (вся компания). Список — только эти
    участники (+ свободный пул, это решает вызывающий код).
    """
    ms = (
        await session.execute(
            select(TeamMembership)
            .where(TeamMembership.team_id == team_id)
            .where(TeamMembership.user_id == user_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if ms is None:
        return None
    if normalize_role(ms.role) != ROLE_MANAGER:
        return None
    if ms.squad_id is None:
        return None
    rows = (
        await session.execute(
            select(TeamMembership.user_id)
            .where(TeamMembership.team_id == team_id)
            .where(TeamMembership.squad_id == ms.squad_id)
        )
    ).scalars()
    return list(rows)
