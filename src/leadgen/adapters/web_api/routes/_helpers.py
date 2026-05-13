"""Cross-route helpers shared by extracted ``APIRouter`` modules.

These were ``app.py`` module-level functions; lifting them here keeps
the per-domain route files free of upward imports into ``app.py``,
which would create a cycle (``app.py`` imports the routers).

Add helpers here only when at least two route modules need them. One-
off helpers belong inside their owning route module.
"""

from __future__ import annotations

import asyncio
import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, Request
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.adapters.web_api.auth import request_ip
from leadgen.adapters.web_api.schemas import (
    LeadResponse,
    LeadStatusSchema,
    LeadTagSchema,
    PendingAction,
    PriorTeamSearch,
    SearchSummary,
    TeamDetailResponse,
    TeamMemberResponse,
    UserProfile,
)
from leadgen.analysis.ai_analyzer import AIAnalyzer
from leadgen.config import get_settings
from leadgen.core.services import (
    mask_email,
    render_verification_email,
    send_email,
)
from leadgen.db.models import (
    EmailVerificationToken,
    Lead,
    LeadMark,
    LeadStatus,
    LeadTag,
    LeadTagAssignment,
    SearchQuery,
    Team,
    TeamInvite,
    TeamMembership,
    User,
    UserAuditLog,
)
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


_DEFAULT_LEAD_STATUSES: tuple[tuple[str, str, str, int, bool], ...] = (
    ("new", "Новый", "slate", 0, False),
    ("contacted", "Связались", "blue", 1, False),
    ("replied", "Ответили", "teal", 2, False),
    ("won", "Сделка", "green", 3, True),
    ("archived", "Архив", "slate", 99, True),
)


def seed_default_lead_statuses(session, team_id) -> None:
    """Insert the five default statuses for a freshly-created team."""
    for key, label, color, order_index, is_terminal in _DEFAULT_LEAD_STATUSES:
        session.add(
            LeadStatus(
                team_id=team_id,
                key=key,
                label=label,
                color=color,
                order_index=order_index,
                is_terminal=is_terminal,
            )
        )


# Backward-compat alias for code that still calls the module-private name.
_seed_default_lead_statuses = seed_default_lead_statuses


async def membership(
    session: AsyncSession, team_id: uuid.UUID, user_id: int
) -> TeamMembership | None:
    """Return the user's membership row in a team, or ``None``."""
    result = await session.execute(
        select(TeamMembership)
        .where(TeamMembership.team_id == team_id)
        .where(TeamMembership.user_id == user_id)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def can_manage_tag(
    session: AsyncSession, tag: LeadTag, user_id: int
) -> bool:
    """Personal tags belong to one user; team tags need membership."""
    if tag.team_id is None:
        return tag.user_id == user_id
    return (await membership(session, tag.team_id, user_id)) is not None


# ── Argon2 password hashing ────────────────────────────────────────────

_password_hasher = PasswordHasher()

# Pre-computed hash of a value that no real password can match. Used by
# login to keep the request timing identical whether the email exists or
# not, blocking enumeration via response-time analysis.
DUMMY_PASSWORD_HASH = _password_hasher.hash("__convioo_dummy_password__")


def hash_password(plain: str) -> str:
    return _password_hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _password_hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False
    except Exception:  # noqa: BLE001
        return False


# ── Audit log ──────────────────────────────────────────────────────────


async def record_audit(
    session,
    *,
    user_id: int,
    action: str,
    request: Request | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Append an entry to ``user_audit_logs``."""
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


# ── Email verification + change-email plumbing ─────────────────────────


async def issue_and_send_verification(session, user: User) -> None:
    """Mint a fresh verification token and email the user."""
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


async def issue_and_send_change_email(
    session, user: User, new_email: str
) -> None:
    """Mint a change-email token addressed to the *new* mailbox."""
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


# ── Onboarding gate ────────────────────────────────────────────────────


def is_onboarded(user: User) -> bool:
    """Web onboarding gate."""
    return user.onboarded_at is not None and bool(
        user.first_name or user.display_name
    )


# ── Team invites ───────────────────────────────────────────────────────


def invite_expired(invite: TeamInvite) -> bool:
    expires = invite.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= expires


async def load_invite(session, token: str) -> tuple[TeamInvite, Team]:
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


# ── Team views ─────────────────────────────────────────────────────────


async def resolve_team_view(
    session,
    team_id: uuid.UUID,
    caller_user_id: int,
    member_user_id: int | None,
) -> int:
    """Decide whose data the caller is allowed to read in a team view."""
    caller = await membership(session, team_id, caller_user_id)
    if caller is None:
        raise HTTPException(status_code=403, detail="not a team member")

    if member_user_id is None or member_user_id == caller_user_id:
        return caller_user_id

    # Admin and owner can both look at another member's CRM. Plain
    # members can only see their own — viewing other people's
    # private notes / pipelines is an elevated capability.
    from leadgen.core.services.team_permissions import can_manage_members

    if not can_manage_members(caller.role):
        raise HTTPException(
            status_code=403,
            detail="only owner or admin can view another member",
        )
    target = await membership(session, team_id, member_user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="that user isn't a team member")
    return member_user_id


async def team_prior_searches(
    session,
    team_id: uuid.UUID,
    niche: str,
    region: str,
) -> list[PriorTeamSearch]:
    """Return earlier completed searches in this team that already
    used the same (niche, region) pair, normalised case-insensitively
    and trimmed.
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


def status_to_schema(row: LeadStatus) -> LeadStatusSchema:
    return LeadStatusSchema(
        id=row.id,
        key=row.key,
        label=row.label,
        color=row.color,
        order_index=row.order_index,
        is_terminal=row.is_terminal,
    )


async def team_detail(
    session, team: Team, viewer_user_id: int
) -> TeamDetailResponse:
    m = await membership(session, team.id, viewer_user_id)
    if m is None:
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
    for i, (mem, user) in enumerate(rows):
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
                role=mem.role,
                description=mem.description,
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
        role=m.role,
        members=members,
    )


# ── Lead helpers ───────────────────────────────────────────────────────


def to_summary(query: SearchQuery) -> SearchSummary:
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
        archived_at=query.archived_at,
    )


async def marks_for_user(
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


def to_lead_response(
    lead: Lead,
    mark_color: str | None,
    user_tags: list[LeadTagSchema] | None = None,
) -> LeadResponse:
    payload = LeadResponse.model_validate(lead)
    payload.mark_color = mark_color
    if user_tags:
        payload.user_tags = list(user_tags)
    return payload


async def tags_by_lead(
    session, lead_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[LeadTagSchema]]:
    """Eager-load every tag chip attached to ``lead_ids``."""
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


def temp(score: float | None) -> str:
    """Bucket a 0–100 AI score into prototype temperature tiers."""
    if score is None:
        return "cold"
    if score >= 75:
        return "hot"
    if score >= 50:
        return "warm"
    return "cold"


def extract_lead_email(lead: Lead) -> str | None:
    """Pluck the first usable email out of the website-meta payload."""
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


def to_profile(user: User) -> UserProfile:
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
        onboarded=is_onboarded(user),
        onboarding_tour_completed=user.onboarding_completed_at is not None,
        email=user.email,
        email_verified=user.email_verified_at is not None,
        recovery_email_masked=mask_email(recovery) if recovery else None,
        queries_used=int(user.queries_used or 0),
        queries_limit=int(user.queries_limit or 0),
    )


# ── Henry (assistant) helpers ──────────────────────────────────────────


# Whole-message confirm/refuse keywords. Anchored so a long message
# that happens to start with "да" doesn't accidentally trigger an
# auto-apply — we only short-circuit the LLM call when the whole
# user reply is clearly a yes / no.
_CONFIRM_RE = re.compile(
    r"^\s*(да|да\.|да!|ага|угу|окей|ок|ok|okay|yes|y|"
    r"верно|подтверждаю|записывай|запиши|записать|применяй|применить|"
    r"давай|поехали|sure|confirm|apply|go ahead)\s*[.!?]?\s*$",
    re.IGNORECASE,
)
_REFUSE_RE = re.compile(
    r"^\s*(нет|нет\.|нет!|не\s+так|поправь|погоди|стоп|"
    r"no|n|nope|cancel|wait|hold on|stop)\s*[.!?]?\s*$",
    re.IGNORECASE,
)


def detect_confirmation(text: str) -> str | None:
    """Return ``"confirm"`` / ``"refuse"`` / ``None`` for a reply."""
    if not text:
        return None
    if _CONFIRM_RE.match(text):
        return "confirm"
    if _REFUSE_RE.match(text):
        return "refuse"
    return None


_PROFILE_FIELDS_WHITELIST = {
    "display_name",
    "age_range",
    "business_size",
    "service_description",
    "home_region",
    "niches",
}


def result_to_pending_actions(
    result: dict[str, Any], mode: str
) -> list[PendingAction]:
    """Translate Henry's raw JSON output to PendingAction items."""
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
                        summary=(
                            f"Запустить поиск: {niche} в {region}"
                        ),
                        payload=payload,
                    )
                )
    return out


async def summarise_and_store(
    user_id: int,
    team_id: uuid.UUID | None,
    history: list[dict[str, str]],
    user_profile: dict[str, Any] | None,
    existing_memories: list[dict[str, Any]],
) -> None:
    """Background task: distill the dialogue, persist summary + facts."""
    from leadgen.core.services.assistant_memory import (
        prune_old,
        record_memory,
    )
    from leadgen.db.session import session_factory

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


async def apply_pending_actions(
    session,
    user: User | None,
    team_context: dict[str, Any] | None,
    actions: list[PendingAction],
) -> list[PendingAction]:
    """Apply a list of confirmed actions, return what was applied."""
    from leadgen.queue import enqueue_search

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
                    m = await membership(
                        session, team_id, target_user_id
                    )
                    if m is not None:
                        m.description = (
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

                queued_id = await enqueue_search(
                    new_query.id,
                    chat_id=None,
                    user_profile=user_profile_for_run,
                )
                if not queued_id:
                    spawn(
                        run_web_search_inline(
                            new_query.id, user_profile_for_run
                        ),
                        name=f"convioo-henry-search-{new_query.id}",
                    )

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


# ── Inline search runner (used as fallback when no Redis worker) ───────


async def run_web_search_inline(
    query_id: uuid.UUID, user_profile: dict[str, Any] | None
) -> None:
    """Fallback in-process runner when no Redis worker is available."""
    from leadgen.adapters.web_api.sinks import WebDeliverySink
    from leadgen.core.services import default_broker
    from leadgen.core.services.progress_broker import BrokerProgressSink
    from leadgen.pipeline.search import run_search_with_timeout

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
