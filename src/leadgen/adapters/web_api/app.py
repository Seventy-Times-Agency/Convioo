"""FastAPI application factory for the web frontend.

Swaps in place of the old aiohttp ``/health`` + ``/metrics`` server.
Same port (``PORT`` env), same paths, plus the new ``/api/v1/*``
routes. Uvicorn runs this app alongside the Telegram bot polling
loop in the same asyncio event loop.

Auth note: the public demo runs **without** an API key gate on
read/write endpoints. ``WEB_API_KEY`` still gates the SSE progress
stream (since that's the only endpoint where the client can't
retry). Re-introduce ``require_api_key`` on the REST handlers once
real user auth lands.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest
from sqlalchemy import func, select, update
from sqlalchemy import text as sa_text
from sqlalchemy.exc import IntegrityError

from leadgen.adapters.web_api.schemas import (
    WEB_DEMO_USER_ID,
    AuthUser,
    DashboardStats,
    HealthResponse,
    LeadListResponse,
    LeadResponse,
    LeadUpdate,
    LoginRequest,
    RegisterRequest,
    SearchCreate,
    SearchCreateResponse,
    SearchSummary,
    TeamMemberResponse,
    UserProfile,
    UserProfileUpdate,
)
from leadgen.analysis.ai_analyzer import AIAnalyzer
from leadgen.adapters.web_api.sinks import WebDeliverySink
from leadgen.config import get_settings
from leadgen.core.services import BillingService, default_broker
from leadgen.core.services.progress_broker import BrokerProgressSink
from leadgen.db.models import Lead, SearchQuery, Team, TeamMembership, User
from leadgen.db.session import _get_engine, session_factory
from leadgen.pipeline.search import run_search_with_sinks
from leadgen.queue import enqueue_search, is_queue_enabled

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


def create_app() -> FastAPI:
    app = FastAPI(
        title="Leadgen API",
        version="0.3.0",
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

    # ── /api/v1/auth ───────────────────────────────────────────────────

    @app.post("/api/v1/auth/register", response_model=AuthUser)
    async def register(body: RegisterRequest) -> AuthUser:
        """Sign up with first + last name only.

        No password / email yet — those land with the proper auth pass.
        Web users get negative bigint ids so they never collide with the
        positive Telegram ids the bot writes. Two people can register
        with identical names; they each get their own user row.
        """
        first = body.first_name.strip()
        last = body.last_name.strip()
        if not first or not last:
            raise HTTPException(status_code=400, detail="first_name and last_name are required")

        async with session_factory() as session:
            for _ in range(5):
                new_id = -secrets.randbelow(2**53) - 1
                user = User(
                    id=new_id,
                    first_name=first,
                    last_name=last,
                    display_name=f"{first} {last}".strip(),
                    queries_used=0,
                    queries_limit=100000,
                )
                session.add(user)
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    continue
                return AuthUser(
                    user_id=new_id,
                    first_name=first,
                    last_name=last,
                    onboarded=False,
                )

        raise HTTPException(status_code=500, detail="failed to allocate a user id")

    @app.post("/api/v1/auth/login", response_model=AuthUser)
    async def login(body: LoginRequest) -> AuthUser:
        """Look up an existing web user by exact first + last name match.

        Case-insensitive. If multiple rows match (two registrations of
        the same name), the most recently created one wins — good enough
        for the temporary name-only flow.
        """
        first = body.first_name.strip()
        last = body.last_name.strip()
        if not first or not last:
            raise HTTPException(status_code=400, detail="first_name and last_name are required")

        async with session_factory() as session:
            result = await session.execute(
                select(User)
                .where(User.id < 0)
                .where(func.lower(User.first_name) == first.lower())
                .where(func.lower(User.last_name) == last.lower())
                .order_by(User.created_at.desc())
                .limit(1)
            )
            user = result.scalar_one_or_none()
            if user is None:
                raise HTTPException(status_code=404, detail="user not found")
            return AuthUser(
                user_id=user.id,
                first_name=user.first_name or first,
                last_name=user.last_name or last,
                onboarded=_is_onboarded(user),
            )

    # ── /api/v1/users ──────────────────────────────────────────────────

    @app.get("/api/v1/users/{user_id}", response_model=UserProfile)
    async def get_user(user_id: int) -> UserProfile:
        async with session_factory() as session:
            user = await session.get(User, user_id)
            if user is None:
                raise HTTPException(status_code=404, detail="user not found")
            return _to_profile(user)

    @app.patch("/api/v1/users/{user_id}", response_model=UserProfile)
    async def update_user(user_id: int, body: UserProfileUpdate) -> UserProfile:
        """Update onboarding profile.

        When ``service_description`` is provided, runs it through Claude
        (`normalize_profession`) so the stored ``profession`` is the
        short, prompt-friendly version — same shape Telegram users get.
        Sets ``onboarded_at`` automatically once the required fields
        (display_name, profession, niches) are all present.
        """
        async with session_factory() as session:
            user = await session.get(User, user_id)
            if user is None:
                raise HTTPException(status_code=404, detail="user not found")

            data = body.model_dump(exclude_unset=True)

            if "display_name" in data:
                user.display_name = (data["display_name"] or "").strip() or None
            if "age_range" in data:
                user.age_range = data["age_range"] or None
            if "business_size" in data:
                user.business_size = data["business_size"] or None
            if "home_region" in data:
                user.home_region = (data["home_region"] or "").strip() or None
            if "language_code" in data:
                user.language_code = data["language_code"] or None
            if "niches" in data:
                cleaned = [
                    n.strip() for n in (data["niches"] or []) if isinstance(n, str) and n.strip()
                ]
                user.niches = cleaned or None
            if "service_description" in data:
                raw = (data["service_description"] or "").strip()
                if raw:
                    user.service_description = raw
                    try:
                        user.profession = (await AIAnalyzer().normalize_profession(raw)) or raw
                    except Exception:  # noqa: BLE001
                        logger.exception("normalize_profession failed; storing raw text")
                        user.profession = raw
                else:
                    user.service_description = None
                    user.profession = None

            if (
                user.display_name
                and user.profession
                and user.niches
                and user.onboarded_at is None
            ):
                user.onboarded_at = datetime.now(timezone.utc)

            await session.commit()
            await session.refresh(user)
            return _to_profile(user)

    # ── /api/v1/searches ───────────────────────────────────────────────

    @app.post("/api/v1/searches", response_model=SearchCreateResponse)
    async def create_search(body: SearchCreate) -> SearchCreateResponse:
        """Create a SearchQuery row + launch the pipeline.

        Execution path:
        1. Redis configured → enqueue on arq (worker does the heavy lifting).
        2. Redis NOT configured → spawn ``asyncio.create_task`` in this
           process. Runs fine for single-container Railway deployments with
           modest traffic; for production volume enable the queue.
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
            user = await session.get(User, body.user_id)
            query = SearchQuery(
                user_id=body.user_id,
                niche=body.niche,
                region=body.region,
                source="web",
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

        # Snapshot the full profile so Claude personalises every lead the
        # same way it does for Telegram users. Per-search overrides on the
        # request body win — the search form lets people retarget without
        # editing their saved profile.
        user_profile: dict[str, Any] = {}
        if user is not None:
            user_profile = {
                "display_name": user.display_name or user.first_name,
                "age_range": user.age_range,
                "business_size": user.business_size,
                "profession": user.profession,
                "service_description": user.service_description,
                "home_region": user.home_region,
                "niches": list(user.niches or []),
                "language_code": user.language_code,
            }
        if body.language_code:
            user_profile["language_code"] = body.language_code
        if body.profession:
            user_profile["profession"] = body.profession

        queued_id = await enqueue_search(
            query.id,
            chat_id=None,
            user_profile=user_profile or None,
        )
        queued = bool(queued_id)

        if not queued:
            # No Redis → run inline. Fire-and-forget; progress is streamed
            # over the broker, so the HTTP response can return immediately.
            asyncio.create_task(
                _run_web_search_inline(query.id, user_profile or None),
                name=f"leadgen-web-search-{query.id}",
            )

        return SearchCreateResponse(id=query.id, queued=queued)

    @app.get("/api/v1/searches", response_model=list[SearchSummary])
    async def list_searches(
        user_id: int = WEB_DEMO_USER_ID, limit: int = 50
    ) -> list[SearchSummary]:
        limit = max(1, min(limit, 200))
        async with session_factory() as session:
            result = await session.execute(
                select(SearchQuery)
                .where(SearchQuery.user_id == user_id)
                .order_by(SearchQuery.created_at.desc())
                .limit(limit)
            )
            return [_to_summary(row) for row in result.scalars().all()]

    @app.get("/api/v1/searches/{search_id}", response_model=SearchSummary)
    async def get_search(search_id: uuid.UUID) -> SearchSummary:
        async with session_factory() as session:
            query = await session.get(SearchQuery, search_id)
            if query is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="search not found"
                )
            return _to_summary(query)

    @app.get(
        "/api/v1/searches/{search_id}/leads", response_model=list[LeadResponse]
    )
    async def list_search_leads(
        search_id: uuid.UUID,
        temp: str | None = None,
    ) -> list[LeadResponse]:
        """All leads for one search. Optional ?temp=hot|warm|cold filter
        (computed from score_ai, not a DB column, so it happens in Python)."""
        async with session_factory() as session:
            result = await session.execute(
                select(Lead)
                .where(Lead.query_id == search_id)
                .order_by(Lead.score_ai.desc().nullslast(), Lead.rating.desc().nullslast())
            )
            leads = list(result.scalars().all())

        if temp in {"hot", "warm", "cold"}:
            leads = [lead for lead in leads if _temp(lead.score_ai) == temp]
        return [LeadResponse.model_validate(lead) for lead in leads]

    @app.get("/api/v1/leads", response_model=LeadListResponse)
    async def list_all_leads(
        user_id: int = WEB_DEMO_USER_ID,
        lead_status: str | None = None,
        limit: int = 200,
    ) -> LeadListResponse:
        """Cross-session CRM listing. Joins on SearchQuery to scope to the
        caller and returns a lightweight session_id → {niche, region} map so
        the UI can show each row's parent session without a second hop."""
        limit = max(1, min(limit, 500))
        async with session_factory() as session:
            stmt = (
                select(Lead, SearchQuery.niche, SearchQuery.region)
                .join(SearchQuery, SearchQuery.id == Lead.query_id)
                .where(SearchQuery.user_id == user_id)
                .where(SearchQuery.source == "web")
                .order_by(Lead.score_ai.desc().nullslast(), Lead.created_at.desc())
                .limit(limit)
            )
            if lead_status:
                stmt = stmt.where(Lead.lead_status == lead_status)
            rows = (await session.execute(stmt)).all()

            total_stmt = (
                select(func.count(Lead.id))
                .join(SearchQuery, SearchQuery.id == Lead.query_id)
                .where(SearchQuery.user_id == user_id)
                .where(SearchQuery.source == "web")
            )
            total = int((await session.execute(total_stmt)).scalar() or 0)

        leads: list[LeadResponse] = []
        sessions_by_id: dict[str, dict[str, Any]] = {}
        for lead, niche, region in rows:
            leads.append(LeadResponse.model_validate(lead))
            sessions_by_id[str(lead.query_id)] = {"niche": niche, "region": region}
        return LeadListResponse(leads=leads, total=total, sessions_by_id=sessions_by_id)

    @app.patch("/api/v1/leads/{lead_id}", response_model=LeadResponse)
    async def update_lead(lead_id: uuid.UUID, body: LeadUpdate) -> LeadResponse:
        """Partial update: status, owner, notes. Touches last_touched_at."""
        changes: dict[str, Any] = {}
        if body.lead_status is not None:
            if body.lead_status not in {"new", "contacted", "replied", "won", "archived"}:
                raise HTTPException(
                    status_code=400,
                    detail="lead_status must be one of new/contacted/replied/won/archived",
                )
            changes["lead_status"] = body.lead_status
        if body.owner_user_id is not None or "owner_user_id" in body.model_fields_set:
            changes["owner_user_id"] = body.owner_user_id
        if body.notes is not None:
            changes["notes"] = body.notes
        if not changes:
            raise HTTPException(status_code=400, detail="no fields to update")
        changes["last_touched_at"] = datetime.now(timezone.utc)

        async with session_factory() as session:
            await session.execute(
                update(Lead).where(Lead.id == lead_id).values(**changes)
            )
            await session.commit()
            lead = await session.get(Lead, lead_id)
            if lead is None:
                raise HTTPException(status_code=404, detail="lead not found")
            return LeadResponse.model_validate(lead)

    @app.get("/api/v1/stats", response_model=DashboardStats)
    async def dashboard_stats(user_id: int = WEB_DEMO_USER_ID) -> DashboardStats:
        async with session_factory() as session:
            # Searches — only count the web-owned ones (Telegram searches
            # have no leads left after cleanup anyway).
            query_stmt = (
                select(SearchQuery)
                .where(SearchQuery.user_id == user_id)
                .where(SearchQuery.source == "web")
            )
            searches = list((await session.execute(query_stmt)).scalars().all())

            # Leads across all done searches.
            lead_stmt = (
                select(Lead.score_ai)
                .join(SearchQuery, SearchQuery.id == Lead.query_id)
                .where(SearchQuery.user_id == user_id)
                .where(SearchQuery.source == "web")
            )
            scores = [row[0] for row in (await session.execute(lead_stmt)).all()]

        hot = sum(1 for s in scores if s is not None and s >= 75)
        warm = sum(1 for s in scores if s is not None and 50 <= s < 75)
        cold = sum(1 for s in scores if s is not None and s < 50)
        running = sum(1 for s in searches if s.status == "running")

        return DashboardStats(
            sessions_total=len(searches),
            sessions_running=running,
            leads_total=len(scores),
            hot_total=hot,
            warm_total=warm,
            cold_total=cold,
        )

    @app.get("/api/v1/team", response_model=list[TeamMemberResponse])
    async def list_team_members() -> list[TeamMemberResponse]:
        """Real teammates from Team / TeamMembership. Returns an empty
        list when there are none so the UI can render its own empty
        state rather than baking a fake "Denys / Alina / Max / Kira"
        roster into the product."""
        async with session_factory() as session:
            stmt = (
                select(TeamMembership, User, Team)
                .join(User, User.id == TeamMembership.user_id)
                .join(Team, Team.id == TeamMembership.team_id)
                .where(User.id != WEB_DEMO_USER_ID)
                .order_by(User.first_name)
            )
            rows = (await session.execute(stmt)).all()

        members: list[TeamMemberResponse] = []
        for i, (_, user, _team) in enumerate(rows):
            display = user.display_name or user.first_name or f"User {user.id}"
            members.append(
                TeamMemberResponse(
                    id=user.id,
                    name=display,
                    role=user.profession or "Member",
                    initials=display[:1].upper(),
                    color=_DEMO_TEAM_COLORS[i % len(_DEMO_TEAM_COLORS)],
                    email=user.username and f"{user.username}@leadgen.app",
                )
            )
        return members

    @app.get("/api/v1/queue/status", include_in_schema=False)
    async def queue_status() -> dict[str, bool]:
        return {"queue_enabled": is_queue_enabled()}

    # ── SSE: live search progress ───────────────────────────────────────

    @app.get("/api/v1/searches/{search_id}/progress")
    async def search_progress(
        search_id: uuid.UUID,
        api_key: str | None = Query(default=None, alias="api_key"),
    ) -> StreamingResponse:
        """Server-Sent Events stream of progress beats.

        Auth: if WEB_API_KEY is configured, require it as ``?api_key=``.
        Otherwise (open-demo mode), stream unauthenticated — connections
        are short-lived and the broker auto-closes on search completion.
        """
        expected = get_settings().web_api_key
        if expected and api_key != expected:
            raise HTTPException(status_code=401, detail="invalid api_key")

        async def event_stream() -> asyncio.AsyncIterator[bytes]:
            yield b"retry: 5000\n\n"
            async for event in default_broker.subscribe(search_id):
                payload = json.dumps({"kind": event.kind, **event.data})
                yield f"event: {event.kind}\ndata: {payload}\n\n".encode()
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


async def _run_web_search_inline(
    query_id: uuid.UUID, user_profile: dict[str, Any] | None
) -> None:
    """Fallback in-process runner when no Redis worker is available.

    Wraps ``run_search_with_sinks`` with a WebDeliverySink + a
    BrokerProgressSink so the SSE endpoint has something to stream.
    Any exception is swallowed here — the pipeline itself marks the
    SearchQuery as failed, and a crash in this task shouldn't take
    down the API server.
    """
    try:
        progress = BrokerProgressSink(default_broker, query_id)
        delivery = WebDeliverySink(query_id)
        await run_search_with_sinks(
            query_id=query_id,
            progress=progress,
            delivery=delivery,
            user_profile=user_profile,
        )
    except Exception:  # noqa: BLE001
        logger.exception("inline web search crashed for %s", query_id)


def _to_summary(query: SearchQuery) -> SearchSummary:
    insights: str | None = None
    if isinstance(query.analysis_summary, dict):
        raw = query.analysis_summary.get("insights")
        if isinstance(raw, str):
            insights = raw
    return SearchSummary(
        id=query.id,
        user_id=query.user_id,
        niche=query.niche,
        region=query.region,
        status=query.status,
        source=query.source,
        created_at=query.created_at,
        finished_at=query.finished_at,
        leads_count=query.leads_count,
        avg_score=query.avg_score,
        hot_leads_count=query.hot_leads_count,
        error=query.error,
        insights=insights,
    )


def _temp(score: float | None) -> str:
    """Bucket a 0–100 AI score into prototype temperature tiers."""
    if score is None:
        return "cold"
    if score >= 75:
        return "hot"
    if score >= 50:
        return "warm"
    return "cold"


def _is_onboarded(user: User) -> bool:
    """Mirror the Telegram bot's check so both surfaces agree."""
    return (
        user.onboarded_at is not None
        and bool(user.profession)
        and bool(user.niches)
    )


def _to_profile(user: User) -> UserProfile:
    return UserProfile(
        user_id=user.id,
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        display_name=user.display_name,
        age_range=user.age_range,
        business_size=user.business_size,
        profession=user.profession,
        service_description=user.service_description,
        home_region=user.home_region,
        niches=list(user.niches) if user.niches else None,
        language_code=user.language_code,
        onboarded=_is_onboarded(user),
    )
