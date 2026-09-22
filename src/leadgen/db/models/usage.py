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

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


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
