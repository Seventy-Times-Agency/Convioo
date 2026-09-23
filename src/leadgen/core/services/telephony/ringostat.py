"""Ringostat: звонок из CRM (callback) и разбор webhook.

Звоним расширенным методом ``/a/v2``: Ringostat набирает сотрудника,
после ответа — клиента. Простой ``callback/outward_call`` не подходит:
его ``extension`` обязан быть номером проекта, подключённым в
Виртуальной АТС как "incoming", а расширенный принимает обычные
мобильные с обеих сторон — отделу продаж не нужен свой номер, чтобы
начать звонить.

Webhook шлёт параметры, которые настраиваются в кабинете Ringostat;
имена полей там зависят от версии, разбираем обе (см. parse_event).
"""

from __future__ import annotations

from typing import Any

import httpx

from leadgen.core.services.telephony import (
    CallEvent,
    TelephonyError,
    normalize_number,
)

API_URL = "https://api.ringostat.net/a/v2"
CALLBACK_METHOD = "Api\\V2\\Callback.external"


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

    def __init__(self, auth_key: str, project_id: str = "") -> None:
        self._key = auth_key
        self._project_id = project_id

    async def start_call(self, *, extension: str, destination: str) -> None:
        """Набрать сотрудника, после ответа соединить с клиентом."""
        params: dict[str, Any] = {
            "caller": extension,
            "callee": destination,
            "direction": "out",
        }
        if self._project_id:
            params["projectId"] = self._project_id
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                API_URL,
                headers={"Auth-key": self._key},
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": CALLBACK_METHOD,
                    "params": params,
                },
            )
        if resp.status_code >= 400:
            raise TelephonyError(
                f"ringostat {resp.status_code}: {resp.text[:200]}"
            )
        # JSON-RPC отвечает 200 и на отказ: и невалидные номера, и
        # запрет исходящих приходят в теле. Без этой проверки неудачный
        # звонок выглядел бы успешным, а продажник ждал бы гудка.
        try:
            body = resp.json()
        except ValueError:
            raise TelephonyError("ringostat: ответ не JSON") from None
        error = body.get("error") if isinstance(body, dict) else None
        if error:
            raise TelephonyError(f"ringostat: {str(error)[:300]}")

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
