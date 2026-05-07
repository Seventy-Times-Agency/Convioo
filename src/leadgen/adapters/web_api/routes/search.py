"""``/api/v1/searches/*`` — search creation, listing, search-leads."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select, update

from leadgen.adapters.web_api.auth import (
    enforce_rate_limit,
    request_ip,
)
from leadgen.adapters.web_api.routes._helpers import (
    marks_for_user,
    membership,
    resolve_team_view,
    run_web_search_inline,
    tags_by_lead,
    team_prior_searches,
    to_lead_response,
    to_summary,
)
from leadgen.adapters.web_api.routes._helpers import (
    temp as compute_temp,
)
from leadgen.adapters.web_api.schemas import (
    WEB_DEMO_USER_ID,
    LeadResponse,
    SearchCreate,
    SearchCreateResponse,
    SearchPreflightResponse,
    SearchSummary,
)
from leadgen.core.services import BillingService
from leadgen.db.models import (
    Lead,
    SearchQuery,
    User,
)
from leadgen.db.session import session_factory
from leadgen.queue import enqueue_search
from leadgen.utils.rate_limit import (
    search_ip_limiter,
    search_team_limiter,
    search_user_limiter,
)

router = APIRouter(tags=["search"])


@router.get(
    "/api/v1/searches/preflight",
    response_model=SearchPreflightResponse,
)
async def search_preflight(
    user_id: int,
    niche: str,
    region: str,
    team_id: uuid.UUID | None = None,
) -> SearchPreflightResponse:
    """Tell the UI whether this niche+region combo is safe to run."""
    if team_id is None:
        return SearchPreflightResponse(blocked=False, matches=[])
    async with session_factory() as session:
        m = await membership(session, team_id, user_id)
        if m is None:
            raise HTTPException(status_code=403, detail="not a team member")
        matches = await team_prior_searches(session, team_id, niche, region)
    return SearchPreflightResponse(blocked=bool(matches), matches=matches)


@router.post("/api/v1/searches", response_model=SearchCreateResponse)
async def create_search(
    body: SearchCreate, request: Request
) -> SearchCreateResponse:
    """Create a SearchQuery row + launch the pipeline."""
    ip = request_ip(request)
    enforce_rate_limit(
        search_user_limiter, f"user:{body.user_id}", retry_hint=300
    )
    if body.team_id is not None:
        enforce_rate_limit(
            search_team_limiter, f"team:{body.team_id}", retry_hint=300
        )
    enforce_rate_limit(
        search_ip_limiter, f"ip:{ip or '?'}", retry_hint=300
    )
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
        if (
            user is not None
            and user.id < 0
            and user.email is not None
            and user.email_verified_at is None
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Подтвердите email чтобы запускать поиски. "
                    "Ссылка отправлена на " + (user.email or "ваш ящик") + "."
                ),
            )

        team_id = body.team_id
        if team_id is not None:
            m = await membership(session, team_id, body.user_id)
            if m is None:
                raise HTTPException(
                    status_code=403,
                    detail="user is not a member of this team",
                )
            prior = await team_prior_searches(
                session, team_id, body.niche, body.region
            )
            if prior:
                first = prior[0]
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"This niche+region was already searched in this "
                        f"team by {first.user_name} on "
                        f"{first.created_at:%Y-%m-%d} "
                        f"({first.leads_count} leads). Pick a different "
                        f"angle so two members don't chase the same companies."
                    ),
                )

        scope = (body.scope or "city").strip().lower()
        if scope not in {"city", "metro", "state", "country"}:
            scope = "city"
        radius_m_value: int | None = None
        if scope in {"city", "metro"} and body.radius_km is not None:
            radius_m_value = max(0, min(int(body.radius_km), 100)) * 1000

        allowed_sources = {"google", "osm", "yelp", "foursquare"}
        enabled_sources_value: list[str] | None = None
        if body.enabled_sources:
            enabled_sources_value = sorted(
                {
                    s.strip().lower()
                    for s in body.enabled_sources
                    if s.strip().lower() in allowed_sources
                }
            ) or None

        stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
        await session.execute(
            update(SearchQuery)
            .where(
                SearchQuery.user_id == body.user_id,
                SearchQuery.status.in_(("pending", "running")),
                SearchQuery.created_at < stale_cutoff,
            )
            .values(
                status="failed",
                error="auto-failed: stale active search reclaimed",
            )
        )

        query = SearchQuery(
            user_id=body.user_id,
            team_id=team_id,
            niche=body.niche,
            region=body.region,
            target_languages=(
                list(body.target_languages)
                if body.target_languages
                else None
            ),
            max_results=(
                int(body.limit) if body.limit is not None else None
            ),
            scope=scope,
            radius_m=radius_m_value,
            enabled_sources=enabled_sources_value,
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

    user_profile: dict[str, Any] = {}
    if user is not None:
        user_profile = {
            "display_name": user.display_name or user.first_name,
            "age_range": user.age_range,
            "gender": user.gender,
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
        asyncio.create_task(
            run_web_search_inline(query.id, user_profile or None),
            name=f"convioo-web-search-{query.id}",
        )

    return SearchCreateResponse(id=query.id, queued=queued)


@router.get("/api/v1/searches", response_model=list[SearchSummary])
async def list_searches(
    user_id: int = WEB_DEMO_USER_ID,
    team_id: uuid.UUID | None = None,
    member_user_id: int | None = None,
    limit: int = 50,
) -> list[SearchSummary]:
    """List searches for a workspace."""
    limit = max(1, min(limit, 200))
    async with session_factory() as session:
        stmt = (
            select(SearchQuery)
            .order_by(SearchQuery.created_at.desc())
            .limit(limit)
        )
        if team_id is not None:
            target_user = await resolve_team_view(
                session, team_id, user_id, member_user_id
            )
            stmt = stmt.where(SearchQuery.team_id == team_id).where(
                SearchQuery.user_id == target_user
            )
        else:
            stmt = stmt.where(SearchQuery.user_id == user_id).where(
                SearchQuery.team_id.is_(None)
            )
        result = await session.execute(stmt)
        return [to_summary(row) for row in result.scalars().all()]


@router.get("/api/v1/searches/{search_id}", response_model=SearchSummary)
async def get_search(search_id: uuid.UUID) -> SearchSummary:
    async with session_factory() as session:
        query = await session.get(SearchQuery, search_id)
        if query is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="search not found"
            )
        return to_summary(query)


@router.get(
    "/api/v1/searches/{search_id}/leads", response_model=list[LeadResponse]
)
async def list_search_leads(
    search_id: uuid.UUID,
    temp: str | None = None,
    user_id: int = WEB_DEMO_USER_ID,
) -> list[LeadResponse]:
    """All leads for one search."""
    async with session_factory() as session:
        result = await session.execute(
            select(Lead)
            .where(Lead.query_id == search_id)
            .where(Lead.deleted_at.is_(None))
            .order_by(Lead.score_ai.desc().nullslast(), Lead.rating.desc().nullslast())
        )
        leads = list(result.scalars().all())
        lead_ids = [lead.id for lead in leads]
        marks = await marks_for_user(session, user_id, lead_ids)
        tags_map = await tags_by_lead(session, lead_ids)

    if temp in {"hot", "warm", "cold"}:
        leads = [lead for lead in leads if compute_temp(lead.score_ai) == temp]
    return [
        to_lead_response(
            lead, marks.get(lead.id), tags_map.get(lead.id)
        )
        for lead in leads
    ]
