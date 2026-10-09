"""Счётчики затрат — сколько внешних вызовов сжёг каждый пользователь.

Раньше эти цифры жили в кэше с TTL: при редеплое обнулялись, между
API и воркером без Redis не сходились, а инкремент был
«прочитал-прибавил-записал» и терял обновления под параллельным
обогащением. На этих цифрах стоит потолок затрат — значит, им место
в базе.

Строка — (пользователь, сервис, день). Инкремент — атомарный UPSERT
``units = units + N`` на стороне БД: параллельные записи складываются,
а не затирают друг друга.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import _UUID, Base, _utcnow


class UsageCounter(Base):
    """Дневной счётчик по одному сервису у одного пользователя.

    ``user_id`` — строка, а не FK: трекер исторически оперирует
    строковыми id (contextvar), и счётчик должен переживать удаление
    аккаунта — расход платформы уже случился.
    """

    __tablename__ = "usage_counters"

    user_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    service: Mapped[str] = mapped_column(String(40), primary_key=True)
    #: YYYYMMDD в UTC — совпадает с прежними ключами кэша.
    day: Mapped[str] = mapped_column(String(8), primary_key=True)
    units: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class CostEvent(Base):
    """Одна трата платформы: сервис, сколько единиц, сколько $.

    Журнал, а не счётчик: у каждой траты есть команда, поиск и этап —
    так видно и полную стоимость запуска, и сколько ушло на то, что в
    выдачу не попало (дубли, отсеянные, неудачные прогоны). Строки
    пишутся и без пользователя: расход платформы случился в любом
    случае.
    """

    __tablename__ = "cost_events"
    __table_args__ = (
        Index("ix_cost_events_team_created", "team_id", "created_at"),
        Index("ix_cost_events_search", "search_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(32))
    team_id: Mapped[uuid.UUID | None] = mapped_column(_UUID())
    search_id: Mapped[uuid.UUID | None] = mapped_column(_UUID())
    service: Mapped[str] = mapped_column(String(48), nullable=False)
    #: discovery · enrichment · scoring · decision_maker · insights ·
    #: assistant · email · calls · other
    stage: Mapped[str | None] = mapped_column(String(24))
    units: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0)


class CostPrice(Base):
    """Цена единицы сервиса, заданная в админке.

    Перекрывает и цены по умолчанию из кода, и COST_OVERRIDES_JSON:
    новый тариф или новый сервис вписывается без программиста.
    """

    __tablename__ = "cost_prices"

    service: Mapped[str] = mapped_column(String(48), primary_key=True)
    price_usd: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)
    updated_by: Mapped[int | None] = mapped_column(BigInteger)
