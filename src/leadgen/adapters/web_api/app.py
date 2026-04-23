"""FastAPI application factory for the web frontend.

Swaps in place of the old aiohttp ``/health`` + ``/metrics`` server.
Same port (``PORT`` env), same paths, plus the new ``/api/v1/*``
routes. Uvicorn runs this app alongside the Telegram bot polling
loop in the same asyncio event loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest
from sqlalchemy import select
from sqlalchemy import text as sa_text

from leadgen.adapters.web_api.auth import require_api_key
from leadgen.adapters.web_api.schemas import (
    HealthResponse,
    SearchCreate,
    SearchCreateResponse,
    SearchSummary,
)
from leadgen.config import get_settings
from leadgen.core.services import BillingService, default_broker
from leadgen.db.models import SearchQuery
from leadgen.db.session import _get_engine, session_factory
from leadgen.queue import enqueue_search, is_queue_enabled

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Leadgen API",
        version="0.2.0",
        docs_url="/docs",
        redoc_url=None,
    )

    cors = get_settings().web_cors_origins
    if cors:
        origins = [o.strip() for o in cors.split(",") if o.strip()]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
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
        """Create a SearchQuery row + optionally enqueue on arq.

        Uses the same BillingService the bot uses, so the web path and
        the Telegram path share one quota bucket and one unique-index
        guard against parallel in-flight searches.
        """
        async with session_factory() as session:
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

        queued_id = await enqueue_search(
            query.id,
            chat_id=None,
            user_profile={"language_code": body.language_code} if body.language_code else None,
        )
        return SearchCreateResponse(id=query.id, queued=bool(queued_id))

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
        response_model=SearchSummary,
        dependencies=[Depends(require_api_key)],
    )
    async def get_search(search_id: uuid.UUID) -> SearchSummary:
        async with session_factory() as session:
            query = await session.get(SearchQuery, search_id)
            if query is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="search not found"
                )
            return _to_summary(query)

    @app.get("/api/v1/queue/status", include_in_schema=False)
    async def queue_status() -> dict[str, bool]:
        return {"queue_enabled": is_queue_enabled()}

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
        if not expected:
            raise HTTPException(status_code=503, detail="web api key not configured")
        if api_key != expected:
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


def _to_summary(query: SearchQuery) -> SearchSummary:
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
    )
