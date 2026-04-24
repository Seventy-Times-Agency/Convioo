"""FastAPI application factory for the web frontend.

Swaps in place of the old aiohttp ``/health`` + ``/metrics`` server.
Same port (``PORT`` env), same paths, plus the new ``/api/v1/*``
routes. Uvicorn runs this app alongside the Telegram bot polling
loop in the same asyncio event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest
from sqlalchemy import select, update
from sqlalchemy import text as sa_text

from leadgen.adapters.web_api.auth import is_open_mode, require_api_key
from leadgen.adapters.web_api.schemas import (
    HealthResponse,
    LeadOut,
    SearchCreate,
    SearchCreateResponse,
    SearchDetail,
    SearchSummary,
)
from leadgen.config import get_settings
from leadgen.core.services import (
    BillingService,
    BrokerProgressSink,
    NullSink,
    default_broker,
)
from leadgen.db.models import Lead, SearchQuery, User
from leadgen.db.session import _get_engine, session_factory
from leadgen.export.excel import build_excel
from leadgen.queue import enqueue_search, is_queue_enabled

logger = logging.getLogger(__name__)


# Hard wall-clock cap on a single web-initiated search. Mirrors the
# Telegram path's SEARCH_TIMEOUT_SEC so behaviour is consistent.
WEB_SEARCH_TIMEOUT_SEC = 10 * 60

# Bag of background tasks we keep a reference to — without this they'd
# get garbage-collected mid-run because asyncio only weak-refs tasks.
_background_searches: set[asyncio.Task[None]] = set()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Leadgen API",
        version="0.3.0",
        docs_url="/docs",
        redoc_url=None,
    )

    cors = get_settings().web_cors_origins
    # Vercel gives every deploy a unique *.vercel.app URL (production +
    # every preview). Matching on a regex covers them all without us
    # chasing deploy URLs through env vars. Exact origins from
    # WEB_CORS_ORIGINS stack on top for custom domains.
    origins = [o.strip() for o in cors.split(",") if o.strip()] if cors else []
    # Always include localhost during dev so `next dev` can hit the API.
    dev_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    all_origins = list({*origins, *dev_origins})
    app.add_middleware(
        CORSMiddleware,
        allow_origins=all_origins,
        allow_origin_regex=r"https://.*\.vercel\.app$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", response_class=PlainTextResponse, include_in_schema=False)
    async def root() -> str:
        return "leadgen alive. /health, /metrics and /api/v1/* available.\n"

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        db_ok = False
        try:
            engine = _get_engine()
            async with engine.connect() as conn:
                result = await conn.execute(sa_text("SELECT 1"))
                db_ok = result.scalar() == 1
        except Exception:  # noqa: BLE001
            logger.exception("health: db check failed")
        return HealthResponse(
            status="healthy" if db_ok else "unhealthy",
            db=db_ok,
            commit=(os.environ.get("RAILWAY_GIT_COMMIT_SHA", "unknown"))[:12],
        )

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        payload = generate_latest(REGISTRY)
        return Response(
            content=payload,
            media_type=CONTENT_TYPE_LATEST.split(";")[0],
        )

    # ── /api/v1/searches ───────────────────────────────────────────────

    @app.post(
        "/api/v1/searches",
        response_model=SearchCreateResponse,
        dependencies=[Depends(require_api_key)],
    )
    async def create_search(body: SearchCreate) -> SearchCreateResponse:
        """Create a SearchQuery row, consume quota, kick off the pipeline.

        Auto-creates the User row on first use so a fresh agency seat can
        run a search without us seeding their account out of band. Uses
        the same ``BillingService`` the bot uses, so both surfaces share
        one quota bucket and the same partial unique index against
        parallel in-flight searches.

        When ``REDIS_URL`` is configured the search is pushed to arq;
        otherwise it runs in-process via ``asyncio.create_task`` on this
        same uvicorn worker. Either way the response returns immediately
        with the search id so the client can subscribe to ``/progress``.
        """
        async with session_factory() as session:
            await _ensure_user(
                session,
                user_id=body.user_id,
                language_code=body.language_code,
                display_name=body.display_name,
                profession=body.profession,
            )

            billing = BillingService(session)
            quota = await billing.try_consume(body.user_id)
            if not quota.allowed:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail=(
                        f"Quota exhausted ({quota.queries_used}/{quota.queries_limit})."
                    ),
                )
            query = SearchQuery(
                user_id=body.user_id, niche=body.niche, region=body.region
            )
            session.add(query)
            try:
                await session.commit()
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Another search is already running for this user, "
                        "or the row couldn't be created."
                    ),
                ) from exc
            await session.refresh(query)

        # Build a profile snapshot so the background task doesn't depend
        # on a session that's already closed.
        user_profile = {
            "language_code": body.language_code,
            "display_name": body.display_name,
            "profession": body.profession,
        }

        queued_id = await enqueue_search(
            query.id,
            chat_id=None,
            user_profile=user_profile,
        )

        if queued_id is None:
            # Redis isn't configured (or enqueue failed). Run the
            # pipeline inline so the user actually gets results — without
            # this fallback the row sat as ``pending`` forever and the
            # SSE stream timed out, which is what made the web UI feel
            # broken in the first place.
            task = asyncio.create_task(
                _run_web_search(query.id, user_profile),
                name=f"leadgen-web-search-{query.id}",
            )
            _background_searches.add(task)
            task.add_done_callback(_background_searches.discard)

        return SearchCreateResponse(id=query.id, queued=bool(queued_id), running=True)

    @app.get(
        "/api/v1/searches",
        response_model=list[SearchSummary],
        dependencies=[Depends(require_api_key)],
    )
    async def list_searches(user_id: int, limit: int = 20) -> list[SearchSummary]:
        limit = max(1, min(limit, 100))
        async with session_factory() as session:
            result = await session.execute(
                select(SearchQuery)
                .where(SearchQuery.user_id == user_id)
                .order_by(SearchQuery.created_at.desc())
                .limit(limit)
            )
            return [_to_summary(row) for row in result.scalars().all()]

    @app.get(
        "/api/v1/searches/{search_id}",
        response_model=SearchDetail,
        dependencies=[Depends(require_api_key)],
    )
    async def get_search(search_id: uuid.UUID) -> SearchDetail:
        async with session_factory() as session:
            query = await session.get(SearchQuery, search_id)
            if query is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="search not found"
                )
            leads_result = await session.execute(
                select(Lead)
                .where(Lead.query_id == search_id)
                .order_by(
                    Lead.score_ai.desc().nullslast(),
                    Lead.rating.desc().nullslast(),
                )
            )
            leads = [_to_lead_out(lead) for lead in leads_result.scalars().all()]
        summary = _to_summary(query)
        stats = None
        if query.analysis_summary:
            stats = query.analysis_summary.get("stats")
        return SearchDetail(
            **summary.model_dump(),
            stats=stats,
            leads=leads,
        )

    @app.get(
        "/api/v1/searches/{search_id}/leads",
        response_model=list[LeadOut],
        dependencies=[Depends(require_api_key)],
    )
    async def get_search_leads(
        search_id: uuid.UUID, limit: int = 200
    ) -> list[LeadOut]:
        limit = max(1, min(limit, 500))
        async with session_factory() as session:
            query = await session.get(SearchQuery, search_id)
            if query is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="search not found"
                )
            result = await session.execute(
                select(Lead)
                .where(Lead.query_id == search_id)
                .order_by(
                    Lead.score_ai.desc().nullslast(),
                    Lead.rating.desc().nullslast(),
                )
                .limit(limit)
            )
            return [_to_lead_out(lead) for lead in result.scalars().all()]

    @app.get(
        "/api/v1/searches/{search_id}/excel",
        dependencies=[Depends(require_api_key)],
    )
    async def get_search_excel(search_id: uuid.UUID) -> Response:
        """Render the lead table as XLSX on demand.

        Cheaper than persisting blob bytes per search and keeps the
        column layout/styling in one place (``export/excel.py``).
        """
        async with session_factory() as session:
            query = await session.get(SearchQuery, search_id)
            if query is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="search not found"
                )
            result = await session.execute(
                select(Lead)
                .where(Lead.query_id == search_id)
                .order_by(
                    Lead.score_ai.desc().nullslast(),
                    Lead.rating.desc().nullslast(),
                )
            )
            leads = list(result.scalars().all())
        if not leads:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="no leads available yet for this search",
            )
        payload = build_excel(leads)
        filename = _safe_filename(f"leads_{query.niche}_{query.region}.xlsx")
        return Response(
            content=payload,
            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/v1/queue/status", include_in_schema=False)
    async def queue_status() -> dict[str, bool]:
        return {"queue_enabled": is_queue_enabled()}

    @app.get("/api/v1/config", include_in_schema=False)
    async def api_config() -> dict[str, bool]:
        """Public config so the frontend knows whether a key is required."""
        return {"open_mode": is_open_mode()}

    # ── SSE: live search progress ───────────────────────────────────────

    @app.get("/api/v1/searches/{search_id}/progress")
    async def search_progress(
        search_id: uuid.UUID,
        api_key: str | None = Query(default=None, alias="api_key"),
    ) -> StreamingResponse:
        """Server-Sent Events stream of progress beats for a running search.

        Auth is via ``?api_key=...`` in the query string rather than a
        header — ``EventSource`` in browsers can't set custom headers,
        so this is the pragmatic way to gate the stream. The key is
        never logged (FastAPI's default access log is off) and each
        connection is short-lived.
        """
        expected = get_settings().web_api_key
        if expected and api_key != expected:
            # When a key is configured we require it on SSE too. Empty
            # ``WEB_API_KEY`` means open mode (see ``auth.py``).
            raise HTTPException(status_code=401, detail="invalid api_key")

        async def event_stream() -> asyncio.AsyncIterator[bytes]:
            # Reconnect-friendly: client will retry after 5s if stream drops.
            yield b"retry: 5000\n\n"
            async for event in default_broker.subscribe(search_id):
                payload = json.dumps({"kind": event.kind, **event.data})
                yield f"event: {event.kind}\ndata: {payload}\n\n".encode()
            # Sentinel: tells EventSource we're done, no reconnect needed.
            yield b"event: done\ndata: {}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    return app


# ── Helpers ──────────────────────────────────────────────────────────────


async def _ensure_user(
    session,  # type: ignore[no-untyped-def]
    *,
    user_id: int,
    language_code: str | None,
    display_name: str | None,
    profession: str | None,
) -> None:
    """Insert the user row if it doesn't exist, otherwise patch the profile.

    We can't take the bot's onboarding flow for granted on the web side.
    The first POST /searches from a browser session needs a user row so
    BillingService and the FK on SearchQuery have something to point to.
    """
    user = await session.get(User, user_id)
    if user is None:
        session.add(
            User(
                id=user_id,
                first_name=display_name,
                display_name=display_name,
                language_code=language_code,
                profession=profession,
                onboarded_at=datetime.now(timezone.utc) if profession else None,
            )
        )
        await session.commit()
        return

    patch: dict[str, object] = {}
    if display_name and not user.display_name:
        patch["display_name"] = display_name
    if profession and not user.profession:
        patch["profession"] = profession
    if language_code and not user.language_code:
        patch["language_code"] = language_code
    if patch:
        await session.execute(update(User).where(User.id == user_id).values(**patch))
        await session.commit()


async def _run_web_search(
    query_id: uuid.UUID, user_profile: dict[str, object]
) -> None:
    """In-process runner for web-initiated searches.

    Mirrors ``run_search`` (the Telegram wrapper) but builds web sinks
    instead of aiogram ones, and skips the per-search lead cleanup so
    the dashboard can read the enriched rows back out of the DB. The
    Telegram path drops them after delivering Excel; the web path
    treats the DB as the delivery sink.
    """
    # Local import keeps the web adapter's module graph independent of
    # the heavier pipeline import chain at app startup.
    from leadgen.pipeline.search import run_search_with_sinks

    progress = BrokerProgressSink(default_broker, query_id)
    try:
        await asyncio.wait_for(
            run_search_with_sinks(
                query_id,
                progress=progress,
                delivery=NullSink(),
                user_profile=user_profile,
            ),
            timeout=WEB_SEARCH_TIMEOUT_SEC,
        )
    except TimeoutError:
        logger.error(
            "web search %s timed out after %ds", query_id, WEB_SEARCH_TIMEOUT_SEC
        )
        async with session_factory() as session:
            await session.execute(
                update(SearchQuery)
                .where(SearchQuery.id == query_id)
                .values(
                    status="failed",
                    error=f"timeout after {WEB_SEARCH_TIMEOUT_SEC}s",
                )
            )
            await session.commit()
        with contextlib.suppress(Exception):
            await progress.finish(
                "Search took too long and was aborted. Try again in a minute."
            )
    except Exception:  # noqa: BLE001
        logger.exception("web search %s failed", query_id)
        with contextlib.suppress(Exception):
            await progress.finish(
                "Search failed unexpectedly. Check /diag from the bot."
            )
    finally:
        # Always close the broker channel so any stuck SSE subscribers
        # get the terminal sentinel and disconnect cleanly.
        with contextlib.suppress(Exception):
            await default_broker.close(query_id)


def _to_summary(query: SearchQuery) -> SearchSummary:
    insights = None
    if query.analysis_summary:
        insights = query.analysis_summary.get("insights")
    return SearchSummary(
        id=query.id,
        user_id=query.user_id,
        niche=query.niche,
        region=query.region,
        status=query.status,
        created_at=query.created_at,
        finished_at=query.finished_at,
        leads_count=query.leads_count,
        avg_score=query.avg_score,
        hot_leads_count=query.hot_leads_count,
        error=query.error,
        insights=insights,
    )


def _to_lead_out(lead: Lead) -> LeadOut:
    return LeadOut(
        id=lead.id,
        name=lead.name,
        website=lead.website,
        phone=lead.phone,
        address=lead.address,
        category=lead.category,
        rating=lead.rating,
        reviews_count=lead.reviews_count,
        latitude=lead.latitude,
        longitude=lead.longitude,
        enriched=lead.enriched,
        score_ai=lead.score_ai,
        tags=lead.tags,
        summary=lead.summary,
        advice=lead.advice,
        strengths=lead.strengths,
        weaknesses=lead.weaknesses,
        red_flags=lead.red_flags,
        social_links=lead.social_links,
        reviews_summary=lead.reviews_summary,
    )


def _safe_filename(name: str) -> str:
    allowed = "-_.() "
    cleaned = "".join(c if c.isalnum() or c in allowed else "_" for c in name)
    return cleaned.replace(" ", "_")
