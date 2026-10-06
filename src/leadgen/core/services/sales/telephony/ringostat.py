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

from leadgen.core.services.sales.telephony import (
    CallEvent,
    TelephonyError,
    normalize_number,
)

API_URL = "https://api.ringostat.net/a/v2"
SIP_ONLINE_URL = "https://api.ringostat.net/sipstatus/online"
CALLS_LIST_URL = "https://api.ringostat.net/calls/list"
#: В стерео-записи Ringostat первая дорожка — внешняя сторона (клиент),
#: вторая — SIP сотрудника. Проверено на живых записях 05.10.2026 для
#: обоих видов исходящих: и звонка из карточки (callback), и набора
#: прямо из Smart Phone.
REP_CHANNEL = 1
#: Имена полей calls/list — проверены на живом ответе (userfield и
#: recording_wav здесь не принимаются: «incorrect field name»).
CALLS_FIELDS = (
    "calldate,caller,dst,disposition,billsec,duration,call_type,"
    "has_recording,recording,uniqueid,connected_with"
)
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
    mode = "callback"

    def __init__(self, auth_key: str, project_id: str = "") -> None:
        self._key = auth_key
        self._project_id = project_id

    async def start_call(self, *, extension: str, destination: str) -> None:
        """Набрать сотрудника, после ответа соединить с клиентом.

        По документации расширенного метода ``caller`` — номер
        КЛИЕНТА, ``callee`` — номер или SIP СОТРУДНИКА, а кто звонит
        первым, решает ``manager_dst``: 0 — сначала callee (сотрудник),
        после ответа — caller (клиент). Раньше стороны были
        перепутаны: в журнале Ringostat SIP селза значился «клиентом»,
        а клиент — «сотрудником», и дозвон шёл не в ту сторону.
        """
        params: dict[str, Any] = {
            "caller": destination,
            "caller_type": "default",
            "callee": extension,
            "callee_type": "default",
            "manager_dst": 0,
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

    async def list_calls(self, since: Any) -> list[dict[str, Any]]:
        """Журнал звонков с ``since``. Время в запросе — в поясе
        проекта, поэтому берём окно с запасом на сутки в обе стороны и
        отсекаем лишнее по ``calldate`` уже у себя."""
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        params = {
            "export_type": "json",
            "from": (since - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
            "to": (now + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
            "fields": CALLS_FIELDS,
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                CALLS_LIST_URL,
                params=params,
                headers={"Auth-key": self._key, "Content-Type": "application/json"},
            )
        if resp.status_code >= 400:
            raise TelephonyError(f"ringostat calls/list {resp.status_code}")
        try:
            body = resp.json()
        except ValueError:
            raise TelephonyError(
                f"ringostat calls/list: {resp.text[:120]}"
            ) from None
        return [row for row in body if isinstance(row, dict)] if isinstance(body, list) else []

    async def sips_online(self) -> set[str] | None:
        """Все SIP-аккаунты проекта, которые сейчас в сети; None —
        проверить не удалось."""
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    SIP_ONLINE_URL, headers={"Auth-key": self._key}
                )
            if resp.status_code >= 400:
                return None
            body = resp.json()
        except Exception:  # noqa: BLE001
            return None
        if isinstance(body, dict):
            body = body.get("data") or body.get("result") or body.get("sips") or []
        if not isinstance(body, list):
            return None
        return {str(x) for x in body}

    async def sip_online(self, login: str) -> bool | None:
        """Зарегистрирован ли SIP-аккаунт сейчас (Smart Phone в сети).
        None — проверить не удалось; тогда звоним как есть."""
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    SIP_ONLINE_URL, headers={"Auth-key": self._key}
                )
            if resp.status_code >= 400:
                return None
            body = resp.json()
        except Exception:  # noqa: BLE001 — проверка не должна ронять звонок
            return None
        if isinstance(body, dict):
            body = body.get("data") or body.get("result") or body.get("sips") or []
        if not isinstance(body, list):
            return None
        return login in {str(x) for x in body}

    def parse_event(self, data: dict[str, Any]) -> CallEvent | None:
        # Имён у одного и того же поля два: классические вебхуки шлют
        # ``callee``/``status``/``call_id``, Webhooks 2.0 — ``dst``/
        # ``disposition``/``cdr_id``. Разбираем оба, чтобы смена версии
        # в кабинете не ломала приём.
        #
        # Где номер клиента — зависит от типа звонка. Реальное событие
        # входящего: ``dst`` = номер проекта, а клиент — в ``E164`` и
        # ``userfield``. У исходящего клиент — набранный ``dst``. Не
        # угадываем: собираем все номера, сопоставление выберет тот,
        # по которому есть наш звонок или лид.
        call_type = str(_first(data, "call_type", "type") or "").lower()
        inbound = call_type in {"in", "incoming", "callback"}
        order = (
            ("E164", "userfield", "caller", "full_num", "dst", "callee", "destination")
            if inbound
            else ("dst", "callee", "destination", "userfield", "E164", "caller", "full_num")
        )
        candidates: list[str] = []
        for key in order:
            number = normalize_number(str(data.get(key) or ""))
            # SIP-логин и короткие внутренние номера — не клиент.
            if number and len(number) >= 9 and number not in candidates:
                candidates.append(number)
        if not candidates:
            return None
        status = str(_first(data, "status", "disposition") or "").upper()
        talk = _int(_first(data, "dialog", "billsec"))
        recording = _first(
            data, "recording_wav", "record_link", "recording"
        )
        call_id = _first(data, "call_id", "cdr_id", "uniqueid")
        # Голосовая почта тоже даёт billsec > 0, но разговора не было.
        # Реальные статусы журнала: ANSWERED, PROPER (целевой разговор),
        # REPEATED (повторный разговор с тем же номером), CLIENT NO
        # ANSWER, VOICEMAIL.
        not_talked = (
            status in {"VOICEMAIL", "BUSY", "FAILED", "NOANSWER"}
            or "NO ANSWER" in status
        )
        answered = status in {"ANSWERED", "PROPER", "REPEATED"} or (
            bool(talk) and not not_talked
        )
        return CallEvent(
            provider_call_id=str(call_id) if call_id else None,
            to_number=candidates[0],
            answered=answered,
            duration_sec=_int(_first(data, "call_duration", "duration")),
            talk_sec=talk if answered else None,
            recording_url=str(recording) if recording and answered else None,
            candidates=tuple(candidates),
            direction="in" if inbound else ("out" if call_type else None),
            rep_channel=REP_CHANNEL,
        )
