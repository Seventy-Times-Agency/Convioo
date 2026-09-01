"""Журнал действий команды — неизменяемая лента «кто что сделал».

Отличается от ``UserAuditLog``: тот про безопасность одного аккаунта
(входы, смены пароля), этот — про работу отдела. Раздал пакет лидов,
поменял воронку, поднял потолок затрат, выгрузил CSV — всё, за что
через месяц спросят «кто это сделал и когда».

Записи append-only: ни редактирования, ни удаления нет даже у
владельца — иначе журнал не аргумент в споре. Текст события не
хранится: хранится машинный ``kind`` + ``payload``, а фразу на языке
пользователя собирает интерфейс. Так журнал переживает смену
формулировок и локалей.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import _JSONB, _UUID, Base, _utcnow

#: Пакет лидов распределён на исполнителя.
JK_BATCH_ASSIGNED = "batch_assigned"
#: Воронка создана.
JK_FUNNEL_CREATED = "funnel_created"
#: Воронка изменена.
JK_FUNNEL_UPDATED = "funnel_updated"
#: Воронка удалена.
JK_FUNNEL_DELETED = "funnel_deleted"
#: Приглашение в команду отправлено.
JK_MEMBER_INVITED = "member_invited"
#: Роль участника изменена.
JK_ROLE_CHANGED = "role_changed"
#: Участник удалён (лиды переданы).
JK_MEMBER_REMOVED = "member_removed"
#: Владение командой передано.
JK_OWNERSHIP_TRANSFERRED = "ownership_transferred"
#: Потолок затрат изменён.
JK_COST_CAP_CHANGED = "cost_cap_changed"
#: Добыча завершена (системное событие).
JK_SEARCH_FINISHED = "search_finished"
#: Экспорт лидов.
JK_LEADS_EXPORTED = "leads_exported"

JOURNAL_KINDS: tuple[str, ...] = (
    JK_BATCH_ASSIGNED,
    JK_FUNNEL_CREATED,
    JK_FUNNEL_UPDATED,
    JK_FUNNEL_DELETED,
    JK_MEMBER_INVITED,
    JK_ROLE_CHANGED,
    JK_MEMBER_REMOVED,
    JK_OWNERSHIP_TRANSFERRED,
    JK_COST_CAP_CHANGED,
    JK_SEARCH_FINISHED,
    JK_LEADS_EXPORTED,
)


class TeamActionLog(Base):
    """Одна строка — одно действие в команде.

    ``actor_id`` может обнулиться при удалении аккаунта, поэтому имя
    и роль снимаются в момент записи — журнал должен читаться и через
    год, когда половины людей в команде уже нет.
    """

    __tablename__ = "team_action_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        _UUID(),
        ForeignKey("teams.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    #: NULL — системное событие (завершение добычи, крон).
    actor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    actor_name: Mapped[str | None] = mapped_column(String(120))
    actor_role: Mapped[str | None] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    #: Параметры события для сборки фразы: счётчики, имена, «было → стало».
    payload: Mapped[dict | None] = mapped_column(_JSONB())
    #: Где это случилось: «База · воронка Аудит-первый».
    object_label: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
