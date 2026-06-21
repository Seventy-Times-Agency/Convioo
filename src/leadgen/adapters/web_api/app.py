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
import json
import logging
import os
import secrets
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from typing import Any

import sqlalchemy as sa
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest
from sqlalchemy import case, func, select, update

from leadgen.adapters.web_api.auth import (
    get_current_user,
    request_ip,
)
from leadgen.adapters.web_api.csrf import CsrfMiddleware
from leadgen.adapters.web_api.schemas import (
    CityEntryResponse,
    CityListResponse,
    DashboardStats,
    HealthResponse,
    LeadResponse,
    LeadStatusCreate,
    LeadStatusListResponse,
    LeadStatusReorderRequest,
    LeadStatusSchema,
    LeadStatusUpdate,
    LeadTagSchema,
    NicheTaxonomyEntry,
    NicheTaxonomyResponse,
    PendingAction,
    PriorTeamSearch,
    SearchSummary,
    TeamAnalytics,
    TeamAnalyticsMemberBucket,
    TeamAnalyticsNicheBucket,
    TeamAnalyticsSourceBucket,
    TeamAnalyticsStatusBucket,
    TeamAnalyticsTimepoint,
    TeamDetailResponse,
    TeamMemberResponse,
    TeamMemberSummary,
    UserProfile,
)
from leadgen.adapters.web_api.sinks import WebDeliverySink
from leadgen.analysis.ai_analyzer import AIAnalyzer
from leadgen.config import assert_production_secrets, get_settings
from leadgen.core.services import (
    default_broker,
    mask_email,
    render_verification_email,
    send_email,
)
from leadgen.core.services.assistant_memory import (
    prune_old,
    record_memory,
)
from leadgen.core.services.progress_broker import BrokerProgressSink
from leadgen.core.services.team_permissions import (
    ROLE_OWNER as _ROLE_OWNER,
)
from leadgen.core.services.team_permissions import (
    can_manage_members as _can_manage_members,
)
from leadgen.core.services.team_permissions import (
    normalize_role as _normalize_role,
)
from leadgen.db.models import (
    EmailVerificationToken,
    Lead,
    LeadMark,
    LeadStatus,
    LeadTag,
    LeadTagAssignment,
    SavedSearch,
    SearchQuery,
    Team,
    TeamInvite,
    TeamMembership,
    User,
    UserAuditLog,
)
from leadgen.db.session import session_factory
from leadgen.pipeline.search import run_search_with_timeout
from leadgen.queue import enqueue_search, is_queue_enabled
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

    @app.get(
        "/api/v1/teams/{team_id}/members-summary",
        response_model=list[TeamMemberSummary],
    )
    async def team_members_summary(
        team_id: uuid.UUID,
        current_user: User = Depends(get_current_user),
    ) -> list[TeamMemberSummary]:
        """Owner-only roll-up: per-member sessions/leads/hot counts.

        Powers the "see each teammate's CRM" panel — the owner picks a
        row and the workspace switches to viewing that member via
        ``member_user_id`` on the list endpoints.
        """
        async with session_factory() as session:
            caller = await _membership(session, team_id, current_user.id)
            if caller is None or _normalize_role(caller.role) != _ROLE_OWNER:
                raise HTTPException(
                    status_code=403,
                    detail="only the team owner can see the per-member summary",
                )

            rows = (
                await session.execute(
                    select(TeamMembership, User)
                    .join(User, User.id == TeamMembership.user_id)
                    .where(TeamMembership.team_id == team_id)
                    .order_by(TeamMembership.created_at)
                )
            ).all()

            # Two aggregate roll-ups keyed by member, so the response is
            # 3 queries total regardless of team size (was 2 per member).
            sessions_by_user = {
                uid: int(count or 0)
                for uid, count in (
                    await session.execute(
                        select(
                            SearchQuery.user_id, func.count(SearchQuery.id)
                        )
                        .where(SearchQuery.team_id == team_id)
                        .group_by(SearchQuery.user_id)
                    )
                ).all()
            }
            leads_by_user = {
                uid: (int(total or 0), int(hot or 0))
                for uid, total, hot in (
                    await session.execute(
                        select(
                            SearchQuery.user_id,
                            func.count(Lead.id),
                            func.count(
                                case((Lead.score_ai >= 75, 1))
                            ),
                        )
                        .join(SearchQuery, SearchQuery.id == Lead.query_id)
                        .where(SearchQuery.team_id == team_id)
                        .group_by(SearchQuery.user_id)
                    )
                ).all()
            }

            results: list[TeamMemberSummary] = []
            for membership, member in rows:
                leads_total, hot = leads_by_user.get(member.id, (0, 0))
                display = (
                    member.display_name
                    or " ".join(filter(None, [member.first_name, member.last_name]))
                    or f"User {member.id}"
                )
                results.append(
                    TeamMemberSummary(
                        user_id=member.id,
                        name=display,
                        role=membership.role,
                        sessions_total=sessions_by_user.get(member.id, 0),
                        leads_total=leads_total,
                        hot_total=hot,
                    )
                )
            return results

    @app.get("/api/v1/stats", response_model=DashboardStats)
    async def dashboard_stats(
        team_id: uuid.UUID | None = None,
        member_user_id: int | None = None,
        current_user: User = Depends(get_current_user),
    ) -> DashboardStats:
        user_id = current_user.id
        async with session_factory() as session:
            query_stmt = (
                select(SearchQuery).where(SearchQuery.source == "web")
            )
            lead_stmt = (
                select(Lead.score_ai)
                .join(SearchQuery, SearchQuery.id == Lead.query_id)
                .where(SearchQuery.source == "web")
            )
            if team_id is not None:
                target_user = await _resolve_team_view(
                    session, team_id, user_id, member_user_id
                )
                query_stmt = query_stmt.where(
                    SearchQuery.team_id == team_id
                ).where(SearchQuery.user_id == target_user)
                lead_stmt = lead_stmt.where(
                    SearchQuery.team_id == team_id
                ).where(SearchQuery.user_id == target_user)
            else:
                query_stmt = query_stmt.where(SearchQuery.user_id == user_id).where(
                    SearchQuery.team_id.is_(None)
                )
                lead_stmt = lead_stmt.where(SearchQuery.user_id == user_id).where(
                    SearchQuery.team_id.is_(None)
                )

            searches = list((await session.execute(query_stmt)).scalars().all())
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

    # GET /api/v1/team (flat all-users roster) was removed: nothing in
    # the frontend called it and it leaked every registered user's name
    # to any caller. Team rosters live at /api/v1/teams/{team_id}.

    @app.get("/api/v1/queue/status", include_in_schema=False)
    async def queue_status() -> dict[str, bool]:
        return {"queue_enabled": is_queue_enabled()}

    # /api/v1/tags moved to routes/tags.py

    # /api/v1/segments moved to routes/segments.py

    # /api/v1/integrations/* and /api/v1/oauth/* and /api/v1/track
    # and /api/v1/affiliate moved to routes/integrations.py


    # /api/v1/billing/* moved to routes/billing.py

    # ── /api/v1/niches (public taxonomy autocomplete) ──────────────────

    @app.get("/api/v1/niches", response_model=NicheTaxonomyResponse)
    async def list_niches(
        q: str | None = Query(default=None, max_length=80),
        lang: str | None = Query(default=None, max_length=8),
        limit: int = Query(default=12, ge=1, le=50),
    ) -> NicheTaxonomyResponse:
        """Static taxonomy lookup for the search-form niche combobox.

        Empty ``q`` returns the curated top-of-list so the dropdown
        can prefill on focus. Anything else does a substring/prefix
        match across labels + aliases in any supported language —
        a Russian-speaking user typing "дантист" lands on
        ``dentists`` even though the canonical English label says
        "Dentists".
        """
        from leadgen.data.niches import (
            DEFAULT_LANGUAGE,
            SUPPORTED_LANGUAGES,
        )
        from leadgen.data.niches import (
            suggest as suggest_niches_taxonomy,
        )

        language = lang or DEFAULT_LANGUAGE
        if language not in SUPPORTED_LANGUAGES:
            language = DEFAULT_LANGUAGE
        matches = suggest_niches_taxonomy(q, language=language, limit=limit)
        return NicheTaxonomyResponse(
            items=[
                NicheTaxonomyEntry(
                    id=m.id,
                    label=m.label(language),
                    category=m.category,
                )
                for m in matches
            ],
            query=(q or ""),
            language=language,
        )

    # ── /api/v1/cities (public city autocomplete) ──────────────────────

    @app.get("/api/v1/cities", response_model=CityListResponse)
    async def list_cities(
        q: str | None = Query(default=None, max_length=80),
        country: str | None = Query(default=None, max_length=4),
        lang: str | None = Query(default=None, max_length=8),
        limit: int = Query(default=12, ge=1, le=50),
    ) -> CityListResponse:
        """Curated city catalogue for the search-form region combobox.

        Empty ``q`` returns the population-sorted top so the dropdown
        prefills on focus. ``country`` (ISO2) narrows to a single
        country once the SPA knows the user picked scope=country.
        Anything outside the catalogue is still typeable by hand —
        the combobox is purely additive.
        """
        from leadgen.data.cities import suggest as suggest_cities

        language = (lang or "en").lower()
        matches = suggest_cities(
            q, country=country, language=language, limit=limit
        )
        return CityListResponse(
            items=[
                CityEntryResponse(
                    id=c.id,
                    name=c.label(language),
                    country=c.country,
                    lat=c.lat,
                    lon=c.lon,
                    population=c.population,
                )
                for c in matches
            ],
            query=(q or ""),
            language=language,
        )

    # /api/v1/admin/* (overview / sources/health / quality) moved
    # to routes/admin.py.

    # ── /api/v1/teams/{team_id}/analytics (per-team analytics) ────────

    @app.get(
        "/api/v1/teams/{team_id}/analytics",
        response_model=TeamAnalytics,
    )
    async def team_analytics(
        team_id: uuid.UUID,
        from_: datetime | None = Query(default=None, alias="from"),
        to: datetime | None = None,
        current_user: User = Depends(get_current_user),
    ) -> TeamAnalytics:
        """Owner-only per-team analytics for ``/app/team/analytics``.

        Returns a single payload with everything the page renders:
        totals, status breakdown, top source / member / niche, and a
        per-day timeseries of searches + leads. Defaults to the last
        30 days when the caller doesn't pass an explicit window.
        """
        now = datetime.now(timezone.utc)
        period_to = to or now
        period_from = from_ or (period_to - timedelta(days=30))
        if period_to.tzinfo is None:
            period_to = period_to.replace(tzinfo=timezone.utc)
        if period_from.tzinfo is None:
            period_from = period_from.replace(tzinfo=timezone.utc)

        async with session_factory() as session:
            team = await session.get(Team, team_id)
            if team is None:
                raise HTTPException(status_code=404, detail="team not found")
            membership = await _membership(session, team_id, current_user.id)
            if membership is None or not _can_manage_members(membership.role):
                raise HTTPException(
                    status_code=403,
                    detail="only owner or admin can view analytics",
                )

            base_searches = (
                select(SearchQuery)
                .where(SearchQuery.team_id == team_id)
                .where(SearchQuery.created_at >= period_from)
                .where(SearchQuery.created_at <= period_to)
            )
            search_rows = (
                await session.execute(base_searches)
            ).scalars().all()

            search_ids = [s.id for s in search_rows]
            lead_rows: list[Lead] = []
            if search_ids:
                lead_rows = (
                    await session.execute(
                        select(Lead).where(Lead.query_id.in_(search_ids))
                    )
                ).scalars().all()

            # Aggregations -------------------------------------------------
            scores = [
                float(lead.score_ai)
                for lead in lead_rows
                if lead.score_ai is not None
            ]
            avg_score = round(sum(scores) / len(scores), 1) if scores else None

            # Per-status (use whatever string is on Lead.lead_status to
            # stay compatible with custom team statuses from PR #30).
            status_counts: dict[str, int] = {}
            for lead in lead_rows:
                key = lead.lead_status or "new"
                status_counts[key] = status_counts.get(key, 0) + 1
            status_breakdown = [
                TeamAnalyticsStatusBucket(status=k, leads_count=v)
                for k, v in sorted(
                    status_counts.items(), key=lambda kv: kv[1], reverse=True
                )
            ]

            # Per-source.
            source_counts: dict[str, int] = {}
            for lead in lead_rows:
                key = lead.source or "unknown"
                source_counts[key] = source_counts.get(key, 0) + 1
            sources = [
                TeamAnalyticsSourceBucket(source=k, leads_count=v)
                for k, v in sorted(
                    source_counts.items(), key=lambda kv: kv[1], reverse=True
                )
            ]
            top_source = sources[0] if sources else None

            # Per-niche (search-level).
            niche_counts: dict[str, int] = {}
            for sq in search_rows:
                key = (sq.niche or "").strip().lower() or "—"
                niche_counts[key] = niche_counts.get(key, 0) + 1
            niches = [
                TeamAnalyticsNicheBucket(niche=k, searches_total=v)
                for k, v in sorted(
                    niche_counts.items(), key=lambda kv: kv[1], reverse=True
                )
            ]
            top_niche = niches[0] if niches else None

            # Per-member (active users in this team during the window).
            members_rows = (
                await session.execute(
                    select(TeamMembership, User)
                    .join(User, User.id == TeamMembership.user_id)
                    .where(TeamMembership.team_id == team_id)
                )
            ).all()
            search_user_map = {sq.id: sq.user_id for sq in search_rows}
            searches_by_user: dict[int, int] = {}
            for sq in search_rows:
                searches_by_user[sq.user_id] = searches_by_user.get(sq.user_id, 0) + 1
            leads_by_user: dict[int, list[Lead]] = {}
            for lead in lead_rows:
                uid = search_user_map.get(lead.query_id)
                if uid is None:
                    continue
                leads_by_user.setdefault(uid, []).append(lead)

            members: list[TeamAnalyticsMemberBucket] = []
            for _ms, u in members_rows:
                user_leads = leads_by_user.get(u.id, [])
                user_scores = [
                    float(lead.score_ai)
                    for lead in user_leads
                    if lead.score_ai is not None
                ]
                hot = sum(1 for s in user_scores if s >= 75)
                avg = (
                    round(sum(user_scores) / len(user_scores), 1)
                    if user_scores
                    else None
                )
                display = (
                    u.display_name
                    or " ".join(filter(None, [u.first_name, u.last_name]))
                    or f"User {u.id}"
                )
                members.append(
                    TeamAnalyticsMemberBucket(
                        user_id=u.id,
                        name=display,
                        searches_total=searches_by_user.get(u.id, 0),
                        leads_total=len(user_leads),
                        hot_leads=hot,
                        avg_score=avg,
                    )
                )
            members.sort(key=lambda m: m.leads_total, reverse=True)
            top_member = (
                members[0] if members and members[0].leads_total > 0 else None
            )

            # Day timeseries (UTC dates).
            day_searches: dict[str, int] = {}
            day_leads: dict[str, int] = {}
            for sq in search_rows:
                d = sq.created_at
                if d.tzinfo is None:
                    d = d.replace(tzinfo=timezone.utc)
                key = d.date().isoformat()
                day_searches[key] = day_searches.get(key, 0) + 1
            for lead in lead_rows:
                d = lead.created_at
                if d.tzinfo is None:
                    d = d.replace(tzinfo=timezone.utc)
                key = d.date().isoformat()
                day_leads[key] = day_leads.get(key, 0) + 1
            day_keys = sorted(set(day_searches) | set(day_leads))
            timeseries = [
                TeamAnalyticsTimepoint(
                    date=k,
                    searches_total=day_searches.get(k, 0),
                    leads_total=day_leads.get(k, 0),
                )
                for k in day_keys
            ]

            # Lead-cost approximation: same Haiku per-call estimate as
            # the admin dashboard, applied to every analyzed lead in
            # the window. One enriched lead ≈ one analysis call.
            enriched_leads = sum(1 for lead in lead_rows if lead.enriched)
            avg_lead_cost = (
                round((enriched_leads * 0.005) / max(len(lead_rows), 1), 4)
                if lead_rows
                else None
            )

        return TeamAnalytics(
            team_id=str(team_id),
            period_from=period_from,
            period_to=period_to,
            searches_total=len(search_rows),
            leads_total=len(lead_rows),
            avg_lead_score=avg_score,
            avg_lead_cost_usd=avg_lead_cost,
            status_breakdown=status_breakdown,
            top_source=top_source,
            top_member=top_member,
            top_niche=top_niche,
            members=members,
            sources=sources,
            niches=niches[:10],
            timeseries=timeseries,
        )

    # ── /api/v1/teams/{team_id}/statuses (custom CRM pipeline) ─────────

    @app.get(
        "/api/v1/teams/{team_id}/statuses",
        response_model=LeadStatusListResponse,
    )
    async def list_lead_statuses(
        team_id: uuid.UUID,
        current_user: User = Depends(get_current_user),
    ) -> LeadStatusListResponse:
        async with session_factory() as session:
            membership = await _membership(session, team_id, current_user.id)
            if membership is None:
                raise HTTPException(status_code=403, detail="forbidden")
            rows = (
                (
                    await session.execute(
                        select(LeadStatus)
                        .where(LeadStatus.team_id == team_id)
                        .order_by(
                            LeadStatus.order_index.asc(),
                            LeadStatus.created_at.asc(),
                        )
                    )
                )
                .scalars()
                .all()
            )
        return LeadStatusListResponse(
            items=[_status_to_schema(s) for s in rows]
        )

    @app.post(
        "/api/v1/teams/{team_id}/statuses",
        response_model=LeadStatusSchema,
    )
    async def create_lead_status(
        team_id: uuid.UUID,
        body: LeadStatusCreate,
        current_user: User = Depends(get_current_user),
    ) -> LeadStatusSchema:
        async with session_factory() as session:
            membership = await _membership(session, team_id, current_user.id)
            if membership is None:
                raise HTTPException(status_code=403, detail="forbidden")
            key = body.key.strip().lower()
            cleaned = "".join(
                ch for ch in key if ch.isalnum() or ch in "-_"
            )
            if len(cleaned) < 1:
                raise HTTPException(
                    status_code=400, detail="key must be alphanumeric"
                )
            existing_keys = (
                await session.execute(
                    select(LeadStatus.key, func.max(LeadStatus.order_index))
                    .where(LeadStatus.team_id == team_id)
                    .group_by(LeadStatus.key)
                )
            ).all()
            keys = {k for k, _ in existing_keys}
            if cleaned in keys:
                raise HTTPException(
                    status_code=409, detail="key already exists in this team"
                )
            max_order = max(
                (m for _, m in existing_keys), default=-1
            )
            row = LeadStatus(
                team_id=team_id,
                key=cleaned[:32],
                label=body.label.strip()[:64],
                color=(body.color or "slate").strip().lower()[:16],
                order_index=int(max_order) + 1,
                is_terminal=bool(body.is_terminal),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
        return _status_to_schema(row)

    @app.patch(
        "/api/v1/teams/{team_id}/statuses/{status_id}",
        response_model=LeadStatusSchema,
    )
    async def update_lead_status(
        team_id: uuid.UUID,
        status_id: uuid.UUID,
        body: LeadStatusUpdate,
        current_user: User = Depends(get_current_user),
    ) -> LeadStatusSchema:
        async with session_factory() as session:
            membership = await _membership(session, team_id, current_user.id)
            if membership is None:
                raise HTTPException(status_code=403, detail="forbidden")
            row = await session.get(LeadStatus, status_id)
            if row is None or row.team_id != team_id:
                raise HTTPException(status_code=404, detail="status not found")
            if body.label is not None:
                row.label = body.label.strip()[:64] or row.label
            if body.color is not None:
                row.color = body.color.strip().lower()[:16] or "slate"
            if body.order_index is not None:
                row.order_index = int(body.order_index)
            if body.is_terminal is not None:
                row.is_terminal = bool(body.is_terminal)
            await session.commit()
            await session.refresh(row)
        return _status_to_schema(row)

    @app.delete("/api/v1/teams/{team_id}/statuses/{status_id}")
    async def delete_lead_status(
        team_id: uuid.UUID,
        status_id: uuid.UUID,
        current_user: User = Depends(get_current_user),
    ) -> dict[str, bool]:
        async with session_factory() as session:
            membership = await _membership(session, team_id, current_user.id)
            if membership is None:
                raise HTTPException(status_code=403, detail="forbidden")
            row = await session.get(LeadStatus, status_id)
            if row is None or row.team_id != team_id:
                raise HTTPException(status_code=404, detail="status not found")
            # Refuse to delete a status still attached to live leads —
            # cascading them silently to "archived" surprises the user.
            in_use = (
                await session.execute(
                    select(func.count(Lead.id))
                    .join(SearchQuery, SearchQuery.id == Lead.query_id)
                    .where(SearchQuery.team_id == team_id)
                    .where(Lead.lead_status == row.key)
                    .where(Lead.deleted_at.is_(None))
                )
            ).scalar_one()
            if int(in_use or 0) > 0:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"{in_use} lead(s) still use this status. "
                        "Move them to another status first, then delete."
                    ),
                )
            await session.delete(row)
            await session.commit()
        return {"ok": True}

    @app.post(
        "/api/v1/teams/{team_id}/statuses/reorder",
        response_model=LeadStatusListResponse,
    )
    async def reorder_lead_statuses(
        team_id: uuid.UUID,
        body: LeadStatusReorderRequest,
        current_user: User = Depends(get_current_user),
    ) -> LeadStatusListResponse:
        async with session_factory() as session:
            membership = await _membership(session, team_id, current_user.id)
            if membership is None:
                raise HTTPException(status_code=403, detail="forbidden")
            owned_ids = set(
                (
                    await session.execute(
                        select(LeadStatus.id).where(
                            LeadStatus.team_id == team_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            updates = [
                {"id": sid, "order_index": index}
                for index, sid in enumerate(body.ordered_ids)
                if sid in owned_ids
            ]
            if updates:
                # Single round-trip executemany — replaces the previous
                # for-loop that issued one UPDATE per status row.
                await session.execute(sa.update(LeadStatus), updates)
            await session.commit()
            rows = list(
                (
                    await session.execute(
                        select(LeadStatus)
                        .where(LeadStatus.team_id == team_id)
                        .order_by(
                            LeadStatus.order_index.asc(),
                            LeadStatus.created_at.asc(),
                        )
                    )
                )
                .scalars()
                .all()
            )
        return LeadStatusListResponse(
            items=[_status_to_schema(r) for r in rows]
        )

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

        # SSE streams hold a connection (and a subscriber slot in the
        # broker) for the lifetime of the search. Cap each stream at
        # 10 min and send a comment heartbeat every 15s so idle proxies
        # and load balancers don't silently drop the socket mid-search.
        stream_max_seconds = 600.0
        heartbeat_interval = 15.0

        async def event_stream() -> asyncio.AsyncIterator[bytes]:
            yield b"retry: 5000\n\n"
            sub = default_broker.subscribe(search_id)
            loop = asyncio.get_running_loop()
            deadline = loop.time() + stream_max_seconds
            try:
                while True:
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        yield b"event: timeout\ndata: {}\n\n"
                        return
                    try:
                        event = await asyncio.wait_for(
                            sub.__anext__(),
                            timeout=min(heartbeat_interval, remaining),
                        )
                    except TimeoutError:
                        # SSE comment line — keepalive that the client
                        # does not surface as an event.
                        yield b": heartbeat\n\n"
                        continue
                    except StopAsyncIteration:
                        break
                    payload = json.dumps({"kind": event.kind, **event.data})
                    yield f"event: {event.kind}\ndata: {payload}\n\n".encode()
                yield b"event: done\ndata: {}\n\n"
            finally:
                await sub.aclose()

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

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
        await run_search_with_timeout(
            query_id=query_id,
            progress=progress,
            delivery=delivery,
            user_profile=user_profile,
        )
    except Exception:  # noqa: BLE001
        logger.exception("inline web search crashed for %s", query_id)


# How often the in-process scheduler scans the saved_searches table
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


async def _marks_for_user(
    session, user_id: int, lead_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Return ``lead_id -> color`` for one user across many leads."""
    if not lead_ids:
        return {}
    rows = (
        await session.execute(
            select(LeadMark.lead_id, LeadMark.color)
            .where(LeadMark.user_id == user_id)
            .where(LeadMark.lead_id.in_(lead_ids))
        )
    ).all()
    return {lead_id: color for lead_id, color in rows}


def _to_lead_response(
    lead: Lead,
    mark_color: str | None,
    user_tags: list[LeadTagSchema] | None = None,
) -> LeadResponse:
    payload = LeadResponse.model_validate(lead)
    payload.mark_color = mark_color
    if user_tags:
        payload.user_tags = list(user_tags)
    return payload


async def _tags_by_lead(
    session, lead_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[LeadTagSchema]]:
    """Eager-load every tag chip attached to ``lead_ids``.

    Returns ``{}`` for an empty input so callers can blindly merge it
    into the listing result.
    """
    if not lead_ids:
        return {}
    rows = (
        await session.execute(
            select(LeadTagAssignment.lead_id, LeadTag)
            .join(LeadTag, LeadTag.id == LeadTagAssignment.tag_id)
            .where(LeadTagAssignment.lead_id.in_(lead_ids))
            .order_by(LeadTag.created_at.asc())
        )
    ).all()
    out: dict[uuid.UUID, list[LeadTagSchema]] = {}
    for lead_id, tag in rows:
        out.setdefault(lead_id, []).append(
            LeadTagSchema(
                id=tag.id, name=tag.name, color=tag.color, team_id=tag.team_id
            )
        )
    return out


def _temp(score: float | None) -> str:
    """Bucket a 0–100 AI score into prototype temperature tiers."""
    if score is None:
        return "cold"
    if score >= 75:
        return "hot"
    if score >= 50:
        return "warm"
    return "cold"


def _extract_lead_email(lead: Lead) -> str | None:
    """Pluck the first usable email out of the website-meta payload.

    The website scraper stores discovered addresses under
    ``website_meta["emails"]`` after filtering out generic ones
    (info@, support@…). We pick the first; if none, we look at
    ``website_meta["primary_email"]`` for the rare case the scraper
    surfaced one but stripped the array.
    """
    meta = lead.website_meta or {}
    candidates = meta.get("emails") or []
    if isinstance(candidates, list) and candidates:
        first = candidates[0]
        if isinstance(first, str) and "@" in first:
            return first
    primary = meta.get("primary_email")
    if isinstance(primary, str) and "@" in primary:
        return primary
    return None


_password_hasher = PasswordHasher()


def _hash_password(plain: str) -> str:
    return _password_hasher.hash(plain)


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return _password_hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False
    except Exception:  # noqa: BLE001
        return False


async def _record_audit(
    session,
    *,
    user_id: int,
    action: str,
    request: Request | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Append an entry to ``user_audit_logs``.

    Best-effort: callers must commit the session themselves. Failures
    are logged but never raised so an audit hiccup can't break a real
    user-facing operation.
    """
    try:
        ua = (
            request.headers.get("user-agent")[:256]
            if request is not None and request.headers.get("user-agent")
            else None
        )
        session.add(
            UserAuditLog(
                user_id=user_id,
                action=action[:64],
                ip=request_ip(request),
                user_agent=ua,
                payload=payload,
            )
        )
    except Exception:  # noqa: BLE001
        logger.exception("failed to record audit log entry")


async def _issue_and_send_verification(session, user: User) -> None:
    """Mint a fresh verification token and email the user.

    Invalidates earlier outstanding tokens so there's only one live
    link at a time. Email dispatch failures don't bubble — the
    log-only fallback in send_email keeps signups working without a
    real provider.
    """
    settings = get_settings()
    await session.execute(
        update(EmailVerificationToken)
        .where(EmailVerificationToken.user_id == user.id)
        .where(EmailVerificationToken.kind == "verify")
        .where(EmailVerificationToken.used_at.is_(None))
        .values(used_at=datetime.now(timezone.utc))
    )
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=24)
    session.add(
        EmailVerificationToken(
            user_id=user.id,
            kind="verify",
            token=token,
            expires_at=expires,
        )
    )
    await session.commit()

    base = settings.public_app_url.rstrip("/")
    verify_url = f"{base}/verify-email/{token}"
    name = (
        user.first_name
        or user.display_name
        or (user.email.split("@")[0] if user.email else "")
        or "там"
    )
    html, text = render_verification_email(name=name, verify_url=verify_url)
    if user.email:
        await send_email(
            to=user.email,
            subject="Подтвердите email — Convioo",
            html=html,
            text=text,
        )


async def _issue_and_send_change_email(
    session, user: User, new_email: str
) -> None:
    """Mint a change-email token addressed to the *new* mailbox.

    The existing email keeps working until the user clicks the link;
    only then ``users.email`` is rewritten to the pending value.
    Earlier outstanding change-email tokens are invalidated so the
    user can't end up confirming a stale request.
    """
    settings = get_settings()
    await session.execute(
        update(EmailVerificationToken)
        .where(EmailVerificationToken.user_id == user.id)
        .where(EmailVerificationToken.kind == "change_email")
        .where(EmailVerificationToken.used_at.is_(None))
        .values(used_at=datetime.now(timezone.utc))
    )
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=24)
    session.add(
        EmailVerificationToken(
            user_id=user.id,
            kind="change_email",
            token=token,
            pending_email=new_email,
            expires_at=expires,
        )
    )
    await session.commit()

    base = settings.public_app_url.rstrip("/")
    verify_url = f"{base}/verify-email/{token}"
    name = (
        user.first_name
        or user.display_name
        or new_email.split("@")[0]
        or "там"
    )
    html, text = render_verification_email(name=name, verify_url=verify_url)
    await send_email(
        to=new_email,
        subject="Подтвердите новый email — Convioo",
        html=html,
        text=text,
    )


def _is_onboarded(user: User) -> bool:
    """Web onboarding gate.

    The web flow only requires a confirmed identity (a name + the
    onboarded_at stamp set at registration). What the user sells, the
    niches they target and their home region are filled later from
    the workspace (manually on /app/profile or via Henry) — they no
    longer block access. The Telegram bot keeps its own stricter
    check because its conversational onboarding still owns those
    fields end-to-end before letting the user search.
    """
    return user.onboarded_at is not None and bool(
        user.first_name or user.display_name
    )


def _invite_expired(invite: TeamInvite) -> bool:
    expires = invite.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= expires


async def _load_invite(session, token: str) -> tuple[TeamInvite, Team]:
    result = await session.execute(
        select(TeamInvite, Team)
        .join(Team, Team.id == TeamInvite.team_id)
        .where(TeamInvite.token == token)
        .limit(1)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="invite not found")
    return row[0], row[1]


async def _authorise_lead_access(
    session, lead_id: uuid.UUID, user_id: int
) -> tuple[Lead, SearchQuery | None]:
    """Load a lead and verify the caller may touch it.

    Allowed when the caller owns the parent search, or is a member of
    the team that search belongs to. Any failure — missing lead,
    missing search, foreign owner — answers 404 (never 403) so lead
    ids can't be probed for existence across accounts.
    """
    lead = await session.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="lead not found")
    search = await session.get(SearchQuery, lead.query_id)
    allowed = search is not None and search.user_id == user_id
    if not allowed and search is not None and search.team_id is not None:
        allowed = (
            await _membership(session, search.team_id, user_id)
        ) is not None
    if not allowed:
        raise HTTPException(status_code=404, detail="lead not found")
    return lead, search


async def _resolve_team_view(
    session,
    team_id: uuid.UUID,
    caller_user_id: int,
    member_user_id: int | None,
) -> int:
    """Decide whose data the caller is allowed to read in a team view.

    Members only ever see their own. The owner can pass an explicit
    ``member_user_id`` to drill into a teammate's CRM; everyone else
    gets a 403 if they try the same.
    """
    caller = await _membership(session, team_id, caller_user_id)
    if caller is None:
        raise HTTPException(status_code=403, detail="not a team member")

    if member_user_id is None or member_user_id == caller_user_id:
        return caller_user_id

    if not _can_manage_members(caller.role):
        raise HTTPException(
            status_code=403,
            detail="only owner or admin can view another member",
        )
    target = await _membership(session, team_id, member_user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="that user isn't a team member")
    return member_user_id


async def _team_prior_searches(
    session,
    team_id: uuid.UUID,
    niche: str,
    region: str,
) -> list[PriorTeamSearch]:
    """Return earlier completed searches in this team that already
    used the same (niche, region) pair, normalised case-insensitively
    and trimmed. Empty list = combo is fresh, OK to launch.
    """
    n = (niche or "").strip().lower()
    r = (region or "").strip().lower()
    if not n or not r:
        return []

    rows = (
        await session.execute(
            select(SearchQuery, User)
            .join(User, User.id == SearchQuery.user_id)
            .where(SearchQuery.team_id == team_id)
            .where(func.lower(func.trim(SearchQuery.niche)) == n)
            .where(func.lower(func.trim(SearchQuery.region)) == r)
            .where(SearchQuery.status.in_(["running", "done", "pending"]))
            .order_by(SearchQuery.created_at.desc())
        )
    ).all()

    out: list[PriorTeamSearch] = []
    for sq, user in rows:
        display = (
            user.display_name
            or " ".join(filter(None, [user.first_name, user.last_name]))
            or f"User {user.id}"
        )
        out.append(
            PriorTeamSearch(
                search_id=sq.id,
                user_id=sq.user_id,
                user_name=display,
                niche=sq.niche,
                region=sq.region,
                leads_count=sq.leads_count,
                created_at=sq.created_at,
            )
        )
    return out


def _status_to_schema(row: LeadStatus) -> LeadStatusSchema:
    return LeadStatusSchema(
        id=row.id,
        key=row.key,
        label=row.label,
        color=row.color,
        order_index=row.order_index,
        is_terminal=row.is_terminal,
    )


# ``_membership`` and ``_can_manage_tag`` were lifted into
# ``routes/_helpers.py`` so the extracted route modules don't import
# back into this file (which would be a cycle). The module-level
# aliases keep the rest of ``app.py`` working unchanged.
from leadgen.adapters.web_api.routes._helpers import (  # noqa: E402
    membership as _membership,
)


async def _team_detail(
    session, team: Team, viewer_user_id: int
) -> TeamDetailResponse:
    membership = await _membership(session, team.id, viewer_user_id)
    if membership is None:
        raise HTTPException(status_code=403, detail="not a team member")

    rows = (
        await session.execute(
            select(TeamMembership, User)
            .join(User, User.id == TeamMembership.user_id)
            .where(TeamMembership.team_id == team.id)
            .order_by(TeamMembership.created_at)
        )
    ).all()

    members: list[TeamMemberResponse] = []
    for i, (m, user) in enumerate(rows):
        display = (
            user.display_name
            or " ".join(filter(None, [user.first_name, user.last_name]))
            or f"User {user.id}"
        )
        initials = "".join(
            part[:1].upper()
            for part in display.split()
            if part
        )[:2] or display[:1].upper()
        members.append(
            TeamMemberResponse(
                id=user.id,
                name=display,
                role=m.role,
                description=m.description,
                initials=initials,
                color=_DEMO_TEAM_COLORS[i % len(_DEMO_TEAM_COLORS)],
                email=None,
            )
        )

    return TeamDetailResponse(
        id=team.id,
        name=team.name,
        description=team.description,
        plan=team.plan,
        created_at=team.created_at,
        role=membership.role,
        members=members,
    )


def _to_profile(user: User) -> UserProfile:
    recovery = getattr(user, "recovery_email", None)
    return UserProfile(
        user_id=user.id,
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        display_name=user.display_name,
        age_range=user.age_range,
        gender=user.gender,
        business_size=user.business_size,
        profession=user.profession,
        service_description=user.service_description,
        home_region=user.home_region,
        niches=list(user.niches) if user.niches else None,
        language_code=user.language_code,
        calendly_url=user.calendly_url,
        onboarded=_is_onboarded(user),
        onboarding_tour_completed=user.onboarding_completed_at is not None,
        email=user.email,
        email_verified=user.email_verified_at is not None,
        recovery_email_masked=mask_email(recovery) if recovery else None,
        queries_used=int(user.queries_used or 0),
        queries_limit=int(user.queries_limit or 0),
    )


async def _summarise_and_store(
    user_id: int,
    team_id: uuid.UUID | None,
    history: list[dict[str, str]],
    user_profile: dict[str, Any] | None,
    existing_memories: list[dict[str, Any]],
) -> None:
    """Background task: distill the dialogue, persist summary + facts.

    Run from ``asyncio.create_task`` so the user-facing chat reply
    isn't blocked on the second LLM call. Failures are swallowed —
    memory is best-effort, the chat itself is the source of truth
    for the current turn.
    """
    try:
        analyzer = AIAnalyzer()
        result = await analyzer.summarize_session(
            history, user_profile, existing_memories=existing_memories
        )
        summary = result.get("summary")
        facts = result.get("facts") or []
        if not summary and not facts:
            return
        async with session_factory() as session:
            if summary:
                await record_memory(
                    session,
                    user_id,
                    team_id,
                    kind="summary",
                    content=summary,
                    meta={"messages": len(history)},
                )
            for fact in facts:
                await record_memory(
                    session,
                    user_id,
                    team_id,
                    kind="fact",
                    content=fact,
                )
            await prune_old(session, user_id, team_id)
            await session.commit()
    except Exception:  # noqa: BLE001
        logger.exception(
            "summarise_and_store failed for user_id=%s team=%s",
            user_id,
            team_id,
        )


# ── Henry confirm-before-write plumbing ─────────────────────────────

# The confirm/refuse keyword regexes (ru + uk + en) live in
# ``routes/_helpers.py`` — single source of truth. The alias keeps the
# legacy ``app.py`` name importable.
from leadgen.adapters.web_api.routes._helpers import (  # noqa: E402, F401, I001
    detect_confirmation as _detect_confirmation,
)


_PROFILE_FIELDS_WHITELIST = {
    "display_name",
    "age_range",
    "business_size",
    "service_description",
    "home_region",
    "niches",
}


async def _apply_pending_actions(
    session,
    user: User | None,
    team_context: dict[str, Any] | None,
    actions: list[PendingAction],
) -> list[PendingAction]:
    """Apply a list of confirmed actions, return what was applied.

    Each action is validated against the kind's whitelist and the
    caller's permissions (owner-only for team / member descriptions).
    Failures are logged and the action is silently skipped — the
    rest of the batch still goes through.
    """
    is_owner = bool(team_context and team_context.get("is_owner"))
    raw_team_id = (team_context or {}).get("team_id")
    team_id: uuid.UUID | None
    if isinstance(raw_team_id, uuid.UUID):
        team_id = raw_team_id
    elif isinstance(raw_team_id, str):
        try:
            team_id = uuid.UUID(raw_team_id)
        except ValueError:
            team_id = None
    else:
        team_id = None

    applied: list[PendingAction] = []
    profile_dirty = False

    for action in actions:
        try:
            kind = action.kind
            payload = action.payload or {}

            if kind == "profile_patch" and user is not None:
                changed = False
                for key, val in payload.items():
                    if key not in _PROFILE_FIELDS_WHITELIST:
                        continue
                    if key == "niches":
                        if isinstance(val, list):
                            cleaned = [
                                n.strip()
                                for n in val
                                if isinstance(n, str) and n.strip()
                            ]
                            user.niches = cleaned[:7] or None
                            changed = True
                    elif key == "service_description":
                        raw = (val or "").strip()
                        if raw:
                            user.service_description = raw
                            try:
                                user.profession = (
                                    await asyncio.wait_for(
                                        AIAnalyzer().normalize_profession(raw),
                                        timeout=8.0,
                                    )
                                ) or raw
                            except Exception:  # noqa: BLE001
                                logger.exception(
                                    "normalize_profession failed in apply"
                                )
                                user.profession = raw
                        else:
                            user.service_description = None
                            user.profession = None
                        changed = True
                    else:
                        text_val = val if val is None else str(val).strip() or None
                        setattr(user, key, text_val)
                        changed = True
                if changed:
                    profile_dirty = True
                    applied.append(action)

            elif (
                kind == "team_description"
                and is_owner
                and team_id is not None
            ):
                description = (payload.get("description") or "").strip() or None
                team = await session.get(Team, team_id)
                if team is not None:
                    team.description = (
                        description[:2000] if description else None
                    )
                    applied.append(action)

            elif (
                kind == "member_description"
                and is_owner
                and team_id is not None
            ):
                target_user_id = payload.get("user_id")
                description = (payload.get("description") or "").strip() or None
                if isinstance(target_user_id, int):
                    membership = await _membership(
                        session, team_id, target_user_id
                    )
                    if membership is not None:
                        membership.description = (
                            description[:1000] if description else None
                        )
                        applied.append(action)

            elif kind == "launch_search" and user is not None:
                niche = (payload.get("niche") or "").strip()
                region = (payload.get("region") or "").strip()
                if not niche or not region:
                    continue
                ideal_customer = (
                    payload.get("ideal_customer") or ""
                ).strip() or None
                exclusions = (payload.get("exclusions") or "").strip() or None
                # Compose the profession blob the search pipeline reads
                # exactly the way /app/search builds it.
                offer_parts: list[str] = []
                base_offer = (user.profession or user.service_description or "").strip()
                if base_offer:
                    offer_parts.append(base_offer)
                if ideal_customer:
                    offer_parts.append(f"Идеальный клиент: {ideal_customer}")
                if exclusions:
                    offer_parts.append(f"Исключения: {exclusions}")
                profession_blob = ". ".join(offer_parts) or None

                new_query = SearchQuery(
                    user_id=user.id,
                    team_id=team_id,
                    niche=niche[:256],
                    region=region[:256],
                    source="web",
                )
                session.add(new_query)
                try:
                    await session.commit()
                except Exception:  # noqa: BLE001
                    await session.rollback()
                    logger.exception(
                        "launch_search via Henry: insert failed (likely "
                        "duplicate niche+region in team)"
                    )
                    continue
                await session.refresh(new_query)

                user_profile_for_run: dict[str, Any] = {
                    "display_name": user.display_name or user.first_name,
                    "age_range": user.age_range,
                    "gender": user.gender,
                    "business_size": user.business_size,
                    "profession": profession_blob or user.profession,
                    "service_description": user.service_description,
                    "home_region": user.home_region,
                    "niches": list(user.niches or []),
                    "language_code": user.language_code,
                }

                # Try the queue first; fall through to inline runner if
                # Redis isn't configured. Same path /api/v1/searches uses.
                queued_id = await enqueue_search(
                    new_query.id,
                    chat_id=None,
                    user_profile=user_profile_for_run,
                )
                if not queued_id:
                    spawn(
                        _run_web_search_inline(
                            new_query.id, user_profile_for_run
                        ),
                        name=f"convioo-henry-search-{new_query.id}",
                    )

                # Echo the new search_id back into the payload so the
                # frontend can render a "Open session" CTA on the
                # applied-action card.
                applied_payload = dict(action.payload)
                applied_payload["search_id"] = str(new_query.id)
                applied.append(
                    PendingAction(
                        kind=action.kind,
                        summary=action.summary,
                        payload=applied_payload,
                    )
                )
        except Exception:  # noqa: BLE001
            logger.exception(
                "apply_pending_action failed for kind=%s", action.kind
            )
            continue

    if applied or profile_dirty:
        await session.commit()
    return applied


def _result_to_pending_actions(
    result: dict[str, Any], mode: str
) -> list[PendingAction]:
    """Translate Henry's raw JSON output to PendingAction items.

    The LLM still emits ``profile_suggestion`` / ``team_suggestion``
    in its JSON because those shapes are easy for the model to fill;
    this helper flattens them into the user-facing pending_actions
    list (one card per action) the frontend renders.
    """
    out: list[PendingAction] = []
    summary_text = (result.get("suggestion_summary") or "").strip()

    if mode == "personal":
        ps = result.get("profile_suggestion")
        if isinstance(ps, dict):
            cleaned = {
                k: v for k, v in ps.items() if k in _PROFILE_FIELDS_WHITELIST and v
            }
            if cleaned:
                out.append(
                    PendingAction(
                        kind="profile_patch",
                        summary=summary_text or "Записать в профиль",
                        payload=cleaned,
                    )
                )

    if mode == "team_owner":
        ts = result.get("team_suggestion")
        if isinstance(ts, dict):
            description = (ts.get("description") or "").strip()
            if description:
                out.append(
                    PendingAction(
                        kind="team_description",
                        summary=summary_text or "Записать описание команды",
                        payload={"description": description},
                    )
                )
            for md in ts.get("member_descriptions") or []:
                if (
                    isinstance(md, dict)
                    and isinstance(md.get("user_id"), int)
                    and (md.get("description") or "").strip()
                ):
                    out.append(
                        PendingAction(
                            kind="member_description",
                            summary=(
                                f"Записать описание для участника "
                                f"#{md['user_id']}"
                            ),
                            payload={
                                "user_id": md["user_id"],
                                "description": md["description"].strip(),
                            },
                        )
                    )

    # Henry-can-search: LLM emits ``search_request`` with the same
    # shape ``consult_search`` slot dict has. Personal mode only —
    # team mode launches go through the regular form.
    if mode == "personal":
        sr = result.get("search_request")
        if isinstance(sr, dict):
            niche = (sr.get("niche") or "").strip()
            region = (sr.get("region") or "").strip()
            if niche and region:
                payload: dict[str, Any] = {
                    "niche": niche,
                    "region": region,
                }
                ic = (sr.get("ideal_customer") or "").strip()
                if ic:
                    payload["ideal_customer"] = ic
                ex = (sr.get("exclusions") or "").strip()
                if ex:
                    payload["exclusions"] = ex
                out.append(
                    PendingAction(
                        kind="launch_search",
                        summary=f"Run search: {niche} in {region}",
                        payload=payload,
                    )
                )

    return out
