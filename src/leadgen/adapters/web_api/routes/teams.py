"""``/api/v1/teams/*`` — team CRUD, invites, membership management."""

from __future__ import annotations

import base64
import binascii
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from leadgen.adapters.web_api.auth import enforce_rate_limit, get_current_user
from leadgen.adapters.web_api.routes._helpers import (
    invite_expired,
    load_invite,
    membership,
    seed_default_lead_statuses,
    status_to_schema,
    team_detail,
)
from leadgen.adapters.web_api.schemas import (
    InviteCreateRequest,
    InvitePreview,
    InviteResponse,
    LeadStatusCreate,
    LeadStatusListResponse,
    LeadStatusReorderRequest,
    LeadStatusSchema,
    LeadStatusUpdate,
    MembershipUpdateRequest,
    TeamAnalytics,
    TeamAnalyticsMemberBucket,
    TeamAnalyticsNicheBucket,
    TeamAnalyticsSourceBucket,
    TeamAnalyticsStatusBucket,
    TeamAnalyticsTimepoint,
    TeamCreateRequest,
    TeamDetailResponse,
    TeamMemberSummary,
    TeamSummary,
    TeamUpdateRequest,
)
from leadgen.core.services.team_permissions import (
    PERM_MANAGE_STATUSES,
    PERM_VIEW_ANALYTICS,
    ROLE_ADMIN,
    ROLE_OWNER,
    assignable_roles_for,
    can_edit_team_settings,
    can_manage_members,
    has_permission,
    normalize_role,
)
from leadgen.db.models import (
    Lead,
    LeadStatus,
    SearchQuery,
    Team,
    TeamInvite,
    TeamMembership,
    User,
)
from leadgen.db.session import session_factory
from leadgen.utils.rate_limit import invite_create_limiter

router = APIRouter(tags=["teams"])


@router.post("/api/v1/teams", response_model=TeamDetailResponse)
async def create_team(
    body: TeamCreateRequest,
    current_user: User = Depends(get_current_user),
) -> TeamDetailResponse:
    """Create a new team owned by the authenticated caller.

    The legacy ``owner_user_id`` field on the request body is ignored —
    a session-bound caller can only create teams they themselves own.
    """
    async with session_factory() as session:
        team = Team(name=body.name.strip(), plan="free")
        session.add(team)
        await session.flush()
        session.add(
            TeamMembership(
                user_id=current_user.id, team_id=team.id, role="owner"
            )
        )
        seed_default_lead_statuses(
            session, team.id, lang=current_user.language_code
        )
        await session.commit()
        await session.refresh(team)

        return await team_detail(session, team, current_user.id)


@router.get("/api/v1/teams", response_model=list[TeamSummary])
async def list_my_teams(
    current_user: User = Depends(get_current_user),
) -> list[TeamSummary]:
    async with session_factory() as session:
        stmt = (
            select(TeamMembership, Team)
            .join(Team, Team.id == TeamMembership.team_id)
            .where(TeamMembership.user_id == current_user.id)
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
async def get_team(
    team_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> TeamDetailResponse:
    async with session_factory() as session:
        team = await session.get(Team, team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="team not found")
        return await team_detail(session, team, current_user.id)


@router.patch("/api/v1/teams/{team_id}", response_model=TeamDetailResponse)
async def update_team(
    team_id: uuid.UUID,
    body: TeamUpdateRequest,
    current_user: User = Depends(get_current_user),
) -> TeamDetailResponse:
    """Owner / admin PATCH for the team's name + description."""
    async with session_factory() as session:
        team = await session.get(Team, team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="team not found")
        m = await membership(session, team_id, current_user.id)
        if m is None or not can_edit_team_settings(m.role):
            raise HTTPException(
                status_code=403,
                detail="only owner or admin can edit the team",
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
        return await team_detail(session, team, current_user.id)


@router.patch(
    "/api/v1/teams/{team_id}/members/{member_user_id}",
    response_model=TeamDetailResponse,
)
async def update_member(
    team_id: uuid.UUID,
    member_user_id: int,
    body: MembershipUpdateRequest,
    current_user: User = Depends(get_current_user),
) -> TeamDetailResponse:
    """PATCH a teammate's per-team description / role.

    Owner can change anyone's role except their own (transfer of
    ownership is a separate flow). Admins can change roles too but
    only within their assignable set (manager / sales) — they can't
    promote anyone to admin or owner, nor touch an existing admin's
    or the owner's seat. Description is freely editable by anyone
    with member-management rights.
    """
    async with session_factory() as session:
        team = await session.get(Team, team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="team not found")
        caller = await membership(session, team_id, current_user.id)
        if caller is None or not can_manage_members(caller.role):
            raise HTTPException(
                status_code=403,
                detail="only owner or admin can edit members",
            )
        target = await membership(session, team_id, member_user_id)
        if target is None:
            raise HTTPException(
                status_code=404, detail="that user isn't a team member"
            )

        data = body.model_dump(exclude_unset=True)
        caller_role = normalize_role(caller.role)
        target_role = normalize_role(target.role)
        # An admin may not touch the owner's or another admin's seat
        # at all — role or description. Peer/superior management is
        # owner-only.
        if (
            caller_role == ROLE_ADMIN
            and target.user_id != current_user.id
            and target_role in {ROLE_OWNER, ROLE_ADMIN}
        ):
            raise HTTPException(
                status_code=403,
                detail="only the owner can edit an admin or the owner",
            )
        if "description" in data:
            desc = (data["description"] or "").strip()
            target.description = desc or None
        if "role" in data and data["role"]:
            role_value = normalize_role(data["role"])
            # Self-demotion guard for the owner. The seat has to keep
            # an owner, so demoting yourself out of owner without a
            # transfer is rejected.
            if (
                target.user_id == current_user.id
                and caller_role == ROLE_OWNER
                and role_value != ROLE_OWNER
            ):
                raise HTTPException(
                    status_code=400,
                    detail="owners can't demote themselves",
                )
            # Each caller role has a fixed assignable set: owner →
            # admin/manager/sales, admin → manager/sales. Nobody
            # assigns "owner" here — that's the transfer flow.
            if role_value not in assignable_roles_for(caller_role):
                raise HTTPException(
                    status_code=403,
                    detail="your role can't assign that role",
                )
            target.role = role_value

        await session.commit()
        return await team_detail(session, team, current_user.id)


class TransferOwnershipRequest(BaseModel):
    new_owner_user_id: int


@router.post(
    "/api/v1/teams/{team_id}/transfer-ownership",
    response_model=TeamDetailResponse,
)
async def transfer_ownership(
    team_id: uuid.UUID,
    body: TransferOwnershipRequest,
    current_user: User = Depends(get_current_user),
) -> TeamDetailResponse:
    """Hand the owner seat to another member (owner only).

    The current owner becomes an admin; the target becomes the
    owner. One transaction — the team never has zero or two owners.
    """
    async with session_factory() as session:
        team = await session.get(Team, team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="team not found")
        caller = await membership(session, team_id, current_user.id)
        if caller is None or normalize_role(caller.role) != ROLE_OWNER:
            raise HTTPException(
                status_code=403,
                detail="only the owner can transfer ownership",
            )
        if body.new_owner_user_id == current_user.id:
            raise HTTPException(
                status_code=400, detail="you already own this team"
            )
        target = await membership(session, team_id, body.new_owner_user_id)
        if target is None:
            raise HTTPException(
                status_code=404, detail="that user isn't a team member"
            )
        caller.role = ROLE_ADMIN
        target.role = ROLE_OWNER
        await session.commit()
        await session.refresh(team)
        return await team_detail(session, team, current_user.id)


class RemoveMemberResponse(BaseModel):
    ok: bool = True
    transferred_leads: int = 0


@router.delete(
    "/api/v1/teams/{team_id}/members/{member_user_id}",
    response_model=RemoveMemberResponse,
)
async def remove_member(
    team_id: uuid.UUID,
    member_user_id: int,
    transfer_to: int | None = Query(default=None),
    current_user: User = Depends(get_current_user),
) -> RemoveMemberResponse:
    """Remove a teammate, transferring their assigned leads first.

    Rules:

    * Owner / admin remove members; an admin can't remove the owner
      or another admin. Any non-owner may remove *themselves* (leave
      the team) without member-management rights.
    * The owner seat can't be removed — ownership is transferred via
      the separate transfer flow first.
    * If the leaving member still has team leads assigned to them,
      ``transfer_to`` (another current member) is REQUIRED — the
      call fails with 409 + the count otherwise. All their leads are
      reassigned in one transaction and an ``assigned`` activity is
      written per lead so the timeline shows the hand-over.
    """
    async with session_factory() as session:
        team = await session.get(Team, team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="team not found")
        caller = await membership(session, team_id, current_user.id)
        if caller is None:
            raise HTTPException(status_code=403, detail="not a team member")
        target = await membership(session, team_id, member_user_id)
        if target is None:
            raise HTTPException(
                status_code=404, detail="that user isn't a team member"
            )

        caller_role = normalize_role(caller.role)
        target_role = normalize_role(target.role)
        is_self = member_user_id == current_user.id

        if target_role == ROLE_OWNER:
            raise HTTPException(
                status_code=400,
                detail=(
                    "the owner can't be removed — transfer ownership first"
                ),
            )
        if not is_self:
            if not can_manage_members(caller.role):
                raise HTTPException(
                    status_code=403,
                    detail="only owner or admin can remove members",
                )
            if caller_role == ROLE_ADMIN and target_role == ROLE_ADMIN:
                raise HTTPException(
                    status_code=403,
                    detail="only the owner can remove an admin",
                )

        # Leads assigned to the leaving member inside this team.
        assigned_ids = (
            (
                await session.execute(
                    select(Lead.id)
                    .join(SearchQuery, SearchQuery.id == Lead.query_id)
                    .where(SearchQuery.team_id == team_id)
                    .where(Lead.owner_user_id == member_user_id)
                    .where(Lead.deleted_at.is_(None))
                )
            )
            .scalars()
            .all()
        )

        if assigned_ids:
            if transfer_to is None:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"{len(assigned_ids)} lead(s) are assigned to this "
                        "member. Pass transfer_to=<user_id> to hand them "
                        "over before removal."
                    ),
                )
            if transfer_to == member_user_id:
                raise HTTPException(
                    status_code=400,
                    detail="transfer_to can't be the member being removed",
                )
            recipient = await membership(session, team_id, transfer_to)
            if recipient is None:
                raise HTTPException(
                    status_code=400,
                    detail="transfer_to must be a current team member",
                )

            await session.execute(
                sa.update(Lead)
                .where(Lead.id.in_(assigned_ids))
                .values(owner_user_id=transfer_to)
            )
            from leadgen.db.models import LeadActivity

            session.add_all(
                [
                    LeadActivity(
                        lead_id=lead_id,
                        user_id=current_user.id,
                        team_id=team_id,
                        kind="assigned",
                        payload={
                            "from": member_user_id,
                            "to": transfer_to,
                            "reason": "member_removed",
                        },
                    )
                    for lead_id in assigned_ids
                ]
            )

        await session.delete(target)
        await session.commit()
        return RemoveMemberResponse(
            ok=True, transferred_leads=len(assigned_ids)
        )


@router.post("/api/v1/teams/{team_id}/invites", response_model=InviteResponse)
async def create_invite(
    team_id: uuid.UUID,
    body: InviteCreateRequest,
    current_user: User = Depends(get_current_user),
) -> InviteResponse:
    enforce_rate_limit(
        invite_create_limiter, f"user:{current_user.id}", retry_hint=60
    )
    async with session_factory() as session:
        team = await session.get(Team, team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="team not found")

        m = await membership(session, team_id, current_user.id)
        if m is None or not can_manage_members(m.role):
            raise HTTPException(
                status_code=403,
                detail="only owner or admin can invite",
            )

        # Each caller role has a fixed assignable set: owner →
        # admin/manager/sales, admin → manager/sales. Nobody invites
        # an "owner". Default (no role in body) is sales — the least
        # powerful seat.
        invite_role = normalize_role(body.role) if body.role else "sales"
        caller_role = normalize_role(m.role)
        if invite_role not in assignable_roles_for(caller_role):
            raise HTTPException(
                status_code=403,
                detail="your role can't invite that role",
            )

        token = secrets.token_urlsafe(24)
        expires = datetime.now(timezone.utc) + timedelta(seconds=body.ttl_seconds)
        invite = TeamInvite(
            team_id=team_id,
            role=invite_role,
            token=token,
            created_by_user_id=current_user.id,
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
    token: str,
    current_user: User = Depends(get_current_user),
) -> TeamDetailResponse:
    """Join the team behind ``token`` as the authenticated caller.

    Legacy clients still POST ``{"user_id": ...}`` — the body is
    ignored; the session decides who joins.
    """
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

        user = await session.get(User, current_user.id)
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


# ── White-label branding ───────────────────────────────────────────────

# A #RRGGBB hex accent. We reject anything else so the colour is safe to
# drop straight into the PDF / web view without further escaping.
_BRAND_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# data:image/(png|jpeg|jpg|webp);base64,<payload>
_BRAND_LOGO_RE = re.compile(
    r"^data:image/(png|jpe?g|webp);base64,(.+)$", re.IGNORECASE
)

# Cap the decoded logo so the base64 blob can't bloat the Postgres row.
_MAX_LOGO_BYTES = 200 * 1024


class BrandingResponse(BaseModel):
    brand_name: str | None = None
    brand_logo: str | None = None
    brand_color: str | None = None


class BrandingUpdateRequest(BaseModel):
    # Pydantic can't tell "field omitted" from "explicit null" without
    # model_fields_set; we read that below so a null clears a field while
    # an absent key leaves it untouched.
    brand_name: str | None = None
    brand_logo: str | None = None
    brand_color: str | None = None


@router.get(
    "/api/v1/teams/{team_id}/branding", response_model=BrandingResponse
)
async def get_branding(
    team_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> BrandingResponse:
    """Read the team's white-label branding. Any member may read it."""
    async with session_factory() as session:
        team = await session.get(Team, team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="team not found")
        m = await membership(session, team_id, current_user.id)
        if m is None:
            raise HTTPException(status_code=403, detail="not a team member")
        return BrandingResponse(
            brand_name=team.brand_name,
            brand_logo=team.brand_logo,
            brand_color=team.brand_color,
        )


@router.patch(
    "/api/v1/teams/{team_id}/branding", response_model=BrandingResponse
)
async def update_branding(
    team_id: uuid.UUID,
    body: BrandingUpdateRequest,
    current_user: User = Depends(get_current_user),
) -> BrandingResponse:
    """Owner-only PATCH of the team's white-label branding.

    Null clears a field; an absent key leaves it untouched. Validates the
    colour (``#RRGGBB``) and the logo (image data URL, ≤200 KB decoded)
    so a malformed value never reaches the Postgres row.
    """
    async with session_factory() as session:
        team = await session.get(Team, team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="team not found")
        m = await membership(session, team_id, current_user.id)
        if m is None or normalize_role(m.role) != ROLE_OWNER:
            raise HTTPException(
                status_code=403,
                detail="only the team owner can edit branding",
            )

        fields = body.model_fields_set

        if "brand_name" in fields:
            raw = body.brand_name
            team.brand_name = (raw.strip() or None) if raw else None

        if "brand_color" in fields:
            raw = body.brand_color
            if raw:
                trimmed = raw.strip()
                if not _BRAND_COLOR_RE.match(trimmed):
                    raise HTTPException(
                        status_code=400,
                        detail="brand_color must be #RRGGBB",
                    )
                team.brand_color = trimmed
            else:
                team.brand_color = None

        if "brand_logo" in fields:
            raw = body.brand_logo
            if raw:
                match = _BRAND_LOGO_RE.match(raw.strip())
                if not match:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "brand_logo must be a data:image/"
                            "(png|jpeg|webp);base64 URL"
                        ),
                    )
                try:
                    decoded = base64.b64decode(match.group(2), validate=True)
                except (binascii.Error, ValueError) as exc:
                    raise HTTPException(
                        status_code=400,
                        detail="brand_logo base64 payload is invalid",
                    ) from exc
                if len(decoded) > _MAX_LOGO_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="brand_logo must be at most 200 KB",
                    )
                team.brand_logo = raw.strip()
            else:
                team.brand_logo = None

        await session.commit()
        await session.refresh(team)
        return BrandingResponse(
            brand_name=team.brand_name,
            brand_logo=team.brand_logo,
            brand_color=team.brand_color,
        )


@router.get(
    "/api/v1/teams/{team_id}/members-summary",
    response_model=list[TeamMemberSummary],
)
async def team_members_summary(
    team_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> list[TeamMemberSummary]:
    """Manager+ roll-up: per-member sessions/leads/hot counts
    (the "Команда" screen). No money fields here by design."""
    async with session_factory() as session:
        caller = await membership(session, team_id, current_user.id)
        if caller is None or not has_permission(
            caller.role, PERM_VIEW_ANALYTICS
        ):
            raise HTTPException(
                status_code=403,
                detail="your role can't see the per-member summary",
            )

        rows = (
            await session.execute(
                select(TeamMembership, User)
                .join(User, User.id == TeamMembership.user_id)
                .where(TeamMembership.team_id == team_id)
                .order_by(TeamMembership.created_at)
            )
        ).all()

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
                            sa.case((Lead.score_ai >= 75, 1))
                        ),
                    )
                    .join(SearchQuery, SearchQuery.id == Lead.query_id)
                    .where(SearchQuery.team_id == team_id)
                    .group_by(SearchQuery.user_id)
                )
            ).all()
        }

        results: list[TeamMemberSummary] = []
        for ms, member in rows:
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
                    role=ms.role,
                    sessions_total=sessions_by_user.get(member.id, 0),
                    leads_total=leads_total,
                    hot_total=hot,
                )
            )
        return results


@router.get(
    "/api/v1/teams/{team_id}/analytics",
    response_model=TeamAnalytics,
)
async def team_analytics(
    team_id: uuid.UUID,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    current_user: User = Depends(get_current_user),
) -> TeamAnalytics:
    """Manager+ per-team analytics for ``/app/team/analytics``."""
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
        ms = await membership(session, team_id, current_user.id)
        if ms is None or not has_permission(ms.role, PERM_VIEW_ANALYTICS):
            raise HTTPException(
                status_code=403,
                detail="your role can't view analytics",
            )

        base_searches = (
            select(SearchQuery)
            .where(SearchQuery.team_id == team_id)
            .where(SearchQuery.created_at >= period_from)
            .where(SearchQuery.created_at <= period_to)
        )
        search_rows = (await session.execute(base_searches)).scalars().all()

        search_ids = [s.id for s in search_rows]
        lead_rows: list[Lead] = []
        if search_ids:
            lead_rows = (
                await session.execute(
                    select(Lead).where(Lead.query_id.in_(search_ids))
                )
            ).scalars().all()

        scores = [
            float(lead.score_ai)
            for lead in lead_rows
            if lead.score_ai is not None
        ]
        avg_score = round(sum(scores) / len(scores), 1) if scores else None

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
        leads_by_user_map: dict[int, list[Lead]] = {}
        for lead in lead_rows:
            uid = search_user_map.get(lead.query_id)
            if uid is None:
                continue
            leads_by_user_map.setdefault(uid, []).append(lead)

        members: list[TeamAnalyticsMemberBucket] = []
        for _ms, u in members_rows:
            user_leads = leads_by_user_map.get(u.id, [])
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


@router.get(
    "/api/v1/teams/{team_id}/statuses",
    response_model=LeadStatusListResponse,
)
async def list_lead_statuses(
    team_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> LeadStatusListResponse:
    async with session_factory() as session:
        ms = await membership(session, team_id, current_user.id)
        if ms is None:
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
    return LeadStatusListResponse(items=[status_to_schema(s) for s in rows])


@router.post(
    "/api/v1/teams/{team_id}/statuses",
    response_model=LeadStatusSchema,
)
async def create_lead_status(
    team_id: uuid.UUID,
    body: LeadStatusCreate,
    current_user: User = Depends(get_current_user),
) -> LeadStatusSchema:
    async with session_factory() as session:
        ms = await membership(session, team_id, current_user.id)
        if ms is None or not has_permission(ms.role, PERM_MANAGE_STATUSES):
            raise HTTPException(status_code=403, detail="forbidden")
        key = body.key.strip().lower()
        cleaned = "".join(ch for ch in key if ch.isalnum() or ch in "-_")
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
        max_order = max((m for _, m in existing_keys), default=-1)
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
    return status_to_schema(row)


@router.patch(
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
        ms = await membership(session, team_id, current_user.id)
        if ms is None or not has_permission(ms.role, PERM_MANAGE_STATUSES):
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
    return status_to_schema(row)


@router.delete("/api/v1/teams/{team_id}/statuses/{status_id}")
async def delete_lead_status(
    team_id: uuid.UUID,
    status_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    async with session_factory() as session:
        ms = await membership(session, team_id, current_user.id)
        if ms is None or not has_permission(ms.role, PERM_MANAGE_STATUSES):
            raise HTTPException(status_code=403, detail="forbidden")
        row = await session.get(LeadStatus, status_id)
        if row is None or row.team_id != team_id:
            raise HTTPException(status_code=404, detail="status not found")
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


@router.post(
    "/api/v1/teams/{team_id}/statuses/reorder",
    response_model=LeadStatusListResponse,
)
async def reorder_lead_statuses(
    team_id: uuid.UUID,
    body: LeadStatusReorderRequest,
    current_user: User = Depends(get_current_user),
) -> LeadStatusListResponse:
    async with session_factory() as session:
        ms = await membership(session, team_id, current_user.id)
        if ms is None or not has_permission(ms.role, PERM_MANAGE_STATUSES):
            raise HTTPException(status_code=403, detail="forbidden")
        owned_ids = set(
            (
                await session.execute(
                    select(LeadStatus.id).where(LeadStatus.team_id == team_id)
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
    return LeadStatusListResponse(items=[status_to_schema(r) for r in rows])
