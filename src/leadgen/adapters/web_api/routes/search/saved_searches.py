"""``/api/v1/saved-searches/*`` — bookmarked + scheduled re-run searches."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.schemas import (
    SavedSearchCreate,
    SavedSearchListResponse,
    SavedSearchSchema,
    SavedSearchUpdate,
    SearchCreate,
    SearchCreateResponse,
)
from leadgen.db.models import SavedSearch, TeamMembership, User
from leadgen.db.session import session_factory

logger = logging.getLogger(__name__)

router = APIRouter(tags=["saved_searches"])


def _saved_to_schema(row: SavedSearch) -> SavedSearchSchema:
    return SavedSearchSchema(
        id=str(row.id),
        name=row.name,
        team_id=str(row.team_id) if row.team_id else None,
        niche=row.niche,
        region=row.region,
        target_languages=row.target_languages,
        scope=row.scope,
        radius_m=row.radius_m,
        max_results=row.max_results,
        schedule=row.schedule,
        next_run_at=row.next_run_at,
        last_run_at=row.last_run_at,
        last_leads_count=row.last_leads_count,
        active=row.active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _normalize_schedule(raw: str | None) -> str | None:
    """Map ``"off"`` and the empty string onto ``None`` so the
    worker query can ``WHERE schedule IS NOT NULL`` cleanly."""
    if not raw:
        return None
    value = raw.strip().lower()
    if value in ("off", "none", "manual", ""):
        return None
    from leadgen.core.services.search.saved_searches import VALID_SCHEDULES

    if value not in VALID_SCHEDULES:
        raise HTTPException(
            status_code=400,
            detail=(
                "schedule must be one of off / daily / weekly / "
                "biweekly / monthly"
            ),
        )
    return value


# Поля, которые живут в своих колонках SavedSearch, а не в launch_params.
_OWN_COLUMNS = {"niche", "region", "team_id", "target_languages", "limit", "scope", "radius_km"}


def _clean_launch_params(raw: dict | None, *, niche: str, region: str) -> dict | None:
    """Проверить параметры по схеме запуска и сохранить без дублей."""
    if not raw:
        return None
    try:
        body = SearchCreate.model_validate({**raw, "niche": niche, "region": region})
    except Exception as exc:  # noqa: BLE001 - pydantic ValidationError
        raise HTTPException(status_code=422, detail=f"invalid launch_params: {exc}") from exc
    return body.model_dump(mode="json", exclude_none=True, exclude=_OWN_COLUMNS) or None


def search_body_from_saved(saved: SavedSearch) -> SearchCreate:
    """Тело запуска для повтора: свои колонки + сохранённые параметры."""
    radius_km = saved.radius_m // 1000 if saved.radius_m else None
    return SearchCreate.model_validate(
        {
            **(saved.launch_params or {}),
            "niche": saved.niche,
            "region": saved.region,
            "team_id": str(saved.team_id) if saved.team_id else None,
            "target_languages": saved.target_languages,
            "limit": saved.max_results,
            "scope": saved.scope,
            "radius_km": radius_km,
        }
    )


async def run_saved_search(saved: SavedSearch) -> SearchCreateResponse:
    """Запустить сохранённый поиск тем же путём, что и кнопка «Найти»."""
    from leadgen.adapters.web_api.routes.search.search import start_search

    async with session_factory() as session:
        user = await session.get(User, saved.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="owner not found")
    return await start_search(user, search_body_from_saved(saved), repeat=True)


@router.get(
    "/api/v1/saved-searches",
    response_model=SavedSearchListResponse,
)
async def list_saved_searches(
    current_user: User = Depends(get_current_user),
) -> SavedSearchListResponse:
    async with session_factory() as session:
        team_ids = (
            (
                await session.execute(
                    select(TeamMembership.team_id).where(
                        TeamMembership.user_id == current_user.id
                    )
                )
            )
            .scalars()
            .all()
        )
        stmt = (
            select(SavedSearch)
            .where(
                sa.or_(
                    sa.and_(
                        SavedSearch.user_id == current_user.id,
                        SavedSearch.team_id.is_(None),
                    ),
                    SavedSearch.team_id.in_(team_ids)
                    if team_ids
                    else sa.false(),
                )
            )
            .order_by(SavedSearch.created_at.desc())
        )
        rows = (await session.execute(stmt)).scalars().all()
    return SavedSearchListResponse(
        items=[_saved_to_schema(r) for r in rows]
    )


@router.post(
    "/api/v1/saved-searches",
    response_model=SavedSearchSchema,
)
async def create_saved_search(
    body: SavedSearchCreate,
    current_user: User = Depends(get_current_user),
) -> SavedSearchSchema:
    from leadgen.core.services.search.saved_searches import (
        next_run_after,
    )

    team_uuid: uuid.UUID | None = None
    if body.team_id:
        try:
            team_uuid = uuid.UUID(body.team_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="invalid team_id"
            ) from exc

    schedule = _normalize_schedule(body.schedule)
    async with session_factory() as session:
        if team_uuid is not None:
            membership = (
                await session.execute(
                    select(TeamMembership)
                    .where(TeamMembership.user_id == current_user.id)
                    .where(TeamMembership.team_id == team_uuid)
                )
            ).scalar_one_or_none()
            if membership is None:
                raise HTTPException(
                    status_code=403, detail="not a team member"
                )
            from leadgen.core.services.account.team_permissions import can_run_search

            # Scheduled prospecting is still prospecting — manager+.
            if not can_run_search(membership.role):
                raise HTTPException(
                    status_code=403,
                    detail="your role can't schedule searches in this team",
                )
        row = SavedSearch(
            user_id=current_user.id,
            team_id=team_uuid,
            name=body.name.strip(),
            niche=body.niche.strip(),
            region=body.region.strip(),
            target_languages=body.target_languages,
            scope=body.scope,
            radius_m=body.radius_m,
            max_results=body.max_results,
            schedule=schedule,
            launch_params=_clean_launch_params(
                body.launch_params, niche=body.niche.strip(), region=body.region.strip()
            ),
            next_run_at=next_run_after(schedule)
            if schedule
            else None,
            active=True,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return _saved_to_schema(row)


@router.patch(
    "/api/v1/saved-searches/{saved_id}",
    response_model=SavedSearchSchema,
)
async def update_saved_search(
    saved_id: uuid.UUID,
    body: SavedSearchUpdate,
    current_user: User = Depends(get_current_user),
) -> SavedSearchSchema:
    from leadgen.core.services.search.saved_searches import (
        next_run_after,
    )

    async with session_factory() as session:
        row = await session.get(SavedSearch, saved_id)
        if row is None or row.user_id != current_user.id:
            raise HTTPException(
                status_code=404, detail="saved search not found"
            )
        if body.name is not None:
            row.name = body.name.strip()
        if body.schedule is not None:
            row.schedule = _normalize_schedule(body.schedule)
            row.next_run_at = (
                next_run_after(row.schedule) if row.schedule else None
            )
        if body.active is not None:
            row.active = body.active
        if body.max_results is not None:
            row.max_results = body.max_results
        if body.radius_m is not None:
            row.radius_m = body.radius_m
        row.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(row)
    return _saved_to_schema(row)


@router.delete("/api/v1/saved-searches/{saved_id}")
async def delete_saved_search(
    saved_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    async with session_factory() as session:
        row = await session.get(SavedSearch, saved_id)
        if row is None or row.user_id != current_user.id:
            raise HTTPException(
                status_code=404, detail="saved search not found"
            )
        await session.delete(row)
        await session.commit()
    return {"ok": True}


@router.post(
    "/api/v1/saved-searches/{saved_id}/run",
    response_model=SearchCreateResponse,
)
async def run_saved_search_now(
    saved_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> SearchCreateResponse:
    """Manually trigger a saved search outside its schedule.

    Useful for the "Run now" button next to each saved search row.
    Reuses the same enqueue plumbing that ``POST /searches`` does so
    the SSE progress stream and the CRM lead-list are identical.
    """
    async with session_factory() as session:
        row = await session.get(SavedSearch, saved_id)
        if row is None or row.user_id != current_user.id:
            raise HTTPException(
                status_code=404, detail="saved search not found"
            )
        row.last_run_at = datetime.now(timezone.utc)
        await session.commit()
    return await run_saved_search(row)
