"""Miscellaneous API endpoints — stats, queue status, taxonomy lookups."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.routes._helpers import resolve_team_view
from leadgen.adapters.web_api.schemas import (
    CityEntryResponse,
    CityListResponse,
    DashboardStats,
    NicheTaxonomyEntry,
    NicheTaxonomyResponse,
)
from leadgen.db.models import Lead, SearchQuery, User
from leadgen.db.session import session_factory
from leadgen.queue import is_queue_enabled

router = APIRouter(tags=["misc"])


@router.get("/api/v1/stats", response_model=DashboardStats)
async def dashboard_stats(
    team_id: uuid.UUID | None = None,
    member_user_id: int | None = None,
    current_user: User = Depends(get_current_user),
) -> DashboardStats:
    user_id = current_user.id
    async with session_factory() as session:
        query_stmt = select(SearchQuery).where(SearchQuery.source == "web")
        lead_stmt = (
            select(Lead.score_ai)
            .join(SearchQuery, SearchQuery.id == Lead.query_id)
            .where(SearchQuery.source == "web")
        )
        if team_id is not None:
            target_user = await resolve_team_view(
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


@router.get("/api/v1/queue/status", include_in_schema=False)
async def queue_status() -> dict[str, bool]:
    return {"queue_enabled": is_queue_enabled()}


@router.get("/api/v1/niches", response_model=NicheTaxonomyResponse)
async def list_niches(
    q: str | None = Query(default=None, max_length=80),
    lang: str | None = Query(default=None, max_length=8),
    limit: int = Query(default=12, ge=1, le=50),
) -> NicheTaxonomyResponse:
    """Static taxonomy lookup for the search-form niche combobox."""
    from leadgen.data.niches import (
        DEFAULT_LANGUAGE,
        SUPPORTED_LANGUAGES,
    )
    from leadgen.data.niches import suggest as suggest_niches_taxonomy

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


@router.get("/api/v1/cities", response_model=CityListResponse)
async def list_cities(
    q: str | None = Query(default=None, max_length=80),
    country: str | None = Query(default=None, max_length=4),
    lang: str | None = Query(default=None, max_length=8),
    limit: int = Query(default=12, ge=1, le=50),
) -> CityListResponse:
    """Curated city catalogue for the search-form region combobox."""
    from leadgen.data.cities import suggest as suggest_cities

    language = (lang or "en").lower()
    matches = suggest_cities(q, country=country, language=language, limit=limit)
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
