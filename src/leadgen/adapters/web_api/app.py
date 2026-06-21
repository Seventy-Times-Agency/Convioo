"""FastAPI application factory for the web frontend.

Listens on ``PORT`` (default 8080), serves ``/health``, ``/metrics``
and ``/api/v1/*``. This is the only delivery surface the product has
since the Telegram bot was removed.

Auth note: real email + password auth is in place. ``WEB_API_KEY``
still gates the SSE progress stream (since that's the only endpoint
where the client can't retry).
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest
from sqlalchemy import update

from leadgen.adapters.web_api.auth import (
    get_current_user,
)
from leadgen.adapters.web_api.csrf import CsrfMiddleware
from leadgen.adapters.web_api.schemas import (
    HealthResponse,
)
from leadgen.config import assert_production_secrets, get_settings
from leadgen.db.models import (
    SavedSearch,
    User,
)
from leadgen.db.session import session_factory
from leadgen.queue import enqueue_search
from leadgen.utils import spawn

logger = logging.getLogger(__name__)


# Demo avatars for team page until seat management is wired up.
_DEMO_TEAM_COLORS = [
    "#3D5AFE",
    "#F59E0B",
    "#16A34A",
    "#EC4899",
    "#8B5CF6",
    "#06B6D4",
]


# Legacy hard-coded lead-status keys. Personal-mode searches still
# use these directly; team-mode searches resolve against the team's
# ``lead_statuses`` palette (which is seeded with the same five keys
# at team creation, so existing rows remain valid).
LEGACY_LEAD_STATUS_KEYS: frozenset[str] = frozenset(
    {"new", "contacted", "replied", "won", "archived"}
)


# Default lead-status palette lives in ``routes/_helpers.py`` (the
# single source of truth, localised per creating user). The aliases
# below keep the legacy ``app.py`` import path working for callers
# and tests that still reference the old private names.
from leadgen.adapters.web_api.routes._helpers import (  # noqa: E402, F401, I001
    _DEFAULT_LEAD_STATUSES,
    seed_default_lead_statuses as _seed_default_lead_statuses,
)


async def _bootstrap_admins() -> None:
    # Promote every email listed in BOOTSTRAP_ADMIN_EMAILS (comma-separated)
    # to platform admin on startup. Missing users are skipped silently — the
    # next boot after they register will pick them up. Lets non-technical
    # operators flip the flag from Railway's Variables UI without SQL.
    raw = os.environ.get("BOOTSTRAP_ADMIN_EMAILS", "").strip()
    if not raw:
        return
    emails = [e.strip().lower() for e in raw.split(",") if e.strip()]
    if not emails:
        return
    try:
        from leadgen.db.models import User
        from leadgen.db.session import get_session

        async with get_session() as session:
            result = await session.execute(
                update(User)
                .where(User.email.in_(emails), User.is_admin.is_(False))
                .values(is_admin=True)
                .returning(User.email)
            )
            promoted = [row[0] for row in result.all()]
            await session.commit()
        if promoted:
            logging.getLogger(__name__).info(
                "bootstrap_admin: promoted %s", ", ".join(promoted)
            )
    except Exception:
        logging.getLogger(__name__).exception("bootstrap_admin failed")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    await _bootstrap_admins()
    # In-process saved-search scheduler. Runs only when Redis is
    # absent — production deploys with arq run a separate worker that
    # does the same scan. Safe in dev because each scan completes in
    # a few ms when no rows are due. Toggle with SAVED_SEARCH_SCHEDULER=0.
    scheduler_task: asyncio.Task[None] | None = None
    if (
        not get_settings().redis_url
        and os.environ.get("SAVED_SEARCH_SCHEDULER", "1") == "1"
    ):
        scheduler_task = asyncio.create_task(
            _saved_search_scheduler_loop(),
            name="convioo-saved-search-scheduler",
        )
    try:
        yield
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await scheduler_task


def create_app() -> FastAPI:
    # Fail fast on Railway when the security-critical secrets are
    # missing — better a crashed deploy than sessions signed with an
    # empty secret or OAuth tokens that reset on every restart.
    # No-ops outside Railway (local dev, pytest).
    assert_production_secrets()

    app = FastAPI(
        title="Convioo API",
        version="0.3.0",
        docs_url="/docs",
        redoc_url=None,
        lifespan=_lifespan,
    )

    cors = get_settings().web_cors_origins
    if cors:
        origins = [o.strip() for o in cors.split(",") if o.strip()]
        if any(o == "*" for o in origins):
            raise RuntimeError(
                "WEB_CORS_ORIGINS contains '*' which is incompatible "
                "with allow_credentials=True. Set an explicit allowlist."
            )
        # CsrfMiddleware sits inside CORSMiddleware so it runs *after*
        # the preflight OPTIONS handshake — preflights stay 200.
        app.add_middleware(CsrfMiddleware, allowed_origins=origins)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        response = await call_next(request)
        # The API only serves JSON / SSE / file downloads, no HTML. A
        # strict default-src 'none' policy means even an accidental
        # HTML response can't pull in third-party scripts / frames.
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
        return response

    @app.get("/", response_class=PlainTextResponse, include_in_schema=False)
    async def root() -> str:
        return "convioo alive. /health, /metrics and /api/v1/* available.\n"

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        from leadgen.core.services.health_probes import probes_for_health

        probes = await probes_for_health()
        db_ok = bool(probes["db"])
        # Redis is optional. If REDIS_URL is unset the bot/web path
        # works without arq, so don't fail the overall status on it.
        # If REDIS_URL is set and the ping failed, surface unhealthy.
        redis_state = probes["redis"]
        redis_down = redis_state is False
        return HealthResponse(
            status="healthy" if db_ok and not redis_down else "unhealthy",
            db=db_ok,
            redis=redis_state,
            queue_depth=probes["queue_depth"],
            commit=(os.environ.get("RAILWAY_GIT_COMMIT_SHA", "unknown"))[:12],
        )

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        payload = generate_latest(REGISTRY)
        return Response(
            content=payload,
            media_type=CONTENT_TYPE_LATEST.split(";")[0],
        )

    # /api/v1/auth/* and /api/v1/api-keys/* moved to routes/auth.py
    # /api/v1/webhooks moved to routes/webhooks.py


    # /api/v1/users/me/* moved to routes/users.py

    # /api/v1/users/me/icp-profile moved to routes/users.py (already there)

    # /api/v1/users/me PATCH moved to routes/users.py

    # /api/v1/teams/* moved to routes/teams.py

    # /api/v1/search/consult, /api/v1/assistant/*, decision-makers, import-csv, suggest-niches moved to routes/assistant.py

    # /api/v1/searches/* moved to routes/search.py

    # /api/v1/leads/*, /api/v1/saved-searches/*, /api/v1/tasks/*
    # moved to routes/leads.py

    # /api/v1/teams/{team_id}/members-summary, /analytics, /statuses
    # moved to routes/teams.py

    # /api/v1/stats, /queue/status, /niches, /cities
    # moved to routes/misc.py

    # /api/v1/searches/{search_id}/progress (SSE) moved to routes/search.py


    # ── Legacy /users/{user_id}/* path redirects ───────────────────────
    #
    # Cookie sessions know who the caller is, so the user_id path
    # parameter is now redundant. New callers MUST use /users/me/*;
    # old clients (older SPA bundles, third-party integrations) get a
    # 308 redirect to the canonical path. The 403 on user_id mismatch
    # also closes the historical IDOR where a path id was trusted
    # without comparing it to the session user.
    legacy_user_suffixes: list[tuple[str, list[str]]] = [
        ("", ["GET", "PATCH", "DELETE"]),
        ("/change-email", ["POST"]),
        ("/change-password", ["POST"]),
        ("/audit-log", ["GET"]),
        ("/export", ["GET"]),
        ("/assistant-memory", ["GET", "DELETE"]),
        ("/weekly-checkin", ["GET"]),
        ("/suggest-niches", ["POST"]),
        ("/tasks", ["GET"]),
    ]

    def _make_legacy_redirect(suffix: str):
        async def _redirect(
            user_id: int,
            request: Request,
            current_user: User = Depends(get_current_user),
        ) -> Response:
            if user_id != current_user.id:
                raise HTTPException(status_code=403, detail="forbidden")
            qs = ("?" + request.url.query) if request.url.query else ""
            return RedirectResponse(
                url=f"/api/v1/users/me{suffix}{qs}", status_code=308
            )

        return _redirect

    # Per-domain APIRouter modules carved out of this monolith. Each
    # one is self-contained (uses module-level dependencies, doesn't
    # capture create_app() locals). Adding a new domain = drop a file
    # in routes/ and one include_router line here.
    from leadgen.adapters.web_api.routes import admin as _admin
    from leadgen.adapters.web_api.routes import assistant as _assistant
    from leadgen.adapters.web_api.routes import audit as _audit
    from leadgen.adapters.web_api.routes import auth as _auth
    from leadgen.adapters.web_api.routes import billing as _billing
    from leadgen.adapters.web_api.routes import (
        deliverability as _deliverability,
    )
    from leadgen.adapters.web_api.routes import inbox as _inbox
    from leadgen.adapters.web_api.routes import integrations as _integrations
    from leadgen.adapters.web_api.routes import leads as _leads
    from leadgen.adapters.web_api.routes import misc as _misc
    from leadgen.adapters.web_api.routes import (
        notifications as _notifications,
    )
    from leadgen.adapters.web_api.routes import reports as _reports
    from leadgen.adapters.web_api.routes import search as _search
    from leadgen.adapters.web_api.routes import segments as _segments
    from leadgen.adapters.web_api.routes import sequences as _sequences
    from leadgen.adapters.web_api.routes import tags as _tags
    from leadgen.adapters.web_api.routes import teams as _teams
    from leadgen.adapters.web_api.routes import templates as _templates
    from leadgen.adapters.web_api.routes import users as _users
    from leadgen.adapters.web_api.routes import webhooks as _webhooks

    # IMPORTANT: include the routers FIRST so the literal /users/me
    # routes win over the legacy /users/{user_id} catch-all below —
    # otherwise FastAPI tries to parse "me" as an int and the SPA's
    # GET /api/v1/users/me dies with 422 ("Input should be a valid
    # integer, unable to parse string as an integer").
    app.include_router(_admin.router)
    app.include_router(_audit.router)
    app.include_router(_assistant.router)
    app.include_router(_auth.router)
    app.include_router(_billing.router)
    app.include_router(_deliverability.router)
    app.include_router(_inbox.router)
    app.include_router(_integrations.router)
    app.include_router(_leads.router)
    app.include_router(_misc.router)
    app.include_router(_notifications.router)
    app.include_router(_reports.router)
    app.include_router(_search.router)
    app.include_router(_segments.router)
    app.include_router(_sequences.router)
    app.include_router(_tags.router)
    app.include_router(_teams.router)
    app.include_router(_templates.router)
    app.include_router(_users.router)
    app.include_router(_webhooks.router)

    for suffix, methods in legacy_user_suffixes:
        app.add_api_route(
            f"/api/v1/users/{{user_id}}{suffix}",
            _make_legacy_redirect(suffix),
            methods=methods,
            deprecated=True,
            include_in_schema=False,
        )

    return app


# when Redis isn't available. 60s lines up with the `daily` recurrence
# resolution, which is the finest grain we expose in the UI.
_SCHEDULER_TICK_SEC = 60


async def _saved_search_scheduler_loop() -> None:
    """Background task: fire due saved searches every ~60 seconds.

    Intentionally does *no* error propagation — the task is
    long-lived and any per-row failure is logged inside
    ``dispatch_due``. A persistent crash here would silence further
    scheduling, so we wrap the whole loop and continue.
    """
    from leadgen.core.services.saved_searches import (
        build_search_query,
        dispatch_due,
    )

    async def _run_one(saved: SavedSearch, session) -> uuid.UUID | None:
        new_query = build_search_query(saved)
        session.add(new_query)
        await session.commit()
        # Mirror the per-search profile lookup used by POST /searches —
        # cheap and lets Henry's tone match the owner.
        user = await session.get(User, saved.user_id)
        profile = (
            {
                "display_name": user.display_name or user.first_name,
                "language_code": user.language_code,
            }
            if user is not None
            else None
        )
        queued = await enqueue_search(
            new_query.id, chat_id=None, user_profile=profile
        )
        if not queued:
            from leadgen.adapters.web_api.routes._helpers import (
                run_web_search_inline as _run_web_search_inline,
            )

            spawn(
                _run_web_search_inline(new_query.id, profile),
                name=f"convioo-saved-{new_query.id}",
            )
        return new_query.id

    while True:
        try:
            async with session_factory() as session:
                count = await dispatch_due(session, run_search=_run_one)
                if count:
                    logger.info(
                        "saved-search scheduler: dispatched %d searches",
                        count,
                    )
        except Exception:  # noqa: BLE001
            logger.exception("saved-search scheduler tick crashed")
        await asyncio.sleep(_SCHEDULER_TICK_SEC)


