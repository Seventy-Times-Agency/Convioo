"""Звонок через телефонию — одна строка на разговор.

Живёт отдельно от ``LeadActivity(kind="call")``: исход (кнопка селза)
и факт звонка у провайдера — разные события, которые приходят в
разное время. Строка создаётся при нажатии «Позвонить», webhook
провайдера дописывает длительность и запись, фоновая обработка —
расшифровку и разбор.

Статусы (``state``): dialing → completed → transcribed → analyzed;
``failed`` на любом шаге, ``missed`` — клиент не взял трубку.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import _JSONB, _UUID, Base, _utcnow


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID(),
        ForeignKey("teams.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID(),
        ForeignKey("leads.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_call_id: Mapped[str | None] = mapped_column(
        String(128), index=True
    )
    direction: Mapped[str] = mapped_column(
        String(8), default="out", nullable=False
    )
    #: Номер клиента в E.164 без «+» — ключ сопоставления webhook.
    to_number: Mapped[str | None] = mapped_column(String(32), index=True)
    state: Mapped[str] = mapped_column(
        String(16), default="dialing", nullable=False
    )
    #: Всего от набора до конца / из них разговор.
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    talk_sec: Mapped[int | None] = mapped_column(Integer)
    recording_url: Mapped[str | None] = mapped_column(Text)
    #: [{"speaker": "rep"|"client"|"s0", "start": 1.2, "text": "..."}]
    transcript: Mapped[list[dict[str, Any]] | None] = mapped_column(_JSONB())
    #: Разбор Claude: summary, next_step, suggested_outcome, objections…
    analysis: Mapped[dict[str, Any] | None] = mapped_column(_JSONB())
    #: Клиент отказался от записи — кнопка «Отменить запись» в звонке.
    #: Запись не скачиваем, не расшифровываем и не храним у себя.
    record_consent: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
