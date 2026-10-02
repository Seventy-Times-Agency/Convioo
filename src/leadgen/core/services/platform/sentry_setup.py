"""Initialise Sentry for the FastAPI process.

Idempotent and lazy — calling without ``SENTRY_DSN_API`` is a no-op,
so dev / CI runs with no DSN behave exactly as before. Both the API
process and the arq worker call ``configure_sentry()`` once at boot.

Why a wrapper instead of inline init:
- Keeps ``__main__.py`` tidy (one call, not 20 lines of SDK setup).
- Centralises the integration list — when we add Stripe / queue
  spans in future, only one file changes.
- Lets us silence the import error when ``sentry-sdk`` isn't on the
  Python path (it's an optional dep). Production deploys list it
  in pyproject; CI runs without a DSN and shouldn't break if the
  package is missing.
"""

from __future__ import annotations

import logging

from leadgen.config import get_settings

logger = logging.getLogger(__name__)


_CONFIGURED = False


def configure_sentry() -> None:
    """Initialise sentry-sdk if a DSN is configured.

    Safe to call from multiple entrypoints — the second call is a
    cheap no-op. Imports the SDK lazily so a missing package only
    becomes an error when the user actually wants Sentry on.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    settings = get_settings()
    dsn = (settings.sentry_dsn_api or "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.asyncio import AsyncioIntegration
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import (
            SqlalchemyIntegration,
        )
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:
        logger.warning(
            "Sentry DSN is set but sentry-sdk is not installed; "
            "skipping init. Add ``sentry-sdk`` to project deps."
        )
        return

    sentry_sdk.init(
        dsn=dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        # 0 = no profiling (we don't pay for that yet).
        profiles_sample_rate=0.0,
        # ``before_send`` would scrub tokens, but our utils.secrets
        # module already runs over user-facing strings; the SDK's
        # default scrubber catches the rest. Keep this hook free for
        # later need-based filtering.
        send_default_pii=False,
        integrations=[
            AsyncioIntegration(),
            FastApiIntegration(),
            StarletteIntegration(),
            SqlalchemyIntegration(),
        ],
    )
    _CONFIGURED = True
    logger.info(
        "sentry: initialised (env=%s, traces=%.2f)",
        settings.sentry_environment,
        settings.sentry_traces_sample_rate,
    )
