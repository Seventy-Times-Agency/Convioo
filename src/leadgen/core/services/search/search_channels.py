"""Каналы поиска — то, что видит пользователь вместо имён вендоров.

Продавцу не нужно знать, что за компанией стоит Google Places, а за
отзывами — Yelp: он выбирает, ГДЕ искать, а не ЧЕМ. Имена поставщиков
остаются деталью реализации; когда источник упирается в лимит или у
него не задан ключ, это вопрос эксплуатации платформы, а не задача
человека, который набирает базу.

Соответствие «канал → источники» живёт здесь одним словарём, чтобы
добавление нового коллектора было правкой в одном месте, а не охотой
по маршрутам и формам.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class Channel:
    key: str
    title: str
    what: str
    limit: str
    #: Ключи коллекторов, которые понимает pipeline/search.py.
    sources: tuple[str, ...]
    #: Без этого канала искать нечего — снять его нельзя.
    required: bool = False


CHANNELS: Final[tuple[Channel, ...]] = (
    Channel(
        key="directories",
        title="Карты и справочники",
        what="Основа охвата: название, адрес, телефон, рейтинг, часы работы.",
        limit="Без этого канала искать нечего — он даёт сам список компаний.",
        sources=("google", "osm"),
        required=True,
    ),
    Channel(
        key="reputation",
        title="Отзывы и репутация",
        what=(
            "Сколько отзывов и какая оценка — по этому видно, живой бизнес "
            "или вывеска."
        ),
        limit="Покрытие неровное: зависит от ниши и страны.",
        sources=("yelp", "foursquare"),
    ),
    Channel(
        key="growth",
        title="Компании в движении",
        what=(
            "Кто прямо сейчас нанимает и кто недавно зарегистрировался — "
            "признак роста и свободного бюджета."
        ),
        limit="Работает там, где такие данные публикуются.",
        sources=("adzuna", "companies_house"),
    ),
)

_BY_KEY: Final[dict[str, Channel]] = {c.key: c for c in CHANNELS}

#: Канал, который нельзя выключить.
REQUIRED_KEYS: Final[tuple[str, ...]] = tuple(
    c.key for c in CHANNELS if c.required
)


def channel_keys() -> tuple[str, ...]:
    return tuple(c.key for c in CHANNELS)


def sources_for(keys: list[str] | None) -> list[str] | None:
    """Развернуть выбранные каналы в набор источников для конвейера.

    ``None`` и пустой список означают «все каналы» — то же самое, что
    простой поиск без настроек. Обязательный канал добавляется всегда,
    даже если его сняли: без списка компаний остальные каналы нечего
    обогащать.
    """
    if not keys:
        return None
    wanted = {k.strip().lower() for k in keys if k}
    wanted.update(REQUIRED_KEYS)
    out: list[str] = []
    for key in wanted:
        channel = _BY_KEY.get(key)
        if channel is None:
            continue
        for src in channel.sources:
            if src not in out:
                out.append(src)
    return out or None
