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


def _build(name: str) -> TelephonyProvider | None:
    settings = get_settings()
    name = name.strip().lower()
    if name == "ringostat" and settings.ringostat_auth_key:
        from leadgen.core.services.telephony.ringostat import RingostatProvider

        return RingostatProvider(settings.ringostat_auth_key)
    return None


def _routes() -> list[tuple[str, str]]:
    """``TELEPHONY_ROUTES="380:ringostat,1:twilio"`` → [(префикс, имя)],
    длинные префиксы первыми — «1» не перехватит «1242»."""
    raw = get_settings().telephony_routes or ""
    out: list[tuple[str, str]] = []
    for part in raw.split(","):
        if ":" in part:
            prefix, name = part.split(":", 1)
            prefix = re.sub(r"\D", "", prefix)
            if prefix and name.strip():
                out.append((prefix, name.strip().lower()))
    return sorted(out, key=lambda r: -len(r[0]))


def get_provider_for(number: str | None) -> TelephonyProvider | None:
    """Провайдер под регион номера: сначала маршруты по коду страны,
    иначе провайдер по умолчанию (TELEPHONY_PROVIDER)."""
    digits = normalize_number(number)
    if digits:
        for prefix, name in _routes():
            if digits.startswith(prefix):
                return _build(name)
    return get_provider()


def get_provider(name: str | None = None) -> TelephonyProvider | None:
    """Провайдер по имени, либо по умолчанию; None — телефония выключена."""
    return _build(name or get_settings().telephony_provider or "")


def enabled_providers() -> list[str]:
    names = {get_settings().telephony_provider or ""} | {n for _p, n in _routes()}
    return sorted(n for n in names if n and _build(n) is not None)


async def guarded_stream(client: Any, url: str) -> Any:
    """GET с потоковой отдачей, где каждый редирект проверяется на
    публичный адрес: ссылка провайдера могла бы увести запрос во
    внутреннюю сеть. Возвращает открытый ответ — закрывает вызывающий."""
    import urllib.parse

    from leadgen.collectors.website import assert_public_url

    for _ in range(5):
        await assert_public_url(url)
        resp = await client.send(client.build_request("GET", url), stream=True)
        if resp.is_redirect and resp.headers.get("location"):
            await resp.aclose()
            url = urllib.parse.urljoin(url, resp.headers["location"])
            continue
        return resp
    raise TelephonyError("too many redirects")
