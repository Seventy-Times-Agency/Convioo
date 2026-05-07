"""``/api/v1/search/consult``, ``/api/v1/assistant/*`` — Henry chat,
memory, niche / axis suggestions, weekly checkin, decision-maker
enrichment, CSV import.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from leadgen.adapters.web_api.auth import (
    enforce_rate_limit,
    get_current_user,
)
from leadgen.adapters.web_api.routes._helpers import (
    apply_pending_actions,
    detect_confirmation,
    membership,
    resolve_team_view,
    result_to_pending_actions,
    summarise_and_store,
)
from leadgen.adapters.web_api.schemas import (
    WEB_DEMO_USER_ID,
    AssistantMemoryDeleteResponse,
    AssistantMemoryItem,
    AssistantMemoryListResponse,
    AssistantRequest,
    AssistantResponse,
    ConsultRequest,
    ConsultResponse,
    CsvImportRequest,
    CsvImportResponse,
    DecisionMaker,
    DecisionMakersResponse,
    NicheSuggestionsResponse,
    SearchAxesResponse,
    SearchAxisOption,
    WeeklyCheckinResponse,
)
from leadgen.analysis.ai_analyzer import AIAnalyzer
from leadgen.core.services.assistant_memory import (
    load_memories,
    should_summarise,
)
from leadgen.db.models import (
    AssistantMemory,
    Lead,
    LeadActivity,
    LeadCustomField,
    SearchQuery,
    Team,
    TeamMembership,
    User,
)
from leadgen.db.session import session_factory
from leadgen.utils.rate_limit import (
    assistant_team_limiter,
    assistant_user_limiter,
)

router = APIRouter(tags=["assistant"])


# ── /api/v1/search/consult ─────────────────────────────────────────


@router.post("/api/v1/search/consult", response_model=ConsultResponse)
async def search_consult(body: ConsultRequest) -> ConsultResponse:
    """One turn of the search-composer dialogue."""
    async with session_factory() as session:
        user = await session.get(User, body.user_id)

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

    history = [m.model_dump() for m in body.messages]
    current_state = {
        "niche": body.current_niche,
        "region": body.current_region,
        "ideal_customer": body.current_ideal_customer,
        "exclusions": body.current_exclusions,
    }
    analyzer = AIAnalyzer()
    result = await analyzer.consult_search(
        history,
        user_profile or None,
        current_state=current_state,
        last_asked_slot=body.last_asked_slot,
    )
    return ConsultResponse(**result)


# ── /api/v1/assistant/chat ─────────────────────────────────────────


@router.post("/api/v1/assistant/chat", response_model=AssistantResponse)
async def assistant_chat(body: AssistantRequest) -> AssistantResponse:
    """Floating in-product assistant — Henry, confirm-before-write."""
    enforce_rate_limit(
        assistant_user_limiter, f"user:{body.user_id}", retry_hint=60
    )
    if body.team_id is not None:
        enforce_rate_limit(
            assistant_team_limiter, f"team:{body.team_id}", retry_hint=60
        )
    team_context: dict[str, Any] | None = None
    async with session_factory() as session:
        if body.team_id is not None:
            team = await session.get(Team, body.team_id)
            if team is None:
                raise HTTPException(status_code=404, detail="team not found")
            m = await membership(
                session, body.team_id, body.user_id
            )
            if m is None:
                raise HTTPException(
                    status_code=403, detail="not a team member"
                )
            rows = (
                await session.execute(
                    select(TeamMembership, User)
                    .join(User, User.id == TeamMembership.user_id)
                    .where(TeamMembership.team_id == body.team_id)
                    .order_by(TeamMembership.created_at)
                )
            ).all()
            members_payload: list[dict[str, Any]] = []
            for mem, u in rows:
                display = (
                    u.display_name
                    or " ".join(filter(None, [u.first_name, u.last_name]))
                    or f"User {u.id}"
                )
                members_payload.append(
                    {
                        "user_id": u.id,
                        "name": display,
                        "role": mem.role,
                        "description": mem.description,
                    }
                )
            viewer = await session.get(User, body.user_id)
            team_context = {
                "team_id": str(team.id),
                "name": team.name,
                "description": team.description,
                "is_owner": m.role == "owner",
                "viewer_user_id": body.user_id,
                "viewer_language_code": viewer.language_code if viewer else None,
                "members": members_payload,
            }

    is_team = bool(team_context)
    is_owner = bool(team_context and team_context.get("is_owner"))
    mode = (
        "team_owner" if is_owner else "team_member" if is_team else "personal"
    )

    last_user_text = ""
    for m in reversed(body.messages):
        if m.role == "user":
            last_user_text = m.content.strip()
            break

    if body.pending_actions and last_user_text:
        verdict = detect_confirmation(last_user_text)
        if verdict == "confirm":
            async with session_factory() as session:
                user = await session.get(User, body.user_id)
                applied = await apply_pending_actions(
                    session, user, team_context, body.pending_actions
                )
            if applied:
                return AssistantResponse(
                    reply="Готово — записал. Что-то ещё?",
                    mode=mode,
                    applied_actions=applied,
                    awaiting_field=None,
                )
        elif verdict == "refuse":
            return AssistantResponse(
                reply="Понял, не записываю. Что поправить?",
                mode=mode,
                pending_actions=None,
                awaiting_field=body.awaiting_field,
            )

    async with session_factory() as session:
        user = await session.get(User, body.user_id)
        memories = await load_memories(
            session, body.user_id, body.team_id
        )

    user_profile: dict[str, Any] = {}
    if user is not None:
        if body.team_id is None:
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
        else:
            user_profile = {
                "display_name": user.display_name or user.first_name,
                "gender": user.gender,
                "language_code": user.language_code,
            }

    history = [m.model_dump() for m in body.messages]
    analyzer = AIAnalyzer()
    result = await analyzer.assistant_chat(
        history,
        user_profile or None,
        team_context=team_context,
        awaiting_field=body.awaiting_field,
        memories=memories,
    )

    pending = result_to_pending_actions(result, mode)

    if should_summarise(history):
        asyncio.create_task(
            summarise_and_store(
                body.user_id,
                body.team_id,
                history,
                user_profile or None,
                memories,
            )
        )

    return AssistantResponse(
        reply=result.get("reply", ""),
        mode=mode,
        suggestion_summary=result.get("suggestion_summary"),
        awaiting_field=result.get("awaiting_field"),
        pending_actions=pending or None,
    )


# ── /api/v1/assistant/memory ───────────────────────────────────────


@router.get(
    "/api/v1/users/me/assistant-memory",
    response_model=AssistantMemoryListResponse,
)
async def list_assistant_memory(
    team_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
) -> AssistantMemoryListResponse:
    """Surface what Henry remembers about this user."""
    user_id = current_user.id
    async with session_factory() as session:
        stmt = select(AssistantMemory).where(
            AssistantMemory.user_id == user_id
        )
        if team_id is not None:
            stmt = stmt.where(
                (AssistantMemory.team_id == team_id)
                | (AssistantMemory.team_id.is_(None))
            )
        else:
            stmt = stmt.where(AssistantMemory.team_id.is_(None))
        stmt = stmt.order_by(AssistantMemory.created_at.desc()).limit(50)
        rows = (await session.execute(stmt)).scalars().all()
        items = [
            AssistantMemoryItem(
                id=row.id,
                kind=row.kind,
                content=row.content,
                team_id=row.team_id,
                created_at=row.created_at,
            )
            for row in rows
        ]
    return AssistantMemoryListResponse(items=items)


@router.delete(
    "/api/v1/users/me/assistant-memory",
    response_model=AssistantMemoryDeleteResponse,
)
async def clear_assistant_memory(
    team_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
) -> AssistantMemoryDeleteResponse:
    """Wipe Henry's memory for this user (and optionally for a team)."""
    user_id = current_user.id
    async with session_factory() as session:
        stmt = select(AssistantMemory).where(
            AssistantMemory.user_id == user_id
        )
        if team_id is None:
            stmt = stmt.where(AssistantMemory.team_id.is_(None))
        else:
            stmt = stmt.where(
                (AssistantMemory.team_id == team_id)
                | (AssistantMemory.team_id.is_(None))
            )
        rows = (await session.execute(stmt)).scalars().all()
        for row in rows:
            await session.delete(row)
        await session.commit()
    return AssistantMemoryDeleteResponse(deleted=len(rows))


@router.post(
    "/api/v1/search/suggest-axes",
    response_model=SearchAxesResponse,
)
async def suggest_search_axes(user_id: int) -> SearchAxesResponse:
    """Henry-proposed ready-to-launch search configurations."""
    async with session_factory() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")
        profile_dict = {
            "service_description": user.service_description,
            "profession": user.profession,
            "home_region": user.home_region,
            "business_size": user.business_size,
            "niches": list(user.niches or []),
        }
    analyzer = AIAnalyzer()
    options = await analyzer.suggest_search_axes(
        profile_dict, max_results=4
    )
    return SearchAxesResponse(
        options=[SearchAxisOption(**o) for o in options]
    )


@router.get(
    "/api/v1/users/me/weekly-checkin",
    response_model=WeeklyCheckinResponse,
)
async def weekly_checkin(
    team_id: uuid.UUID | None = None,
    member_user_id: int | None = None,
    current_user: User = Depends(get_current_user),
) -> WeeklyCheckinResponse:
    """Henry's short read on the user's recent CRM activity."""
    user_id = current_user.id
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    cutoff_14 = now - timedelta(days=14)

    async with session_factory() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")

        if team_id is not None:
            target_user = await resolve_team_view(
                session, team_id, user_id, member_user_id
            )
            lead_filter = (
                (SearchQuery.team_id == team_id)
                & (SearchQuery.user_id == target_user)
            )
            session_filter = lead_filter
        else:
            lead_filter = (
                (SearchQuery.user_id == user_id)
                & (SearchQuery.team_id.is_(None))
            )
            session_filter = lead_filter

        base_lead_q = (
            select(func.count(Lead.id))
            .join(SearchQuery, SearchQuery.id == Lead.query_id)
            .where(SearchQuery.source == "web")
            .where(lead_filter)
        )
        leads_total = int(
            (await session.execute(base_lead_q)).scalar() or 0
        )
        hot_total = int(
            (
                await session.execute(
                    base_lead_q.where(Lead.score_ai >= 75)
                )
            ).scalar()
            or 0
        )
        warm_total = int(
            (
                await session.execute(
                    base_lead_q.where(Lead.score_ai >= 50).where(
                        Lead.score_ai < 75
                    )
                )
            ).scalar()
            or 0
        )
        cold_total = max(leads_total - hot_total - warm_total, 0)
        new_this_week = int(
            (
                await session.execute(
                    base_lead_q.where(Lead.created_at >= week_ago)
                )
            ).scalar()
            or 0
        )
        untouched_14d = int(
            (
                await session.execute(
                    base_lead_q.where(
                        (Lead.last_touched_at < cutoff_14)
                        | (Lead.last_touched_at.is_(None))
                    )
                    .where(Lead.lead_status != "won")
                    .where(Lead.lead_status != "archived")
                )
            ).scalar()
            or 0
        )
        sessions_this_week = int(
            (
                await session.execute(
                    select(func.count(SearchQuery.id))
                    .where(SearchQuery.source == "web")
                    .where(session_filter)
                    .where(SearchQuery.created_at >= week_ago)
                )
            ).scalar()
            or 0
        )
        last_session_row = (
            await session.execute(
                select(SearchQuery.created_at)
                .where(SearchQuery.source == "web")
                .where(session_filter)
                .order_by(SearchQuery.created_at.desc())
                .limit(1)
            )
        ).first()
        last_session_at = (
            last_session_row[0].isoformat()
            if last_session_row
            else None
        )

        user_profile_dict: dict[str, Any] = {
            "display_name": user.display_name or user.first_name,
            "gender": user.gender,
            "profession": user.profession,
            "service_description": user.service_description,
            "home_region": user.home_region,
            "niches": list(user.niches or []),
            "language_code": user.language_code,
        }

    stats = {
        "leads_total": leads_total,
        "hot_total": hot_total,
        "warm_total": warm_total,
        "cold_total": cold_total,
        "new_this_week": new_this_week,
        "untouched_14d": untouched_14d,
        "sessions_this_week": sessions_this_week,
        "last_session_at": last_session_at,
    }

    analyzer = AIAnalyzer()
    result = await analyzer.weekly_checkin(stats, user_profile_dict)

    return WeeklyCheckinResponse(
        summary=result.get("summary", ""),
        highlights=result.get("highlights", []),
        leads_total=leads_total,
        hot_total=hot_total,
        new_this_week=new_this_week,
        untouched_14d=untouched_14d,
        sessions_this_week=sessions_this_week,
    )


@router.post(
    "/api/v1/leads/{lead_id}/enrich/decision-makers",
    response_model=DecisionMakersResponse,
)
async def enrich_decision_makers(
    lead_id: uuid.UUID,
    user_id: int = WEB_DEMO_USER_ID,
) -> DecisionMakersResponse:
    """Henry pulls decision-maker contacts from the lead's site."""
    async with session_factory() as session:
        lead = await session.get(Lead, lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="lead not found")
        website = (lead.website or "").strip()

    if not website:
        return DecisionMakersResponse(items=[])

    analyzer = AIAnalyzer()
    people = await analyzer.extract_decision_makers(website)
    if not people:
        return DecisionMakersResponse(items=[])

    async with session_factory() as session:
        now = datetime.now(timezone.utc)
        for idx, p in enumerate(people, start=1):
            key = f"decision_maker_{idx}"
            value_parts = [p["name"]]
            if p.get("role"):
                value_parts.append(p["role"])
            if p.get("email"):
                value_parts.append(p["email"])
            if p.get("linkedin"):
                value_parts.append(p["linkedin"])
            value = " · ".join(value_parts)
            existing = (
                await session.execute(
                    select(LeadCustomField)
                    .where(LeadCustomField.lead_id == lead_id)
                    .where(LeadCustomField.user_id == user_id)
                    .where(LeadCustomField.key == key)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    LeadCustomField(
                        lead_id=lead_id,
                        user_id=user_id,
                        key=key,
                        value=value,
                    )
                )
            else:
                existing.value = value
                existing.updated_at = now
        session.add(
            LeadActivity(
                lead_id=lead_id,
                user_id=user_id,
                team_id=None,
                kind="custom_field",
                payload={
                    "key": "decision_makers",
                    "count": len(people),
                },
            )
        )
        await session.commit()

    return DecisionMakersResponse(
        items=[DecisionMaker(**p) for p in people]
    )


@router.post(
    "/api/v1/searches/import-csv",
    response_model=CsvImportResponse,
)
async def import_search_csv(body: CsvImportRequest) -> CsvImportResponse:
    """Bulk-import a list of companies as a synthetic search session."""
    if body.team_id is not None:
        async with session_factory() as session:
            m = await membership(
                session, body.team_id, body.user_id
            )
            if m is None:
                raise HTTPException(
                    status_code=403, detail="not a team member"
                )

    async with session_factory() as session:
        parent_region = ""
        for row in body.rows:
            if row.region and row.region.strip():
                parent_region = row.region.strip()
                break
        if not parent_region:
            parent_region = "—"

        search = SearchQuery(
            user_id=body.user_id,
            team_id=body.team_id,
            niche=body.label[:256],
            region=parent_region[:256],
            source="web",
            status="done",
            finished_at=datetime.now(timezone.utc),
        )
        session.add(search)
        try:
            await session.commit()
        except Exception:  # noqa: BLE001
            await session.rollback()
            raise HTTPException(
                status_code=500,
                detail="failed to create CSV import session",
            ) from None
        await session.refresh(search)

        inserted = 0
        skipped = 0
        for idx, row in enumerate(body.rows):
            name = row.name.strip()
            if not name:
                skipped += 1
                continue
            source_id = f"csv-{search.id}-{idx}"
            lead = Lead(
                query_id=search.id,
                name=name[:512],
                website=(row.website or None),
                phone=(row.phone or None),
                address=(row.region or None),
                category=(row.category or None),
                source="csv",
                source_id=source_id,
                raw={"csv_index": idx, "extras": dict(row.extras)},
            )
            session.add(lead)
            try:
                await session.flush()
            except Exception:  # noqa: BLE001
                await session.rollback()
                skipped += 1
                continue

            for k, v in (row.extras or {}).items():
                cleaned_key = (k or "").strip()[:64]
                cleaned_val = (v or "").strip()
                if not cleaned_key:
                    continue
                session.add(
                    LeadCustomField(
                        lead_id=lead.id,
                        user_id=body.user_id,
                        key=cleaned_key,
                        value=cleaned_val[:2000] or None,
                    )
                )

            session.add(
                LeadActivity(
                    lead_id=lead.id,
                    user_id=body.user_id,
                    team_id=body.team_id,
                    kind="created",
                    payload={"source": "csv"},
                )
            )
            inserted += 1

        search.leads_count = inserted
        await session.commit()

    return CsvImportResponse(
        search_id=search.id,
        inserted=inserted,
        skipped=skipped,
    )


@router.post(
    "/api/v1/users/me/suggest-niches",
    response_model=NicheSuggestionsResponse,
)
async def suggest_niches(
    current_user: User = Depends(get_current_user),
) -> NicheSuggestionsResponse:
    """Henry-proposed target niches based on the user's offer."""
    user_id = current_user.id
    async with session_factory() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")
        profile_dict = {
            "service_description": user.service_description,
            "profession": user.profession,
            "home_region": user.home_region,
            "business_size": user.business_size,
        }
        existing = list(user.niches or [])

    analyzer = AIAnalyzer()
    suggestions = await analyzer.suggest_niches(
        profile_dict, existing=existing, max_results=8
    )
    return NicheSuggestionsResponse(suggestions=suggestions)
