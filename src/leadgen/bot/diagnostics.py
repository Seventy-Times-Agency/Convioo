"""On-demand integration health checks.

Exposed via the ``/diag`` command so the user can answer, in chat, the
question "does the bot actually have access to Google Maps / websites /
Anthropic / Telegram / its database?" without squinting at Railway logs.

Each check returns a short human-readable line with a status emoji. The
checks are independent and run sequentially so one slow or failing
endpoint doesn't block the others.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx
from aiogram import Bot
from sqlalchemy import text

from leadgen.collectors.google_places import GooglePlacesCollector, GooglePlacesError
from leadgen.collectors.website import WebsiteCollector
from leadgen.config import get_settings
from leadgen.db.session import _get_engine

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    took_ms: int


def _mask(value: str | None, show: int = 4) -> str:
    if not value:
        return "—"
    if len(value) <= show * 2:
        return "•" * len(value)
    return f"{value[:show]}…{value[-show:]} ({len(value)} симв.)"


async def check_env() -> CheckResult:
    start = time.monotonic()
    try:
        s = get_settings()
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            name="env",
            ok=False,
            detail=f"Settings load failed: {exc}",
            took_ms=int((time.monotonic() - start) * 1000),
        )
    parts = [
        f"BOT_TOKEN={_mask(s.bot_token)}",
        f"DATABASE_URL={_mask(s.database_url)}",
        f"GOOGLE_PLACES_API_KEY={_mask(s.google_places_api_key) or '—'}",
        f"ANTHROPIC_API_KEY={_mask(s.anthropic_api_key) or '—'}",
    ]
    missing = []
    if not s.bot_token:
        missing.append("BOT_TOKEN")
    if not s.database_url:
        missing.append("DATABASE_URL")
    if not s.google_places_api_key:
        missing.append("GOOGLE_PLACES_API_KEY")
    ok = not missing
    detail = "\n".join(parts)
    if missing:
        detail += f"\n⚠️ Отсутствуют: {', '.join(missing)}"
    return CheckResult(
        name="env",
        ok=ok,
        detail=detail,
        took_ms=int((time.monotonic() - start) * 1000),
    )


async def check_database() -> CheckResult:
    start = time.monotonic()
    try:
        engine = _get_engine()
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            row = result.scalar()
        detail = f"SELECT 1 = {row}"
        ok = row == 1
    except Exception as exc:  # noqa: BLE001
        ok = False
        detail = f"{type(exc).__name__}: {str(exc)[:200]}"
    return CheckResult(
        name="database",
        ok=ok,
        detail=detail,
        took_ms=int((time.monotonic() - start) * 1000),
    )


async def check_telegram(bot: Bot) -> CheckResult:
    start = time.monotonic()
    try:
        me = await bot.get_me()
        detail = f"@{me.username} (id={me.id})"
        ok = True
    except Exception as exc:  # noqa: BLE001
        ok = False
        detail = f"{type(exc).__name__}: {str(exc)[:200]}"
    return CheckResult(
        name="telegram",
        ok=ok,
        detail=detail,
        took_ms=int((time.monotonic() - start) * 1000),
    )


async def check_google_places() -> CheckResult:
    """Do a real small Google Places search and report count + status code."""
    start = time.monotonic()
    try:
        collector = GooglePlacesCollector(page_size=5, max_pages=1, timeout=15.0)
        leads = await collector.search(niche="кофейня", region="Москва")
        ok = len(leads) > 0
        detail = f"поисковый ответ: {len(leads)} компаний для «кофейня Москва»"
        if not ok:
            detail += " (0 результатов — возможно API не включён или квота исчерпана)"
    except GooglePlacesError as exc:
        ok = False
        detail = f"GooglePlacesError: {str(exc)[:250]}"
    except Exception as exc:  # noqa: BLE001
        ok = False
        detail = f"{type(exc).__name__}: {str(exc)[:250]}"
    return CheckResult(
        name="google_places",
        ok=ok,
        detail=detail,
        took_ms=int((time.monotonic() - start) * 1000),
    )


async def check_website_fetch() -> CheckResult:
    """Fetch a known-good URL to verify outbound HTTP works from the container."""
    start = time.monotonic()
    try:
        collector = WebsiteCollector(timeout=10.0)
        info = await collector.fetch("https://example.com")
        ok = info.ok and info.status_code == 200
        detail = (
            f"GET https://example.com → {info.status_code}, "
            f"title={info.title!r}"
        )
        if info.error:
            detail += f", error={info.error}"
    except Exception as exc:  # noqa: BLE001
        ok = False
        detail = f"{type(exc).__name__}: {str(exc)[:250]}"
    return CheckResult(
        name="website_fetch",
        ok=ok,
        detail=detail,
        took_ms=int((time.monotonic() - start) * 1000),
    )


async def check_anthropic() -> CheckResult:
    """Small ping to the Anthropic API — send a 1-token reply to confirm auth."""
    start = time.monotonic()
    settings = get_settings()
    if not settings.anthropic_api_key:
        return CheckResult(
            name="anthropic",
            ok=False,
            detail="ANTHROPIC_API_KEY не задан — AI-оценка работает в fallback-режиме (эвристика)",
            took_ms=int((time.monotonic() - start) * 1000),
        )
    try:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        msg = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=10,
            messages=[{"role": "user", "content": "Ответь одним словом: пинг"}],
        )
        text_out = "".join(
            getattr(block, "text", "") for block in msg.content
        ).strip()[:60]
        ok = True
        detail = f"{settings.anthropic_model}: ответ {text_out!r}"
    except Exception as exc:  # noqa: BLE001
        ok = False
        detail = f"{type(exc).__name__}: {str(exc)[:250]}"
    return CheckResult(
        name="anthropic",
        ok=ok,
        detail=detail,
        took_ms=int((time.monotonic() - start) * 1000),
    )


async def check_outbound_internet() -> CheckResult:
    """Raw httpx GET to a stable endpoint — isolates container network from API-specific issues."""
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get("https://www.google.com/generate_204")
        ok = resp.status_code in (200, 204)
        detail = f"GET google.com/generate_204 → {resp.status_code}"
    except Exception as exc:  # noqa: BLE001
        ok = False
        detail = f"{type(exc).__name__}: {str(exc)[:250]}"
    return CheckResult(
        name="outbound_internet",
        ok=ok,
        detail=detail,
        took_ms=int((time.monotonic() - start) * 1000),
    )


async def run_all_checks(bot: Bot) -> list[CheckResult]:
    """Run all diagnostics sequentially — reveals which layer is broken."""
    return [
        await check_env(),
        await check_database(),
        await check_telegram(bot),
        await check_outbound_internet(),
        await check_google_places(),
        await check_website_fetch(),
        await check_anthropic(),
    ]


def format_results(results: list[CheckResult]) -> str:
    """Render check results as a single Telegram-safe HTML report."""
    lines: list[str] = ["🔧 <b>Диагностика бота</b>\n"]
    for r in results:
        icon = "✅" if r.ok else "❌"
        lines.append(f"{icon} <b>{r.name}</b> ({r.took_ms} мс)")
        lines.append(f"<code>{_escape(r.detail)}</code>")
        lines.append("")
    failed = [r for r in results if not r.ok]
    if failed:
        lines.append(
            f"Провалилось: <b>{len(failed)}/{len(results)}</b>. "
            f"Посмотри детали выше — они подскажут какую переменную "
            f"добавить в Railway или какой API включить."
        )
    else:
        lines.append(
            f"✅ <b>Все {len(results)} проверок ок</b> — бот может искать и анализировать."
        )
    return "\n".join(lines)


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
