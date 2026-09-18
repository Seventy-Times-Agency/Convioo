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
        # Исходящий звонок: клиент — callee. Без callee событие не про
        # нас (служебное), его пропускаем.
        callee = normalize_number(
            data.get("callee") or data.get("destination")
        )
        if not callee:
            return None
        status = str(data.get("status") or "").upper()
        talk = _int(data.get("dialog") or data.get("billsec"))
        recording = (
            data.get("recording_wav")
            or data.get("record_link")
            or data.get("recording")
        )
        answered = status == "ANSWERED" or bool(talk)
        return CallEvent(
            provider_call_id=(str(data["call_id"]) if data.get("call_id") else None),
            to_number=callee,
            answered=answered,
            duration_sec=_int(data.get("call_duration") or data.get("duration")),
            talk_sec=talk,
            recording_url=str(recording) if recording and answered else None,
        )
