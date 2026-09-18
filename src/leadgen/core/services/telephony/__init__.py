"""Телефония: общий слой над провайдерами звонков.

Платформа говорит с провайдером через ``TelephonyProvider`` — звонок
из карточки, разбор webhook. Украина идёт через Ringostat; другие
регионы добавятся адаптерами (Twilio/Telnyx) без изменений выше.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from leadgen.config import get_settings


def normalize_number(raw: str | None) -> str | None:
    """Номер в цифры E.164 без «+». Украинские 0XX… → 380XX…"""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 10 and digits.startswith("0"):
        digits = "38" + digits
    return digits


@dataclass(slots=True)
class CallEvent:
    """Итог звонка из webhook, приведённый к одному виду."""

    provider_call_id: str | None
    to_number: str | None
    answered: bool
    duration_sec: int | None
    talk_sec: int | None
    recording_url: str | None


class TelephonyError(RuntimeError):
    pass


class TelephonyProvider(Protocol):
    name: str

    async def start_call(self, *, extension: str, destination: str) -> None:
        """Сначала звонит сотруднику (extension), затем клиенту."""

    def parse_event(self, data: dict[str, Any]) -> CallEvent | None:
        """Webhook → CallEvent; None — событие не про итог звонка."""


def get_provider() -> TelephonyProvider | None:
    """Активный провайдер по настройкам, или None — телефония выключена."""
    settings = get_settings()
    name = (settings.telephony_provider or "").strip().lower()
    if name == "ringostat" and settings.ringostat_auth_key:
        from leadgen.core.services.telephony.ringostat import RingostatProvider

        return RingostatProvider(settings.ringostat_auth_key)
    return None
