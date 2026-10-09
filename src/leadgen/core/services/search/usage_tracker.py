"""Per-user, per-service API usage tracker.

Convioo's variable cost is dominated by Google Places (Text Search +
Place Details) and Anthropic Claude. This module gives the rest of
the codebase a single, no-fuss API for *recording* a billable call
and *aggregating* what a given user has spent during a window — so
the admin dashboard can spot a runaway tenant before the monthly
Google invoice does.

Design choices:

* **Durable counters in the database.** Storage is the
  ``usage_counters`` table, one row per ``(user_id, service, day)``,
  incremented with an atomic ``INSERT .. ON CONFLICT`` on the DB
  side. The earlier cache-based storage lost increments under
  concurrent enrichment, reset on redeploy, and diverged between
  the API and the worker without Redis — the cost ceiling stands
  on these numbers, so they live where the data does.
* **Context-scoped user id.** Collectors don't take a user-id
  parameter today and we don't want to thread it through every
  call site. ``set_active_user(...)`` writes into a
  :class:`contextvars.ContextVar` that the recorder reads — async
  tasks inherit the value automatically.
* **Cost is computed once, here.** Pricing is centralised in
  ``UNIT_COST_USD`` so a Google SKU change is a one-line edit, not
  a hunt across collectors.

Usage is fire-and-forget: any error is logged and swallowed —
billing telemetry must not break the user-facing search.
"""

from __future__ import annotations

import contextvars
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# Цены за единицу. Google — прайс Places API (New) с марта 2025:
# Text Search с телефоном/сайтом/рейтингом и отзывами — Enterprise +
# Atmosphere $40/1000 страниц (до 20 компаний), Place Details с
# отзывами — $25/1000 (теперь только для старых записей без отзывов).
# Claude Haiku 4.5 — $1/$5 за MTok. Платные кредиты обогащения — по
# типовым тарифам; свой тариф владелец задаёт в COST_OVERRIDES_JSON,
# туда же — цена любого нового сервиса (без правки кода).
UNIT_COST_USD: dict[str, float] = {
    "google_text_search": 0.040,
    "google_place_details": 0.025,
    "claude_input_tokens": 1.0 / 1_000_000,
    "claude_output_tokens": 5.0 / 1_000_000,
    "claude_cache_read_tokens": 0.10 / 1_000_000,
    "claude_cache_write_tokens": 1.25 / 1_000_000,
    "hunter_credit": 0.07,
    "apollo_credit": 0.03,
    "opencorporates_call": 0.0,
    "companies_house_call": 0.0,
    "yelp_call": 0.0,
    "foursquare_call": 0.015,
    "elevenlabs_stt_seconds": 0.40 / 3600,
    "resend_email": 0.0004,
}

_overrides_cache: tuple[str, dict[str, float]] | None = None

#: Цены из админки (таблица cost_prices). Перечитываются не чаще раза в
#: минуту — у API и воркера свой кэш, правка доезжает до обоих.
_db_prices: dict[str, float] = {}
_db_prices_at: float = 0.0
DB_PRICES_TTL_SECONDS = 60.0


def env_overrides() -> dict[str, float]:
    """Цены из COST_OVERRIDES_JSON (кривой JSON → пусто)."""
    price_of("")
    return dict(_overrides_cache[1]) if _overrides_cache else {}


def db_prices() -> dict[str, float]:
    return dict(_db_prices)


def invalidate_prices() -> None:
    """Сбросить кэш цен из админки — следующая трата перечитает их."""
    global _db_prices_at
    _db_prices_at = 0.0


async def refresh_db_prices(session: Any, *, force: bool = False) -> None:
    global _db_prices, _db_prices_at
    import time

    if not force and time.monotonic() - _db_prices_at < DB_PRICES_TTL_SECONDS and _db_prices_at:
        return
    try:
        from sqlalchemy import select

        from leadgen.db.models import CostPrice

        rows = (await session.execute(select(CostPrice.service, CostPrice.price_usd))).all()
        _db_prices = {s: float(p) for s, p in rows}
    except Exception as exc:  # noqa: BLE001 — нет таблицы/базы → цены из кода
        logger.debug("cost_prices refresh skipped err=%s", exc)
    _db_prices_at = time.monotonic()


def price_of(service: str) -> float:
    """Цена единицы сервиса: админка → COST_OVERRIDES_JSON → код."""
    global _overrides_cache
    if service in _db_prices:
        return _db_prices[service]
    raw = ""
    try:
        from leadgen.config import get_settings

        raw = get_settings().cost_overrides_json or ""
    except Exception:  # noqa: BLE001
        raw = ""
    if _overrides_cache is None or _overrides_cache[0] != raw:
        parsed: dict[str, float] = {}
        if raw.strip():
            try:
                import json

                parsed = {k: float(v) for k, v in json.loads(raw).items()}
            except Exception:  # noqa: BLE001 — кривой JSON не роняет учёт
                logger.warning("COST_OVERRIDES_JSON is not valid JSON")
        _overrides_cache = (raw, parsed)
    return _overrides_cache[1].get(service, UNIT_COST_USD.get(service, 0.0))

# Строки старше этого срока подчищает ночной крон воркера — 30-дневному
# окну хватает с запасом.
USAGE_RETENTION_DAYS = 60

# 30-day lookback for "monthly" aggregates. Calendar-month math is
# noisy across DST and short months — a rolling window is closer to
# what an operator actually wants when triaging "who blew up our
# bill today".
_MONTH_WINDOW_DAYS = 30

# ContextVar so collectors don't have to grow user_id parameters.
_ACTIVE_USER: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "convioo_active_user", default=None
)
# Команда, поиск и этап — для журнала трат (cost_events).
_ACTIVE_TEAM: contextvars.ContextVar[Any] = contextvars.ContextVar("convioo_active_team", default=None)
_ACTIVE_SEARCH: contextvars.ContextVar[Any] = contextvars.ContextVar("convioo_active_search", default=None)
_ACTIVE_STAGE: contextvars.ContextVar[str | None] = contextvars.ContextVar("convioo_active_stage", default=None)


def bind_search(search_id: Any, team_id: Any) -> tuple[contextvars.Token, contextvars.Token]:
    """Все траты дальше в этом контексте — этого поиска и команды."""
    return _ACTIVE_SEARCH.set(search_id), _ACTIVE_TEAM.set(team_id)


def unbind_search(tokens: tuple[contextvars.Token, contextvars.Token]) -> None:
    _ACTIVE_SEARCH.reset(tokens[0])
    _ACTIVE_TEAM.reset(tokens[1])


def bind_team(team_id: Any) -> contextvars.Token:
    return _ACTIVE_TEAM.set(team_id)


def unbind_team(token: contextvars.Token) -> None:
    _ACTIVE_TEAM.reset(token)


def set_stage(stage: str | None) -> contextvars.Token:
    """Этап поиска для следующих трат (discovery, enrichment, …)."""
    return _ACTIVE_STAGE.set(stage)


def reset_stage(token: contextvars.Token) -> None:
    _ACTIVE_STAGE.reset(token)


@dataclass(slots=True)
class UsageSummary:
    """Aggregated usage for a (user, window) pair."""

    user_id: str
    window: str
    units_by_service: dict[str, int]
    cost_usd_by_service: dict[str, float]
    total_cost_usd: float


def set_active_user(user_id: str | int | None) -> contextvars.Token[str | None]:
    """Bind the current async context to ``user_id``.

    Returns a token the caller can pass to :func:`reset_active_user`
    to restore the previous value (typical pattern: ``try/finally``
    around a search run).
    """
    value = str(user_id) if user_id is not None else None
    return _ACTIVE_USER.set(value)


def reset_active_user(token: contextvars.Token[str | None]) -> None:
    _ACTIVE_USER.reset(token)


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _day_keys(days: int) -> list[str]:
    """YYYYMMDD-ключи скользящего окна в ``days`` дней, включая сегодня."""
    today = datetime.now(timezone.utc)
    return [
        today.fromordinal(today.toordinal() - i).strftime("%Y%m%d")
        for i in range(days)
    ]


def _insert_for(session: Any):
    """Диалектный INSERT ... ON CONFLICT — атомарный инкремент на
    стороне БД. Postgres в проде, SQLite в тестах и zero-config
    запуске; оба поддерживают ``on_conflict_do_update``."""
    dialect = session.bind.dialect.name if session.bind is not None else ""
    if dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert

        return insert
    from sqlalchemy.dialects.postgresql import insert

    return insert


async def record(service: str, units: float = 1, *, stage: str | None = None) -> None:
    """Record ``units`` of ``service``.

    Two writes: the per-user daily counter (only when a user is bound)
    and a cost_events row with team, search and stage — always, even
    without a user, because the platform paid regardless. Errors are
    logged and swallowed — billing telemetry never breaks a search.
    """
    if units <= 0:
        return
    user_id = _ACTIVE_USER.get()
    try:
        from leadgen.db.models import CostEvent
        from leadgen.db.session import session_factory

        async with session_factory() as session:
            await refresh_db_prices(session)
            session.add(
                CostEvent(
                    user_id=user_id,
                    team_id=_ACTIVE_TEAM.get(),
                    search_id=_ACTIVE_SEARCH.get(),
                    service=service,
                    stage=stage or _ACTIVE_STAGE.get(),
                    units=float(units),
                    cost_usd=round(float(units) * price_of(service), 8),
                )
            )
            await session.commit()
    except Exception as exc:  # noqa: BLE001 — telemetry must never raise
        logger.debug("usage_tracker cost event swallowed err=%s", exc)
    if not user_id:
        return
    units = int(round(units)) or 1
    try:
        from leadgen.db.models import UsageCounter
        from leadgen.db.session import session_factory

        async with session_factory() as session:
            insert = _insert_for(session)
            stmt = insert(UsageCounter).values(
                user_id=user_id,
                service=service,
                day=_today_key(),
                units=units,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["user_id", "service", "day"],
                set_={"units": UsageCounter.units + stmt.excluded.units},
            )
            await session.execute(stmt)
            await session.commit()
    except Exception as exc:  # noqa: BLE001 — telemetry must never raise
        logger.debug("usage_tracker.record swallowed err=%s", exc)


async def record_claude_usage(usage_obj: Any) -> None:
    """Pull token counts off an Anthropic ``Usage`` object and record them.

    The SDK exposes ``input_tokens``, ``output_tokens``, and the two
    cache fields ``cache_creation_input_tokens`` /
    ``cache_read_input_tokens`` once prompt caching is in play. Each
    is recorded under its own service slug so cost aggregation can
    apply the right per-token price.
    """
    if usage_obj is None:
        return
    pairs = (
        ("claude_input_tokens", "input_tokens"),
        ("claude_output_tokens", "output_tokens"),
        ("claude_cache_write_tokens", "cache_creation_input_tokens"),
        ("claude_cache_read_tokens", "cache_read_input_tokens"),
    )
    for service, attr in pairs:
        value = getattr(usage_obj, attr, 0) or 0
        if value:
            await record(service, int(value))


async def tracked_create(client: Any, **kwargs: Any) -> Any:
    """``client.messages.create`` + запись токенов в учёт. Через неё
    идёт каждый вызов Claude, чтобы ни один не выпал из расходов."""
    msg = await client.messages.create(**kwargs)
    await record_claude_usage(getattr(msg, "usage", None))
    return msg


async def get_user_usage(
    user_id: str | int, *, window: str = "today"
) -> UsageSummary:
    """Aggregate one user's usage for ``today`` or ``month`` (rolling 30d)."""
    uid = str(user_id)
    days = 1 if window == "today" else _MONTH_WINDOW_DAYS
    units: dict[str, int] = {}
    try:
        from sqlalchemy import func, select

        from leadgen.db.models import UsageCounter
        from leadgen.db.session import session_factory

        async with session_factory() as session:
            rows = await session.execute(
                select(
                    UsageCounter.service, func.sum(UsageCounter.units)
                )
                .where(UsageCounter.user_id == uid)
                .where(UsageCounter.day.in_(_day_keys(days)))
                .group_by(UsageCounter.service)
            )
            for service, total in rows.all():
                if total:
                    units[service] = int(total)
    except Exception as exc:  # noqa: BLE001 — та же семантика, что у
        # record: телеметрия не роняет запрос, при сбое БД счётчики
        # просто пустые (и сам запрос всё равно упадёт раньше на данных).
        logger.warning("usage_tracker.get swallowed err=%s", exc)
    cost = {
        service: round(count * price_of(service), 6)
        for service, count in units.items()
    }
    return UsageSummary(
        user_id=uid,
        window=window,
        units_by_service=units,
        cost_usd_by_service=cost,
        total_cost_usd=round(sum(cost.values()), 4),
    )


async def prune(retention_days: int = USAGE_RETENTION_DAYS) -> int:
    """Удалить счётчики старше окна. Зовёт ночной крон воркера."""
    from sqlalchemy import delete

    from leadgen.db.models import UsageCounter
    from leadgen.db.session import session_factory

    cutoff = datetime.now(timezone.utc)
    cutoff_key = cutoff.fromordinal(
        cutoff.toordinal() - retention_days
    ).strftime("%Y%m%d")
    async with session_factory() as session:
        result = await session.execute(
            delete(UsageCounter).where(UsageCounter.day < cutoff_key)
        )
        await session.commit()
    return int(result.rowcount or 0)
