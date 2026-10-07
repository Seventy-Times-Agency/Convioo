"""``GET /api/v1/teams/{team_id}/tech-info`` — полная техническая сводка.

Для владельца и техника. Всё, что техотделу нужно, чтобы связать
Convioo со своим ядром управления: адреса и IP, способы авторизации,
входящие и исходящие вебхуки, каталог API, внешние сервисы, фоновые
задачи, лимиты и идентификаторы команды. Секретов здесь нет.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.routing import APIRoute
from sqlalchemy import select, text

from leadgen.adapters.web_api.auth import COOKIE_NAME, get_current_user, request_ip
from leadgen.adapters.web_api.routes._helpers import membership
from leadgen.config import get_settings
from leadgen.core.services.account.team_permissions import has_full_access
from leadgen.core.services.platform import tech_info
from leadgen.db.models import Funnel, LeadStatus, Team, TeamMembership, User, Webhook
from leadgen.db.session import session_factory

router = APIRouter(tags=["tech"])


def _api_catalog(request: Request) -> list[dict[str, Any]]:
    rows = []
    for route in request.app.routes:
        if not isinstance(route, APIRoute) or not route.include_in_schema:
            continue
        if not route.path.startswith("/api/"):
            continue
        doc = (route.endpoint.__doc__ or "").strip().splitlines()
        summary = route.summary or (doc[0].strip() if doc else "")
        group = (route.tags[0] if route.tags else route.path.split("/")[3]) if route.path.count("/") >= 3 else "api"
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            rows.append({"group": str(group), "method": method, "path": route.path, "summary": summary[:160]})
    rows.sort(key=lambda r: (r["group"], r["path"], r["method"]))
    return rows


@router.get("/api/v1/teams/{team_id}/tech-info")
async def tech_overview(
    team_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    from leadgen.core.services.integrations.webhooks import (
        ALLOWED_EVENTS,
        DELIVERY_TIMEOUT_S,
        MAX_CONSECUTIVE_FAILURES,
        SIGNATURE_HEADER,
        SIGNATURE_TIMESTAMPED_HEADER,
    )
    from leadgen.core.services.platform.health_probes import probes_for_health

    settings = get_settings()
    async with session_factory() as session:
        ms = await membership(session, team_id, current_user.id)
        if ms is None or not has_full_access(ms.role):
            raise HTTPException(status_code=403, detail="owner or tech only")
        team = await session.get(Team, team_id)
        members = (
            await session.execute(
                select(TeamMembership, User)
                .join(User, User.id == TeamMembership.user_id)
                .where(TeamMembership.team_id == team_id)
            )
        ).all()
        funnels = (
            await session.execute(select(Funnel).where(Funnel.team_id == team_id))
        ).scalars().all()
        statuses = (
            await session.execute(
                select(LeadStatus).where(LeadStatus.team_id == team_id).order_by(LeadStatus.order_index)
            )
        ).scalars().all()
        my_hooks = (
            await session.execute(select(Webhook).where(Webhook.user_id == current_user.id))
        ).scalars().all()
        try:
            revision = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar()
        except Exception:  # noqa: BLE001 — SQLite без alembic
            revision = None

    api_direct = str(request.base_url).rstrip("/")
    app_url = settings.public_app_url.rstrip("/")
    probes, egress, api_ips, app_ips = await asyncio.gather(
        probes_for_health(),
        tech_info.egress_ip(),
        tech_info.resolve(request.url.hostname),
        tech_info.resolve(tech_info.host_of(app_url)),
    )
    token = settings.telephony_webhook_token

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime": {
            **tech_info.runtime(),
            "db_ok": bool(probes["db"]),
            "db_dialect": settings.sqlalchemy_url.split(":", 1)[0],
            "db_revision": revision,
            "redis": probes["redis"],
            "queue_depth": probes["queue_depth"],
        },
        "network": {
            "app_url": app_url,
            "api_via_app": f"{app_url}/api/v1",
            "api_direct": f"{api_direct}/api/v1",
            "api_host_ips": api_ips,
            "app_host_ips": app_ips,
            "egress_ip": egress,
            "your_ip": request_ip(request),
            "cors_origins": [o.strip() for o in (settings.web_cors_origins or "").split(",") if o.strip()],
            "docs": {"swagger": f"{api_direct}/docs", "openapi": f"{api_direct}/openapi.json",
                     "health": f"{api_direct}/health", "metrics": f"{api_direct}/metrics"},
        },
        "auth": {
            "api_key_header": "Authorization: Bearer convioo_pk_…",
            "api_key_where": "Настройки → Техническое → API-ключи (ключ действует от имени создавшего)",
            "session_cookie": COOKIE_NAME,
            "csrf": "Запросы с cookie проверяются по Origin; запросы с Bearer-ключом — без cookie и CSRF",
            "roles": ["owner", "tech", "admin", "manager", "sales"],
        },
        "inbound": [
            {"name": "Telnyx (события звонков)", "method": "POST",
             "url": f"{api_direct}/api/v1/telephony/telnyx/webhook?token={token}" if token else None,
             "auth": "token в URL + подпись Ed25519 (TELNYX_PUBLIC_KEY)"},
            {"name": "Ringostat (события звонков)", "method": "POST",
             "url": f"{api_direct}/api/v1/telephony/ringostat/webhook?token={token}" if token else None,
             "auth": "token в URL"},
            {"name": "Telegram-бот", "method": "POST", "url": f"{api_direct}/api/v1/telegram/webhook",
             "auth": "заголовок X-Telegram-Bot-Api-Secret-Token"},
            {"name": "Gmail OAuth (возврат)", "method": "GET", "url": settings.google_oauth_redirect_uri, "auth": "подписанный state"},
            {"name": "Stripe", "method": "POST", "url": f"{api_direct}/api/v1/billing/webhook", "auth": "подпись Stripe"},
            {"name": "Отписка от писем", "method": "GET/POST", "url": f"{api_direct}/api/v1/unsubscribe/{{token}}",
             "auth": "подписанный токен в ссылке"},
            {"name": "Пиксель открытия письма", "method": "GET", "url": f"{api_direct}/api/v1/track/{{token}}",
             "auth": "HMAC-токен"},
        ],
        "outbound_webhooks": {
            "events": list(ALLOWED_EVENTS),
            "manage": f"{api_direct}/api/v1/webhooks",
            "signature": f"{SIGNATURE_HEADER}: sha256=<HMAC-SHA256(secret, body)>",
            "signature_timestamped": f"{SIGNATURE_TIMESTAMPED_HEADER}: t=<unix>,v1=<HMAC-SHA256(secret, t.body)> + X-Convioo-Timestamp",
            "timeout_s": DELIVERY_TIMEOUT_S,
            "disable_after_failures": MAX_CONSECUTIVE_FAILURES,
            "yours": [
                {"id": str(h.id), "url": h.target_url, "events": list(h.event_types or []), "active": h.active}
                for h in my_hooks
            ],
        },
        "integrations": tech_info.integrations(),
        "flags": tech_info.flags(),
        "jobs": tech_info.jobs(),
        "limits": tech_info.limits(),
        "team": {
            "id": str(team_id),
            "name": team.name if team else None,
            "your_user_id": current_user.id,
            "members": [
                {"user_id": u.id, "name": u.display_name or " ".join(filter(None, [u.first_name, u.last_name])) or None,
                 "email": u.email, "role": m.role, "squad_id": str(m.squad_id) if m.squad_id else None}
                for m, u in members
            ],
            "funnels": [{"id": str(f.id), "name": f.name, "status": f.status} for f in funnels],
            "lead_statuses": [{"key": s.key, "label": s.label, "terminal": s.is_terminal} for s in statuses],
        },
        "api": _api_catalog(request),
    }
