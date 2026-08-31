"""Токены — валюта, в которой команда видит стоимость работы.

Внутри система считает настоящую себестоимость в долларах
(``usage_tracker`` / ``cost_control``): столько платформа отдаёт
Google и Anthropic. Пользователю эта цифра не нужна и вредна — она
меняется от тарифов поставщиков и ничего не говорит о ценности.
Поэтому наружу выведен один понятный счётчик: **один базовый лид —
один токен**.

Два слоя намеренно не сливаются в один. Доллары остаются для админки
платформы и для того, чтобы позже назначить цену токена, сравнив одно
с другим.

Почему журнал, а не просто число на команде. Число отвечает на вопрос
«сколько осталось» и ни на один другой. Через месяц спросят «куда
ушла тысяча токенов», «вернулись ли токены за упавший поиск»,
«сколько докупили в марте» — и без журнала это не восстановить.
Баланс здесь кэш: его значение всегда равно сумме строк, и обновляется
он в той же транзакции, что и строка.

Списание идёт в два шага. При запуске резервируется оценка, после
завершения списывается факт, разница возвращается. Поиск почти всегда
приносит меньше, чем заказали: если списывать вперёд по заказу, с
команды регулярно берут за лидов, которых она не получила.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import _UUID, Base, _utcnow

#: Начисление по подписке — приходит при продлении тарифа.
KIND_GRANT = "grant"
#: Докупка сверх тарифа. Доступна на любом тарифе.
KIND_TOPUP = "topup"
#: Резерв под запущенный поиск: токены заняты, но ещё не потрачены.
KIND_HOLD = "hold"
#: Факт по завершённому поиску.
KIND_SPEND = "spend"
#: Возврат неиспользованного резерва или компенсация за сбой.
KIND_REFUND = "refund"
#: Ручная правка админом платформы. Всегда с причиной.
KIND_ADJUST = "adjust"

LEDGER_KINDS: tuple[str, ...] = (
    KIND_GRANT,
    KIND_TOPUP,
    KIND_HOLD,
    KIND_SPEND,
    KIND_REFUND,
    KIND_ADJUST,
)


class TokenLedger(Base):
    """Одна строка — одно движение токенов у команды.

    ``amount`` со знаком: приход положительный, расход отрицательный.
    Сумма всех строк команды равна её ``token_balance`` — это
    инвариант, на который опирается сверка.
    """

    __tablename__ = "token_ledger"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        _UUID(),
        ForeignKey("teams.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Баланс команды сразу после этой строки — чтобы историю можно
    #: было читать без пересчёта всей ленты.
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Поиск, к которому относится движение (для hold/spend/refund).
    search_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID(),
        ForeignKey("search_queries.id", ondelete="SET NULL"),
        index=True,
    )
    #: Кто инициировал. NULL для системных начислений.
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    #: Человеческая формулировка: «поиск: пекарни, Орландо — 26 лидов».
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
