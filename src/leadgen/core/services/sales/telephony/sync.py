"""Итоги звонков забираем у провайдера сами, не дожидаясь webhook.

Webhook Ringostat «После звонка» срабатывает только на входящие; для
исходящих у него отдельное событие, которое нужно настраивать в
кабинете. Вместо зависимости от чужих настроек раз в минуту читаем
журнал звонков через API и дописываем итог:

* нашим звонкам из карточки, которые ещё висят в «наборе» (или уже
  закрыты по таймауту как «нет результата от провайдера»);
* звонкам, сделанным мимо платформы — прямо из Smart Phone, — если
  номер принадлежит известному лиду.

Тот же путь страхует от событий, потерянных во время деплоя.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from leadgen.core.services.sales.telephony import (
    CallEvent,
    get_provider,
    normalize_number,
    rep_channel_for,
)
from leadgen.db.models import Call, Lead, SearchQuery, TeamMembership
from leadgen.db.session import session_factory

logger = logging.getLogger(__name__)

#: Сколько назад смотрим: звонок из карточки живёт минуты, запись у
#: провайдера появляется в пределах пары минут после разговора.
LOOKBACK = timedelta(hours=3)
NO_RESULT_ERROR = "no result from the phone provider"
#: Разговор был, а записи ещё нет — ждём её не дольше этого.
RECORDING_GRACE = timedelta(minutes=5)
#: Строка «без разговора» может быть звонком, который ещё идёт: журнал
#: показывает его с нулями до конца. Недозвоном считаем не раньше.
UNANSWERED_GRACE = timedelta(minutes=10)


async def find_dialing(session: Any, to_number: str, since: datetime) -> Call | None:
    return (
        await session.execute(
            select(Call)
            .where(Call.to_number == to_number)
            .where(Call.state == "dialing")
            .where(Call.created_at >= since)
            .order_by(Call.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def lead_for_direct_call(
    session: Any, number: str
) -> tuple[Lead | None, uuid.UUID | None]:
    """Лид для звонка, сделанного мимо кнопки «Позвонить».

    Ищем только в командах, где телефония настроена — у кого-то из
    участников задан номер для звонков. Демо-команда и чужие команды
    в той же базе сюда не попадают. Если номер нашёлся у лидов
    нескольких таких команд, звонок не привязываем: угадать, чей он,
    нельзя, а приклеить разговор к чужой карточке хуже, чем потерять.
    """
    team_ids = select(TeamMembership.team_id).where(
        TeamMembership.phone_extension.is_not(None)
    )
    rows = (
        await session.execute(
            select(Lead, SearchQuery.team_id)
            .join(SearchQuery, SearchQuery.id == Lead.query_id)
            .where(SearchQuery.team_id.in_(team_ids))
            .where(Lead.phone.is_not(None))
            .where(Lead.deleted_at.is_(None))
            .order_by(Lead.created_at.desc())
        )
    ).all()
    matches = [
        (lead, team_id)
        for lead, team_id in rows
        if normalize_number(lead.phone) == number
    ]
    if not matches or len({team_id for _lead, team_id in matches}) > 1:
        return None, None
    return matches[0]


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _row_time(row: dict[str, Any]) -> datetime | None:
    raw = str(row.get("calldate") or "")
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _apply(call: Call, event: CallEvent) -> bool:
    """Дописать итог в строку звонка; True — есть запись на разбор."""
    call.provider_call_id = event.provider_call_id or call.provider_call_id
    channel = rep_channel_for(event, call.to_number)
    if channel is not None:
        call.rep_channel = channel
    call.duration_sec = event.duration_sec
    call.talk_sec = event.talk_sec
    # Клиент отказался от записи — ссылку не сохраняем вовсе.
    call.recording_url = event.recording_url if call.record_consent else None
    call.state = "completed" if event.answered else "missed"
    call.error = None
    call.completed_at = datetime.now(timezone.utc)
    return bool(call.recording_url)


async def sync_ringostat_calls(now: datetime | None = None) -> int:
    """Один проход: журнал провайдера → итоги наших звонков. Возвращает
    число звонков, которым дописан итог или которые заведены заново."""
    provider = get_provider("ringostat")
    list_calls = getattr(provider, "list_calls", None)
    if provider is None or list_calls is None:
        return 0
    now = now or datetime.now(timezone.utc)
    since = now - LOOKBACK

    async with session_factory() as session:
        pending = list(
            (
                await session.execute(
                    select(Call)
                    .where(Call.provider == "ringostat")
                    .where(Call.created_at >= since)
                    .where(
                        (Call.state == "dialing")
                        | (
                            (Call.state == "missed")
                            & (Call.error == NO_RESULT_ERROR)
                        )
                    )
                    .order_by(Call.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        try:
            rows = await list_calls(since - timedelta(minutes=10))
        except Exception:  # noqa: BLE001 — провайдер недоступен: попробуем через минуту
            logger.warning("ringostat sync: calls/list failed", exc_info=True)
            return 0

        parsed: list[tuple[datetime, dict[str, Any], CallEvent]] = []
        for row in rows:
            when = _row_time(row)
            event = provider.parse_event(row)
            if when is None or event is None or not event.provider_call_id:
                continue
            if _aware(when) < since - timedelta(minutes=10):
                continue
            parsed.append((_aware(when), row, event))
        parsed.sort(key=lambda item: item[0])
        if not parsed:
            return 0

        ids = [event.provider_call_id for _w, _r, event in parsed]
        bound = {
            c.provider_call_id: c
            for c in (
                await session.execute(
                    select(Call).where(Call.provider_call_id.in_(ids))
                )
            )
            .scalars()
            .all()
        }
        used = set(bound)

        def ready(when: datetime, row: dict[str, Any], event: CallEvent) -> bool:
            """Можно ли уже фиксировать итог по этой строке журнала."""
            if not event.answered:
                # Пока разговор идёт, строка выглядит как недозвон.
                return now - when > UNANSWERED_GRACE
            if event.recording_url:
                return True
            ended = when + timedelta(seconds=event.duration_sec or 0)
            return now - ended > RECORDING_GRACE

        touched = 0
        to_process: list[uuid.UUID] = []

        # 0. Звонок уже привязан, но итог был снят слишком рано (шёл
        #    разговор) или запись появилась позже — дополняем.
        for when, _row, event in parsed:
            call = bound.get(event.provider_call_id or "")
            if call is None:
                continue
            # Звонок, заведённый по журналу, раньше получал время
            # загрузки, а не разговора — и вставал в истории не на своё
            # место. Наш звонок из карточки создаётся ДО набора, поэтому
            # «создан заметно позже начала» бывает только у таких.
            if _aware(call.created_at) > when + timedelta(minutes=1):
                call.created_at = when
            channel = rep_channel_for(event, call.to_number)
            if channel is not None and call.rep_channel != channel:
                call.rep_channel = channel
            if not event.answered:
                continue
            got_talk = call.state == "missed"
            got_recording = (
                bool(event.recording_url)
                and not call.recording_url
                and call.record_consent
                and call.state in {"missed", "completed"}
            )
            if not (got_talk or got_recording):
                continue
            if _apply(call, event):
                to_process.append(call.id)
            touched += 1

        # 1. Наши звонки из карточки.
        for call in pending:
            created = _aware(call.created_at)
            for when, row, event in parsed:
                if event.provider_call_id in used:
                    continue
                if call.to_number not in event.candidates:
                    continue
                if not (
                    created - timedelta(minutes=2)
                    <= when
                    <= created + timedelta(minutes=15)
                ):
                    continue
                if not ready(when, row, event):
                    break
                used.add(event.provider_call_id)
                if _apply(call, event):
                    to_process.append(call.id)
                touched += 1
                break

        # 2. Звонки мимо платформы (из Smart Phone напрямую).
        for when, row, event in parsed:
            if event.provider_call_id in used or not event.answered:
                continue
            if not ready(when, row, event):
                continue
            match = team_id = number = None
            for candidate in event.candidates:
                match, team_id = await lead_for_direct_call(session, candidate)
                if match is not None:
                    number = candidate
                    break
            if match is None:
                continue
            call = Call(
                team_id=team_id,
                lead_id=match.id,
                user_id=match.owner_user_id,
                provider="ringostat",
                to_number=number,
                direction=event.direction or "out",
                # Время разговора, а не загрузки: история в карточке
                # идёт по порядку звонков.
                created_at=when,
            )
            session.add(call)
            await session.flush()
            used.add(event.provider_call_id)
            if _apply(call, event):
                to_process.append(call.id)
            touched += 1

        await session.commit()

    if to_process:
        from leadgen.core.services.sales.telephony.processing import schedule

        for call_id in to_process:
            await schedule(call_id)
    if touched:
        logger.info(
            "ringostat sync: %d call(s) updated, %d sent to analysis",
            touched,
            len(to_process),
        )
    return touched
