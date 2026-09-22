"""Ringostat: звонок из CRM (callback) и разбор webhook.

Callback ``/callback/outward_call``: Ringostat звонит сотруднику на
``extension`` (номер/SIP проекта), после ответа — клиенту на
``destination``. Webhook шлёт параметры, которые настраиваются в
кабинете Ringostat; мы ждём стандартные имена (см. Настройки →
Телефония).
"""

from __future__ import annotations

from typing import Any

import httpx

from leadgen.core.services.telephony import (
    CallEvent,
    TelephonyError,
    normalize_number,
)

API_URL = "https://api.ringostat.net/callback/outward_call"


def _first(data: dict[str, Any], *keys: str) -> Any:
    """Первое непустое значение из нескольких имён одного поля."""
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def _int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


class RingostatProvider:
    name = "ringostat"

    def __init__(self, auth_key: str) -> None:
        self._key = auth_key

    async def start_call(self, *, extension: str, destination: str) -> None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                API_URL,
                headers={"Auth-key": self._key},
                data={"extension": extension, "destination": destination},
            )
        if resp.status_code >= 400:
            raise TelephonyError(
                f"ringostat {resp.status_code}: {resp.text[:200]}"
            )

    def parse_event(self, data: dict[str, Any]) -> CallEvent | None:
        # Имён у одного и того же поля два: классические вебхуки шлют
        # ``callee``/``status``/``call_id``, Webhooks 2.0 — ``dst``/
        # ``disposition``/``cdr_id``. Разбираем оба, чтобы смена версии
        # в кабинете не ломала приём.
        #
        # Исходящий звонок: клиент — вызываемая сторона. Без неё событие
        # не про нас (служебное), его пропускаем.
        callee = normalize_number(
            _first(data, "callee", "destination", "dst")
        )
        if not callee:
            return None
        status = str(_first(data, "status", "disposition") or "").upper()
        talk = _int(_first(data, "dialog", "billsec"))
        recording = _first(
            data, "recording_wav", "record_link", "recording"
        )
        call_id = _first(data, "call_id", "cdr_id", "uniqueid")
        answered = status == "ANSWERED" or bool(talk)
        return CallEvent(
            provider_call_id=str(call_id) if call_id else None,
            to_number=callee,
            answered=answered,
            duration_sec=_int(_first(data, "call_duration", "duration")),
            talk_sec=talk,
            recording_url=str(recording) if recording and answered else None,
        )
