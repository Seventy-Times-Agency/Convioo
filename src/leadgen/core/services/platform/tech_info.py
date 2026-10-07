"""Техническая сводка платформы для вкладки «Техническое».

Техотдел клиента переносит часть управления Convioo в своё ядро, и ему
нужна полная картина: где что крутится, какие внешние сервисы
подключены, какие у платформы адреса и IP, какие фоновые задачи и
лимиты. Здесь собирается всё, что можно показать БЕЗ секретов: ключи,
токены и пароли никогда не возвращаются — только «настроено / нет» и
имена переменных окружения.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import socket
import sys
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from leadgen.config import get_settings

logger = logging.getLogger(__name__)

_STARTED_AT = datetime.now(timezone.utc)

# (ключ, название, зачем, переменные окружения, поле настроек для «настроено»)
_INTEGRATIONS: tuple[tuple[str, str, str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("google_places", "Google Places API (New)", "Поиск компаний на картах — основной источник лидов",
     ("GOOGLE_PLACES_API_KEY",), ("google_places_api_key",)),
    ("anthropic", "Anthropic Claude", "Оценка лидов, советы, черновики писем, Henry, разбор звонков",
     ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "HENRY_MODEL"), ("anthropic_api_key",)),
    ("osm", "OpenStreetMap (Nominatim + Overpass)", "Геокодинг городов и второй источник компаний",
     ("OSM_ENABLED", "NOMINATIM_BASE_URL", "OVERPASS_BASE_URL"), ("osm_enabled",)),
    ("yelp", "Yelp Fusion", "Канал «Репутация»: отзывы и рейтинг", ("YELP_API_KEY", "YELP_ENABLED"), ("yelp_api_key",)),
    ("foursquare", "Foursquare Places", "Канал «Репутация»", ("FSQ_API_KEY", "FSQ_ENABLED"), ("fsq_api_key",)),
    ("adzuna", "Adzuna", "Канал «Рост»: компании, которые нанимают", ("ADZUNA_APP_ID", "ADZUNA_API_KEY", "ADZUNA_ENABLED"),
     ("adzuna_app_id", "adzuna_api_key")),
    ("companies_house", "Companies House (UK)", "Реестр компаний Великобритании, директора",
     ("COMPANIES_HOUSE_API_KEY", "COMPANIES_HOUSE_ENABLED"), ("companies_house_api_key",)),
    ("opencorporates", "OpenCorporates", "Реестры компаний, поиск ЛПР", ("OPENCORPORATES_API_TOKEN",), ("opencorporates_api_token",)),
    ("hunter", "Hunter.io", "Поиск email по домену", ("HUNTER_API_KEY",), ("hunter_api_key",)),
    ("apollo", "Apollo", "Поиск ЛПР (руководителя)", ("APOLLO_API_KEY",), ("apollo_api_key",)),
    ("gmail", "Gmail OAuth", "Отправка писем с почты менеджера, входящие, отслеживание ответов",
     ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REDIRECT_URI"),
     ("google_oauth_client_id", "google_oauth_client_secret")),
    ("resend", "Resend", "Системные письма: подтверждение, сброс пароля, срочные уведомления",
     ("RESEND_API_KEY", "EMAIL_FROM"), ("resend_api_key",)),
    ("telnyx", "Telnyx", "Звонки из браузера (WebRTC) и запись разговоров",
     ("TELNYX_API_KEY", "TELNYX_CONNECTION_ID", "TELNYX_CALLER_ID", "TELNYX_PUBLIC_KEY"), ("telnyx_api_key",)),
    ("ringostat", "Ringostat", "Звонки через обратный вызов (Украина) и записи",
     ("RINGOSTAT_AUTH_KEY", "RINGOSTAT_PROJECT_ID"), ("ringostat_auth_key",)),
    ("elevenlabs", "ElevenLabs STT", "Расшифровка записей звонков", ("ELEVENLABS_API_KEY", "ELEVENLABS_STT_MODEL"),
     ("elevenlabs_api_key",)),
    ("telegram", "Telegram Bot API", "Копии уведомлений и /search из бота",
     ("TELEGRAM_BOT_TOKEN", "TELEGRAM_WEBHOOK_SECRET"), ("telegram_bot_token", "telegram_webhook_secret")),
    ("redis", "Redis + arq worker", "Очередь поисков и фоновые задачи", ("REDIS_URL",), ("redis_url",)),
    ("sentry", "Sentry", "Ошибки бэкенда", ("SENTRY_DSN_API", "SENTRY_ENVIRONMENT"), ("sentry_dsn_api",)),
    ("stripe", "Stripe", "Биллинг (сейчас выключен: BILLING_ENFORCED=false)",
     ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_PRICE_ID_PRO", "STRIPE_PRICE_ID_AGENCY"),
     ("stripe_secret_key",)),
    ("hubspot", "HubSpot OAuth", "Выгрузка лидов в HubSpot (скрыто в интерфейсе)",
     ("HUBSPOT_OAUTH_CLIENT_ID", "HUBSPOT_OAUTH_CLIENT_SECRET", "HUBSPOT_OAUTH_REDIRECT_URI"), ("hubspot_oauth_client_id",)),
    ("pipedrive", "Pipedrive OAuth", "Выгрузка лидов в Pipedrive (скрыто в интерфейсе)",
     ("PIPEDRIVE_OAUTH_CLIENT_ID", "PIPEDRIVE_OAUTH_CLIENT_SECRET", "PIPEDRIVE_OAUTH_REDIRECT_URI"),
     ("pipedrive_oauth_client_id",)),
    ("notion", "Notion OAuth", "Двусторонняя синхронизация с Notion (скрыто в интерфейсе)",
     ("NOTION_OAUTH_CLIENT_ID", "NOTION_OAUTH_CLIENT_SECRET", "NOTION_OAUTH_REDIRECT_URI"), ("notion_oauth_client_id",)),
    ("sheets", "Google Sheets", "Выгрузка лидов в таблицу", ("GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON",),
     ("google_sheets_service_account_json",)),
    ("slack", "Slack webhook", "Общий канал о горячих лидах (один на платформу)", ("SLACK_WEBHOOK_URL",),
     ("slack_webhook_url",)),
)


def integrations() -> list[dict[str, Any]]:
    s = get_settings()
    out = []
    for key, name, purpose, env, fields in _INTEGRATIONS:
        configured = all(bool(getattr(s, f, None)) for f in fields)
        out.append(
            {"key": key, "name": name, "purpose": purpose, "configured": configured, "env": list(env)}
        )
    return out


def flags() -> dict[str, Any]:
    """Переключатели поведения платформы (значения не секретны)."""
    s = get_settings()
    return {
        "BILLING_ENFORCED": s.billing_enforced,
        "TOKENS_ENFORCED": s.tokens_enforced,
        "REQUIRE_EMAIL_VERIFICATION": s.require_email_verification,
        "DEMO_MODE": s.demo_active,
        "BATCH_SCORING_ENABLED": s.batch_scoring_enabled,
        "FALLBACK_SOURCES_ALWAYS_ON": s.fallback_sources_always_on,
        "TELEPHONY_PROVIDER": s.telephony_provider or None,
        "ANTHROPIC_MODEL": s.anthropic_model,
        "HENRY_MODEL": getattr(s, "henry_model", None),
        "LOG_LEVEL": s.log_level,
        "REGISTRATION_CLOSED": bool(s.registration_password),
    }


def limits() -> dict[str, Any]:
    from leadgen.core.services.account import tokens as _tokens
    from leadgen.core.services.outreach import send_quota
    from leadgen.core.services.search.cost_control import COST_PER_ENRICHED_LEAD_USD
    from leadgen.utils import rate_limit as rl

    s = get_settings()
    rate = {}
    for name in dir(rl):
        obj = getattr(rl, name)
        if name.endswith("_limiter") and hasattr(obj, "max_actions"):
            rate[name.removesuffix("_limiter")] = f"{obj.max_actions} / {int(obj.window_sec)} с"
    return {
        "max_results_per_query": s.max_results_per_query,
        "max_enrich_leads": s.max_enrich_leads,
        "enrich_concurrency": s.enrich_concurrency,
        "tokens_per_lead": _tokens.TOKENS_PER_LEAD,
        "tokens_per_decision_maker": _tokens.TOKENS_PER_DECISION_MAKER,
        "token_price_usd": float(COST_PER_ENRICHED_LEAD_USD),
        "personal_monthly_cost_cap_usd": float(s.personal_monthly_cost_cap_usd or 0),
        "email_warmup": f"{send_quota.WARMUP_START} писем в первый день, +{send_quota.WARMUP_STEP}/день, максимум {send_quota.WARMUP_MAX}",
        "session_days": s.auth_session_days,
        "rate_limits": rate,
    }


def jobs() -> list[dict[str, Any]]:
    """Фоновые задачи воркера с расписанием (UTC)."""
    try:
        from leadgen.queue.worker import WorkerSettings
    except Exception:  # noqa: BLE001 — нет arq в окружении
        return []

    def _fmt(v: Any) -> str:
        if v is None:
            return "*"
        vals = sorted(v) if isinstance(v, (set, frozenset, list, tuple)) else [v]
        if len(vals) > 4:
            step = vals[1] - vals[0]
            return f"каждые {step}" if all(b - a == step for a, b in zip(vals, vals[1:], strict=False)) else ",".join(map(str, vals))
        return ",".join(str(x) for x in vals)

    out = []
    for j in WorkerSettings.cron_jobs:
        doc = (j.coroutine.__doc__ or "").strip().splitlines()
        when = f"мин {_fmt(j.minute)} · час {_fmt(j.hour)}"
        if j.weekday is not None:
            when += f" · день недели {_fmt(j.weekday)}"
        if j.second is not None and j.minute is None:
            when = f"каждую минуту (сек {_fmt(j.second)})"
        out.append({"name": j.coroutine.__name__, "schedule": when, "purpose": doc[0] if doc else ""})
    for fn in WorkerSettings.functions:
        doc = (fn.__doc__ or "").strip().splitlines()
        out.append({"name": fn.__name__, "schedule": "по событию (очередь)", "purpose": doc[0] if doc else ""})
    return out


_egress: tuple[datetime, str | None] | None = None


async def egress_ip() -> str | None:
    """Внешний IP, с которого сервер ходит наружу (для белых списков)."""
    global _egress
    now = datetime.now(timezone.utc)
    if _egress is not None and (now - _egress[0]).total_seconds() < 3600:
        return _egress[1]
    ip = None
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get("https://api.ipify.org", params={"format": "json"})
            ip = resp.json().get("ip")
    except Exception:  # noqa: BLE001
        logger.info("egress ip lookup failed", exc_info=True)
    _egress = (now, ip)
    return ip


async def resolve(host: str | None) -> list[str]:
    """IP-адреса, на которые сейчас смотрит DNS-имя."""
    if not host:
        return []
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, 443, proto=socket.IPPROTO_TCP)
    except Exception:  # noqa: BLE001
        return []
    return sorted({i[4][0] for i in infos})


def runtime() -> dict[str, Any]:
    env = os.environ
    return {
        "commit": (env.get("RAILWAY_GIT_COMMIT_SHA") or "unknown")[:12],
        "branch": env.get("RAILWAY_GIT_BRANCH"),
        "environment": env.get("RAILWAY_ENVIRONMENT_NAME") or env.get("RAILWAY_ENVIRONMENT"),
        "service": env.get("RAILWAY_SERVICE_NAME"),
        "region": env.get("RAILWAY_REPLICA_REGION"),
        "replica": env.get("RAILWAY_REPLICA_ID"),
        "private_domain": env.get("RAILWAY_PRIVATE_DOMAIN"),
        "public_domain": env.get("RAILWAY_PUBLIC_DOMAIN"),
        "python": sys.version.split()[0],
        "platform": platform.platform(terse=True),
        "started_at": _STARTED_AT.isoformat(),
        "hosting": "Railway (API + worker), Vercel (сайт)",
    }


def host_of(url: str | None) -> str | None:
    return urlparse(url).hostname if url else None
