"""Telnyx: звонок прямо из браузера, запись и итог через webhooks.

Схема отличается от Ringostat. Там платформа просит провайдера набрать
сотрудника, потом клиента. Здесь селз звонит сам из вкладки Convioo:
бэкенд выдаёт браузеру короткоживущий JWT (телефонный credential на
пользователя), WebRTC SDK Telnyx набирает номер клиента, а Telnyx
присылает события на наш webhook:

* ``call.answered``        — соединились; просим ``record_start``;
* ``call.hangup``          — итог: причина, время начала/конца;
* ``call.recording.saved`` — ссылка на запись (приходит позже hangup).

Настройка в кабинете Telnyx (один раз):
  1. Номер (Numbers → Buy).
  2. Voice → SIP Connections → Credential Connection, в нём
     Webhook URL = адрес из Настройки → Телефония, API version 2;
     номер назначен на это соединение; Outbound Voice Profile задан.
  3. API Key (Auth → API Keys) и Public Key (Auth → Public Key) —
     второй нужен, чтобы проверять подпись webhook.
Переменные: TELNYX_API_KEY, TELNYX_CONNECTION_ID, TELNYX_CALLER_ID,
TELNYX_PUBLIC_KEY (необязательна), маршрут ``1:telnyx`` в
TELEPHONY_ROUTES или TELEPHONY_PROVIDER=telnyx.
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime
from typing import Any

import httpx

from leadgen.core.services.sales.telephony import (
    CallEvent,
    TelephonyError,
    normalize_number,
)

logger = logging.getLogger(__name__)

API_BASE = "https://api.telnyx.com/v2"
#: Сколько живёт JWT для браузера. Telnyx выдаёт на 24 часа; свой
#: срок мы не задаём, просто перезапрашиваем токен раз в сутки.
TOKEN_TTL_SEC = 24 * 3600


def _parse_ts(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _pstn_number(*candidates: Any) -> str | None:
    """Из ``from``/``to`` берём тот, что похож на телефон: вторая
    сторона у звонка из браузера — ``sip:<credential>@sip.telnyx.com``."""
    for raw in candidates:
        if not raw or not isinstance(raw, str) or raw.startswith("sip:"):
            continue
        digits = normalize_number(raw)
        if digits and len(digits) >= 7:
            return digits
    return None


class TelnyxProvider:
    name = "telnyx"
    #: Звонок начинается в браузере — бэкенд не набирает никого сам.
    mode = "browser"

    def __init__(
        self,
        api_key: str,
        connection_id: str,
        caller_id: str,
        public_key: str = "",
    ) -> None:
        self._key = api_key
        self.connection_id = connection_id
        self.caller_id = caller_id
        self._public_key = public_key

    # ── HTTP ─────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
        }

    async def _post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{API_BASE}{path}", headers=self._headers(), json=body or {}
            )
        if resp.status_code >= 400:
            raise TelephonyError(f"telnyx {resp.status_code}: {resp.text[:300]}")
        try:
            return resp.json()
        except ValueError:
            # Токен приходит как JWT в plain text, не JSON.
            return {"text": resp.text}

    # ── WebRTC: credential на пользователя + JWT ──────────────────────

    async def create_credential(self, name: str) -> str:
        """Создать телефонный credential под одного пользователя.
        Каждому — свой: так Telnyx различает, кто звонил, и токен
        одного человека не открывает линию другому."""
        data = await self._post(
            "/telephony_credentials",
            {"connection_id": self.connection_id, "name": name},
        )
        cred_id = (data.get("data") or {}).get("id")
        if not cred_id:
            raise TelephonyError("telnyx: credential without id")
        return str(cred_id)

    async def webrtc_token(self, credential_id: str) -> str:
        data = await self._post(f"/telephony_credentials/{credential_id}/token")
        token = data.get("text") or (data.get("data") or {}).get("token")
        if not token or not isinstance(token, str):
            raise TelephonyError("telnyx: empty token")
        return token.strip()

    # ── Call Control ─────────────────────────────────────────────────

    async def record_start(self, call_control_id: str) -> None:
        """Писать разговор с момента ответа. Две дорожки: селз слева,
        клиент справа — расшифровка тогда точно знает, кто говорит."""
        await self._post(
            f"/calls/{call_control_id}/actions/record_start",
            {"format": "mp3", "channels": "dual"},
        )

    async def start_call(self, *, extension: str, destination: str) -> None:
        # Исходящий через бэкенд (сначала телефон селза, потом клиент)
        # для Telnyx не делаем: звонок идёт из браузера.
        raise TelephonyError("telnyx calls start in the browser")

    # ── Webhooks ─────────────────────────────────────────────────────

    def verify_signature(self, body: bytes, signature: str | None, timestamp: str | None) -> bool:
        """Подпись Ed25519 над ``timestamp|body``. Без публичного ключа
        проверка не выполняется — остаётся токен в адресе webhook."""
        if not self._public_key:
            return True
        if not signature or not timestamp:
            return False
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PublicKey,
            )

            key = Ed25519PublicKey.from_public_bytes(
                base64.b64decode(self._public_key)
            )
            key.verify(
                base64.b64decode(signature),
                f"{timestamp}|".encode() + body,
            )
            return True
        except Exception:  # noqa: BLE001 — любая ошибка = подпись не сошлась
            return False

    def parse_event(self, data: dict[str, Any]) -> CallEvent | None:
        envelope = data.get("data") if isinstance(data.get("data"), dict) else data
        event_type = str(envelope.get("event_type") or "")
        payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
        session_id = payload.get("call_session_id")
        provider_call_id = str(session_id) if session_id else None
        to_number = _pstn_number(payload.get("to"), payload.get("from"))

        if event_type == "call.answered":
            return CallEvent(
                kind="answered",
                provider_call_id=provider_call_id,
                to_number=to_number,
                answered=True,
                duration_sec=None,
                talk_sec=None,
                recording_url=None,
                call_control_id=payload.get("call_control_id"),
            )

        if event_type == "call.hangup":
            start = _parse_ts(payload.get("start_time"))
            end = _parse_ts(payload.get("end_time"))
            duration = (
                max(int((end - start).total_seconds()), 0)
                if start and end
                else None
            )
            # ``normal_clearing`` — положили трубку после разговора;
            # всё остальное (timeout, user_busy, originator_cancel…) —
            # соединения не было.
            answered = str(payload.get("hangup_cause") or "") == "normal_clearing"
            return CallEvent(
                kind="result",
                provider_call_id=provider_call_id,
                to_number=to_number,
                answered=answered,
                duration_sec=duration,
                talk_sec=duration if answered else None,
                recording_url=None,
            )

        if event_type == "call.recording.saved":
            urls = payload.get("recording_urls") or {}
            url = urls.get("mp3") or urls.get("wav")
            if not url:
                return None
            return CallEvent(
                kind="recording",
                provider_call_id=provider_call_id,
                to_number=to_number,
                answered=True,
                duration_sec=None,
                talk_sec=None,
                recording_url=str(url),
            )

        return None
