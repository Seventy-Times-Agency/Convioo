"""Запись в журнал действий команды.

Одна функция, чтобы у каждой точки вызова не было соблазна собирать
строку по-своему. Запись идёт в ту же сессию, что и само действие:
действие и его след либо фиксируются вместе, либо не фиксируются
вовсе. Исключение — системные события из пайплайна, там своя сессия.

Сбой журнала не должен ронять действие: заворачиваем в try/except и
пишем warning. Потерянная строка журнала — плохо; сорванная раздача
лидов из-за журнала — хуже.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from leadgen.core.services.team_permissions import normalize_role
from leadgen.db.models import TeamActionLog, User

logger = logging.getLogger(__name__)


def _actor_name(user: User) -> str:
    return (user.display_name or user.email or f"id {user.id}")[:120]


async def record(
    session: Any,
    team_id: uuid.UUID,
    kind: str,
    *,
    actor: User | None = None,
    actor_role: str | None = None,
    payload: dict[str, Any] | None = None,
    object_label: str | None = None,
) -> None:
    """Добавить строку журнала. ``actor=None`` — системное событие."""
    try:
        session.add(
            TeamActionLog(
                team_id=team_id,
                actor_id=actor.id if actor is not None else None,
                actor_name=_actor_name(actor) if actor is not None else None,
                actor_role=(
                    normalize_role(actor_role) if actor_role else None
                ),
                kind=kind,
                payload=payload or None,
                object_label=(object_label or None)
                and object_label[:160],
            )
        )
    except Exception:  # noqa: BLE001 — журнал не роняет действие
        logger.warning("team_journal.record failed kind=%s", kind, exc_info=True)
