"""Телефония: звонок из карточки, webhook провайдера, записи.

* ``GET  /teams/{id}/telephony``              — статус и настройки
* ``PATCH /teams/{id}/members/{uid}/phone``   — номер/SIP сотрудника
* ``POST /leads/{id}/call``                   — позвонить через провайдера
* ``POST /telephony/{provider}/webhook``      — итог звонка от провайдера
* ``GET  /leads/{id}/calls``                  — звонки лида с разбором
* ``GET  /calls/{id}/recording``              — прослушать запись

Селз видит звонки только своих лидов — то же правило, что везде.
Секрет webhook сравнивается за постоянное время; тело провайдера —
недоверенные данные, из него берём только известные поля.
"""

from __future__ import annotations

import hmac
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.routes._helpers import membership
from leadgen.adapters.web_api.routes.crm.leads import _authorise_lead_access
from leadgen.config import get_settings
from leadgen.core.services.account.team_permissions import (
    can_manage_members,
    is_sales,
)
from leadgen.core.services.sales.telephony import (
    TelephonyError,
    browser_provider,
    enabled_providers,
    get_provider,
    get_provider_for,
    normalize_number,
)
from leadgen.db.models import Call, Lead, SearchQuery, TeamMembership, User
from leadgen.db.session import session_factory

router = APIRouter(tags=["telephony"])
logger = logging.getLogger(__name__)

#: Имена параметров, которые нужно включить в webhook Ringostat.
# Имена полей Webhooks 2.0 в кабинете Ringostat. Разбор принимает и
# классические имена (call_id / callee / status / call_duration /
# dialog), но подсказываем актуальные — их и предлагает кабинет.
RINGOSTAT_WEBHOOK_PARAMS = (
    "cdr_id",
    "dst",
    "userfield",
    "disposition",
    "duration",
    "billsec",
    "recording_wav",
)


class TelephonyStatus(BaseModel):
    enabled: bool
    provider: str | None
    transcription: bool
    my_extension: str | None
    #: ``browser`` — звонок из вкладки (Telnyx), номер сотрудника не
    #: нужен; ``callback`` — провайдер звонит сотруднику первым.
    mode: str = "callback"
    #: Номер, который видит клиент при звонке из браузера.
    caller_number: str | None = None
    #: Для владельца/РОПа: адрес webhook и что прописать у провайдера.
    webhook_url: str | None = None
    webhook_params: list[str] = []
    members: list[dict[str, Any]] = []


class PhoneUpdate(BaseModel):
    phone_extension: str | None = Field(default=None, max_length=64)


class CallOut(BaseModel):
    id: uuid.UUID
    state: str
    created_at: datetime
    duration_sec: int | None
    talk_sec: int | None
    has_recording: bool
    transcript: list[dict[str, Any]] | None
    analysis: dict[str, Any] | None
    error: str | None
    record_consent: bool = True
    user_name: str | None = None


def _webhook_url(request: Request, provider: str) -> str | None:
    token = get_settings().telephony_webhook_token
    if not token:
        return None
    base = str(request.base_url).rstrip("/")
    return f"{base}/api/v1/telephony/{provider}/webhook?token={token}"


@router.get("/api/v1/teams/{team_id}/telephony", response_model=TelephonyStatus)
async def telephony_status(
    team_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> TelephonyStatus:
    providers = enabled_providers()
    provider = get_provider(providers[0]) if providers else None
    settings = get_settings()
    async with session_factory() as session:
        ms = await membership(session, team_id, current_user.id)
        if ms is None:
            raise HTTPException(status_code=403, detail="not a team member")
        browser = browser_provider()
        out = TelephonyStatus(
            enabled=bool(providers),
            provider=", ".join(providers) or None,
            transcription=bool(settings.elevenlabs_api_key),
            my_extension=ms.phone_extension,
            mode="browser" if browser is not None else "callback",
            caller_number=getattr(browser, "caller_id", None),
        )
        if can_manage_members(ms.role):
            if browser is not None:
                out.webhook_url = _webhook_url(request, browser.name)
            elif provider is not None:
                out.webhook_url = _webhook_url(request, provider.name)
                out.webhook_params = list(RINGOSTAT_WEBHOOK_PARAMS)
            rows = (
                await session.execute(
                    select(TeamMembership, User)
                    .join(User, User.id == TeamMembership.user_id)
                    .where(TeamMembership.team_id == team_id)
                    .order_by(TeamMembership.created_at)
                )
            ).all()
            out.members = [
                {
                    "user_id": u.id,
                    "name": u.display_name or u.first_name or f"#{u.id}",
                    "role": mem.role,
                    "phone_extension": mem.phone_extension,
                }
                for mem, u in rows
            ]
        return out


@router.patch("/api/v1/teams/{team_id}/members/{member_user_id}/phone")
async def set_member_phone(
    team_id: uuid.UUID,
    member_user_id: int,
    body: PhoneUpdate,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Номер/SIP для звонков. Свой — любой участник, чужой — РОП и
    владелец."""
    async with session_factory() as session:
        caller = await membership(session, team_id, current_user.id)
        if caller is None:
            raise HTTPException(status_code=403, detail="not a team member")
        if member_user_id != current_user.id and not can_manage_members(
            caller.role
        ):
            raise HTTPException(
                status_code=403, detail="only owner or head of sales"
            )
        target = await membership(session, team_id, member_user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="member not found")
        value = (body.phone_extension or "").strip() or None
        target.phone_extension = value
        await session.commit()
        return {"ok": True, "phone_extension": value}


@router.post("/api/v1/leads/{lead_id}/call")
async def start_call(
    lead_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Позвонить лиду через провайдера: сначала зазвонит телефон
    сотрудника, после ответа — клиента."""
    async with session_factory() as session:
        lead, search = await _authorise_lead_access(
            session, lead_id, current_user.id
        )
        destination = normalize_number(lead.phone)
        if not destination:
            raise HTTPException(status_code=400, detail="lead has no phone number")
        # Провайдер под регион клиента: Украина — Ringostat, другие
        # страны — свои провайдеры по маршрутам TELEPHONY_ROUTES.
        provider = get_provider_for(destination)
        if provider is None:
            raise HTTPException(
                status_code=409,
                detail="no phone provider for this region",
            )
        team_id = search.team_id if search is not None else None
        if getattr(provider, "mode", "callback") == "browser":
            # Селз звонит сам из вкладки: нам достаточно завести
            # строку звонка — webhook провайдера найдёт её по номеру.
            call = Call(
                team_id=team_id,
                lead_id=lead.id,
                user_id=current_user.id,
                provider=provider.name,
                to_number=destination,
                state="dialing",
            )
            session.add(call)
            await session.commit()
            return {
                "ok": True,
                "call_id": str(call.id),
                "mode": "browser",
                "destination": f"+{destination}",
                "caller_number": getattr(provider, "caller_id", None),
            }
        extension = None
        if team_id is not None:
            ms = await membership(session, team_id, current_user.id)
            extension = ms.phone_extension if ms is not None else None
        if not extension:
            raise HTTPException(
                status_code=409,
                detail=(
                    "set your phone number for calls in Settings → "
                    "Telephony first"
                ),
            )
        # SIP-логин (не номер): если Smart Phone не в сети, звонок
        # уйдёт в пустоту — провайдер будет минуту ждать ответа SIP.
        # Лучше сразу сказать селзу, что делать.
        caller = normalize_number(extension)
        is_sip_login = not (caller and len(caller) >= 10)
        check_online = getattr(provider, "sip_online", None)
        if is_sip_login and check_online is not None:
            online = await check_online(extension)
            if online is False:
                raise HTTPException(
                    status_code=409,
                    detail="your softphone is offline: open Ringostat Smart Phone and sign in",
                )
        call = Call(
            team_id=team_id,
            lead_id=lead.id,
            user_id=current_user.id,
            provider=provider.name,
            to_number=destination,
            state="dialing",
        )
        session.add(call)
        await session.commit()
        try:
            # Номер сотрудника тоже приводим к международному виду:
            # в настройках его пишут как привыкли («067…»), а провайдер
            # ждёт E.164. Короткие значения — это SIP-аккаунт или
            # внутренний номер, их отдаём как есть.
            await provider.start_call(
                extension=(
                    f"+{caller}" if caller and len(caller) >= 10 else extension
                ),
                destination=f"+{destination}",
            )
        except TelephonyError as exc:
            call.state = "failed"
            call.error = str(exc)[:500]
            await session.commit()
            raise HTTPException(status_code=502, detail="the phone provider refused the call") from exc
        return {"ok": True, "call_id": str(call.id), "mode": "callback"}


class WebrtcTokenRequest(BaseModel):
    team_id: uuid.UUID


@router.post("/api/v1/telephony/webrtc-token")
async def webrtc_token(
    body: WebrtcTokenRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """JWT для звонка из браузера. Credential у провайдера заводится
    на человека один раз и запоминается; токен живёт сутки, браузер
    запрашивает новый сам."""
    provider = browser_provider()
    if provider is None:
        raise HTTPException(status_code=409, detail="browser calling is not enabled")
    async with session_factory() as session:
        ms = await membership(session, body.team_id, current_user.id)
        if ms is None:
            raise HTTPException(status_code=403, detail="not a team member")
        user = await session.get(User, current_user.id)
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")
        try:
            if not user.webrtc_credential_id:
                user.webrtc_credential_id = await provider.create_credential(  # type: ignore[attr-defined]
                    f"convioo-u{user.id}"
                )
                await session.commit()
            token = await provider.webrtc_token(user.webrtc_credential_id)  # type: ignore[attr-defined]
        except TelephonyError as exc:
            logger.warning("webrtc token failed for user %s: %s", current_user.id, exc)
            raise HTTPException(
                status_code=502, detail="the phone provider refused the token"
            ) from exc
    from leadgen.core.services.sales.telephony.telnyx import TOKEN_TTL_SEC

    return {
        "provider": provider.name,
        "token": token,
        "caller_number": getattr(provider, "caller_id", None),
        "expires_in": TOKEN_TTL_SEC,
    }


async def _payload(request: Request, raw: bytes | None = None) -> dict[str, Any]:
    import json

    data: dict[str, Any] = dict(request.query_params)
    data.pop("token", None)
    ctype = request.headers.get("content-type", "")
    try:
        if "application/json" in ctype:
            body = json.loads(raw) if raw is not None else await request.json()
            if isinstance(body, dict):
                data.update(body)
        else:
            form = await request.form()
            data.update({k: v for k, v in form.items() if isinstance(v, str)})
    except Exception:  # noqa: BLE001 — кривое тело не должно ронять ответ
        pass
    return data


async def _lead_for_direct_call(
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


@router.api_route("/api/v1/telephony/{provider_name}/webhook", methods=["GET", "POST"])
async def telephony_webhook(
    provider_name: str, request: Request
) -> dict[str, Any]:
    expected = get_settings().telephony_webhook_token
    supplied = request.query_params.get("token") or ""
    if not expected or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=403, detail="bad token")
    # Провайдера берём по имени из адреса, а не из TELEPHONY_PROVIDER:
    # тот задаёт провайдера по умолчанию для исходящих и может быть
    # пуст, когда регионы разведены только через TELEPHONY_ROUTES.
    # Неподключённый провайдер всё равно отсеется — без ключа
    # ``get_provider`` возвращает None.
    provider = get_provider(provider_name)
    if provider is None:
        return {"ok": True, "ignored": "provider disabled"}

    raw = await request.body()
    verify = getattr(provider, "verify_signature", None)
    if verify is not None and not verify(
        raw,
        request.headers.get("telnyx-signature-ed25519"),
        request.headers.get("telnyx-timestamp"),
    ):
        raise HTTPException(status_code=403, detail="bad signature")

    event = provider.parse_event(await _payload(request, raw))
    if event is None:
        return {"ok": True, "ignored": "not a call result"}
    if event.kind == "recording":
        return await _attach_recording(provider, event)
    if event.kind == "answered":
        return await _on_answered(provider, event)
    if not event.to_number:
        return {"ok": True, "ignored": "not a call result"}

    since = datetime.now(timezone.utc) - timedelta(hours=3)
    async with session_factory() as session:
        call = None
        if event.provider_call_id:
            call = (
                await session.execute(
                    select(Call).where(
                        Call.provider_call_id == event.provider_call_id
                    )
                )
            ).scalar_one_or_none()
        if call is not None and call.completed_at is not None:
            # Повтор того же события: провайдер шлёт webhook заново,
            # если не дождался ответа. Итог уже записан, запись уже в
            # обработке — второй раз не расшифровываем и не платим.
            return {"ok": True, "ignored": "duplicate"}
        if call is None:
            # Наш звонок из карточки: тот же номер, ещё без итога.
            call = (
                await session.execute(
                    select(Call)
                    .where(Call.to_number == event.to_number)
                    .where(Call.state == "dialing")
                    .where(Call.created_at >= since)
                    .order_by(Call.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        if call is None:
            # Звонок мимо платформы (с телефона напрямую) — если номер
            # принадлежит известному лиду, всё равно сохраним разговор.
            match, match_team_id = await _lead_for_direct_call(
                session, event.to_number
            )
            if match is None:
                return {"ok": True, "ignored": "unknown number"}
            call = Call(
                team_id=match_team_id,
                lead_id=match.id,
                user_id=match.owner_user_id,
                provider=provider.name,
                to_number=event.to_number,
            )
            session.add(call)

        call.provider_call_id = event.provider_call_id or call.provider_call_id
        call.duration_sec = event.duration_sec
        call.talk_sec = event.talk_sec
        # Клиент отказался от записи — ссылку не сохраняем вовсе.
        call.recording_url = (
            event.recording_url if call.record_consent else None
        )
        call.state = "completed" if event.answered else "missed"
        call.completed_at = datetime.now(timezone.utc)
        await session.commit()
        call_id = call.id
        should_process = bool(call.recording_url)

    if should_process:
        from leadgen.core.services.sales.telephony.processing import schedule

        await schedule(call_id)
    return {"ok": True}


async def _find_dialing(session: Any, to_number: str, since: datetime) -> Call | None:
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


async def _on_answered(provider: Any, event: Any) -> dict[str, Any]:
    """Соединились: привязываем id сессии провайдера к нашему звонку
    и просим писать разговор, если клиент не против."""
    since = datetime.now(timezone.utc) - timedelta(hours=3)
    async with session_factory() as session:
        call = None
        if event.to_number:
            call = await _find_dialing(session, event.to_number, since)
        if call is None:
            return {"ok": True, "ignored": "unknown call"}
        call.provider_call_id = event.provider_call_id or call.provider_call_id
        await session.commit()
        consent = call.record_consent
    record = getattr(provider, "record_start", None)
    if consent and record is not None and event.call_control_id:
        try:
            await record(event.call_control_id)
        except TelephonyError as exc:
            logger.warning("record_start failed: %s", exc)
    return {"ok": True}


async def _attach_recording(provider: Any, event: Any) -> dict[str, Any]:
    """Запись приходит отдельным событием после итога: находим звонок
    по id сессии провайдера и запускаем расшифровку."""
    if not event.provider_call_id or not event.recording_url:
        return {"ok": True, "ignored": "no recording"}
    async with session_factory() as session:
        call = (
            await session.execute(
                select(Call).where(Call.provider_call_id == event.provider_call_id)
            )
        ).scalar_one_or_none()
        if call is None:
            return {"ok": True, "ignored": "unknown call"}
        if call.recording_url or not call.record_consent:
            return {"ok": True, "ignored": "duplicate" if call.recording_url else "no consent"}
        call.recording_url = event.recording_url
        await session.commit()
        call_id = call.id
    from leadgen.core.services.sales.telephony.processing import schedule

    await schedule(call_id)
    return {"ok": True}


class ConsentUpdate(BaseModel):
    allowed: bool


@router.post("/api/v1/calls/{call_id}/consent")
async def set_record_consent(
    call_id: uuid.UUID,
    body: ConsentUpdate,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """«Отменить запись» / «Включить запись» во время звонка. Отказ
    стирает у нас всё, что уже успело появиться: ссылку, текст, разбор."""
    async with session_factory() as session:
        call = await session.get(Call, call_id)
        if call is None or call.lead_id is None:
            raise HTTPException(status_code=404, detail="call not found")
        await _authorise_lead_access(session, call.lead_id, current_user.id)
        call.record_consent = body.allowed
        if not body.allowed:
            call.recording_url = None
            call.transcript = None
            call.analysis = None
        await session.commit()
        return {"ok": True, "record_consent": call.record_consent}


@router.get("/api/v1/leads/{lead_id}/calls", response_model=list[CallOut])
async def lead_calls(
    lead_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> list[CallOut]:
    async with session_factory() as session:
        await _authorise_lead_access(session, lead_id, current_user.id)
        rows = (
            await session.execute(
                select(Call, User)
                .outerjoin(User, User.id == Call.user_id)
                .where(Call.lead_id == lead_id)
                .order_by(Call.created_at.desc())
                .limit(30)
            )
        ).all()
        return [
            CallOut(
                id=c.id,
                state=c.state,
                created_at=c.created_at,
                duration_sec=c.duration_sec,
                talk_sec=c.talk_sec,
                has_recording=bool(c.recording_url),
                transcript=c.transcript,
                analysis=c.analysis,
                error=c.error,
                record_consent=c.record_consent,
                user_name=(u.display_name or u.first_name) if u else None,
            )
            for c, u in rows
        ]


@router.get("/api/v1/calls/{call_id}/recording")
async def call_recording(
    call_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Прослушать запись через нас: ссылка провайдера наружу не уходит,
    доступ — по тем же правилам, что к лиду."""
    import httpx

    async with session_factory() as session:
        call = await session.get(Call, call_id)
        if call is None or call.lead_id is None or not call.recording_url:
            raise HTTPException(status_code=404, detail="recording not found")
        await _authorise_lead_access(session, call.lead_id, current_user.id)
        url = call.recording_url
    from leadgen.core.services.sales.telephony import guarded_stream

    client = httpx.AsyncClient(timeout=60.0, follow_redirects=False)
    try:
        upstream = await guarded_stream(client, url)
    except Exception as exc:
        await client.aclose()
        raise HTTPException(status_code=502, detail="recording unavailable") from exc
    if upstream.status_code >= 400:
        await upstream.aclose()
        await client.aclose()
        raise HTTPException(status_code=502, detail="recording unavailable")

    async def body():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        body(),
        media_type=upstream.headers.get("content-type", "audio/wav"),
    )


__all__ = ["router", "is_sales"]
