"""``/api/v1/teams/*`` — team CRUD, invites, membership management."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from leadgen.adapters.web_api.routes._helpers import (
    invite_expired,
    load_invite,
    membership,
    seed_default_lead_statuses,
    team_detail,
)
from leadgen.adapters.web_api.schemas import (
    InviteAcceptRequest,
    InviteCreateRequest,
    InvitePreview,
    InviteResponse,
    MembershipUpdateRequest,
    TeamCreateRequest,
    TeamDetailResponse,
    TeamSummary,
    TeamUpdateRequest,
)
from leadgen.db.models import (
    Team,
    TeamInvite,
    TeamMembership,
    User,
)
from leadgen.db.session import session_factory

router = APIRouter(tags=["teams"])


@router.post("/api/v1/teams", response_model=TeamDetailResponse)
async def create_team(body: TeamCreateRequest) -> TeamDetailResponse:
    async with session_factory() as session:
        owner = await session.get(User, body.owner_user_id)
        if owner is None:
            raise HTTPException(status_code=404, detail="owner not found")

        team = Team(name=body.name.strip(), plan="free")
        session.add(team)
        await session.flush()
        session.add(
            TeamMembership(user_id=owner.id, team_id=team.id, role="owner")
        )
        seed_default_lead_statuses(session, team.id)
        await session.commit()
        await session.refresh(team)

        return await team_detail(session, team, owner.id)


@router.get("/api/v1/teams", response_model=list[TeamSummary])
async def list_my_teams(user_id: int) -> list[TeamSummary]:
    async with session_factory() as session:
        stmt = (
            select(TeamMembership, Team)
            .join(Team, Team.id == TeamMembership.team_id)
            .where(TeamMembership.user_id == user_id)
            .order_by(Team.created_at.desc())
        )
        rows = (await session.execute(stmt)).all()

        results: list[TeamSummary] = []
        for m, team in rows:
            count = await session.scalar(
                select(func.count(TeamMembership.id)).where(
                    TeamMembership.team_id == team.id
                )
            )
            results.append(
                TeamSummary(
                    id=team.id,
                    name=team.name,
                    plan=team.plan,
                    role=m.role,
                    member_count=int(count or 0),
                    created_at=team.created_at,
                )
            )
        return results


@router.get("/api/v1/teams/{team_id}", response_model=TeamDetailResponse)
async def get_team(team_id: uuid.UUID, user_id: int) -> TeamDetailResponse:
    async with session_factory() as session:
        team = await session.get(Team, team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="team not found")
        return await team_detail(session, team, user_id)


@router.patch("/api/v1/teams/{team_id}", response_model=TeamDetailResponse)
async def update_team(
    team_id: uuid.UUID, body: TeamUpdateRequest
) -> TeamDetailResponse:
    """Owner-only PATCH for the team's name + description."""
    async with session_factory() as session:
        team = await session.get(Team, team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="team not found")
        m = await membership(session, team_id, body.by_user_id)
        if m is None or m.role != "owner":
            raise HTTPException(
                status_code=403,
                detail="only the team owner can edit the team",
            )

        data = body.model_dump(exclude_unset=True)
        if "name" in data and data["name"] is not None:
            trimmed = data["name"].strip()
            if trimmed:
                team.name = trimmed
        if "description" in data:
            desc = (data["description"] or "").strip()
            team.description = desc or None

        await session.commit()
        await session.refresh(team)
        return await team_detail(session, team, body.by_user_id)


@router.patch(
    "/api/v1/teams/{team_id}/members/{member_user_id}",
    response_model=TeamDetailResponse,
)
async def update_member(
    team_id: uuid.UUID,
    member_user_id: int,
    body: MembershipUpdateRequest,
) -> TeamDetailResponse:
    """Owner-only PATCH of a teammate's per-team description / role."""
    async with session_factory() as session:
        team = await session.get(Team, team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="team not found")
        caller = await membership(session, team_id, body.by_user_id)
        if caller is None or caller.role != "owner":
            raise HTTPException(
                status_code=403,
                detail="only the team owner can edit members",
            )
        target = await membership(session, team_id, member_user_id)
        if target is None:
            raise HTTPException(
                status_code=404, detail="that user isn't a team member"
            )

        data = body.model_dump(exclude_unset=True)
        if "description" in data:
            desc = (data["description"] or "").strip()
            target.description = desc or None
        if "role" in data and data["role"]:
            role_value = data["role"].strip()
            if (
                target.user_id == body.by_user_id
                and role_value != "owner"
            ):
                raise HTTPException(
                    status_code=400,
                    detail="owners can't demote themselves",
                )
            target.role = role_value

        await session.commit()
        return await team_detail(session, team, body.by_user_id)


@router.post("/api/v1/teams/{team_id}/invites", response_model=InviteResponse)
async def create_invite(
    team_id: uuid.UUID, body: InviteCreateRequest
) -> InviteResponse:
    async with session_factory() as session:
        team = await session.get(Team, team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="team not found")

        m = await membership(session, team_id, body.by_user_id)
        if m is None or m.role != "owner":
            raise HTTPException(
                status_code=403, detail="only the team owner can invite"
            )

        token = secrets.token_urlsafe(24)
        expires = datetime.now(timezone.utc) + timedelta(seconds=body.ttl_seconds)
        invite = TeamInvite(
            team_id=team_id,
            role=body.role.strip() or "member",
            token=token,
            created_by_user_id=body.by_user_id,
            expires_at=expires,
        )
        session.add(invite)
        await session.commit()
        await session.refresh(invite)

        return InviteResponse(
            token=invite.token,
            team_id=team.id,
            team_name=team.name,
            role=invite.role,
            expires_at=invite.expires_at,
        )


@router.get("/api/v1/teams/invites/{token}", response_model=InvitePreview)
async def preview_invite(token: str) -> InvitePreview:
    async with session_factory() as session:
        invite, team = await load_invite(session, token)
        return InvitePreview(
            team_id=team.id,
            team_name=team.name,
            role=invite.role,
            expires_at=invite.expires_at,
            expired=invite_expired(invite),
            accepted=invite.accepted_at is not None,
        )


@router.post(
    "/api/v1/teams/invites/{token}/accept",
    response_model=TeamDetailResponse,
)
async def accept_invite(
    token: str, body: InviteAcceptRequest
) -> TeamDetailResponse:
    async with session_factory() as session:
        invite, team = await load_invite(session, token)
        if invite.accepted_at is not None:
            raise HTTPException(
                status_code=410, detail="invite already used"
            )
        if invite_expired(invite):
            raise HTTPException(
                status_code=410, detail="invite expired"
            )

        user = await session.get(User, body.user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")

        existing = await membership(session, team.id, user.id)
        if existing is None:
            session.add(
                TeamMembership(
                    user_id=user.id, team_id=team.id, role=invite.role
                )
            )
        invite.accepted_at = datetime.now(timezone.utc)
        invite.accepted_by_user_id = user.id

        await session.commit()
        await session.refresh(team)
        return await team_detail(session, team, user.id)
