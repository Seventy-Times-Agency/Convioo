"""Module-level helpers used by the web-API route handlers.

Used to live at the bottom of ``app.py``; pulled into a dedicated
module so the route files (auth.py, integrations.py, leads.py …)
can import what they need without dragging the whole ``create_app``
factory along.

No FastAPI app instance is created here — every helper is either a
plain function or operates on a SQLAlchemy session passed by the
caller. Keep it that way: this module must stay safe to import from
both the API process and the arq worker.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, Request
from sqlalchemy import func, select, update

from leadgen.adapters.web_api.schemas import (
    PriorTeamSearch,
    SearchSummary,
    TeamDetailResponse,
    TeamMemberResponse,
    UserProfile,
)
from leadgen.adapters.web_api.sinks import WebDeliverySink
from leadgen.analysis.ai_analyzer import AIAnalyzer
from leadgen.config import get_settings
from leadgen.core.services import default_broker
from leadgen.core.services.assistant_memory import prune_old, record_memory
from leadgen.core.services.email_sender import (
    render_verification_email as _render_verification_email,
)
from leadgen.core.services.email_sender import send_email
from leadgen.core.services.progress_broker import BrokerProgressSink
from leadgen.db.models import (
    EmailVerificationToken,
    Lead,
    LeadMark,
    SearchQuery,
    Team,
    TeamInvite,
    TeamMembership,
    User,
    UserAuditLog,
)
from leadgen.db.session import session_factory
from leadgen.pipeline.search import run_search_with_sinks

logger = logging.getLogger(__name__)


# Demo avatars for team page until seat management is wired up.
DEMO_TEAM_COLORS = [
    "#3D5AFE",
    "#F59E0B",
    "#16A34A",
    "#EC4899",
    "#8B5CF6",
    "#06B6D4",
]


# ── Search pipeline ────────────────────────────────────────────────────


async def run_web_search_inline(
    query_id, user_profile: dict[str, Any] | None
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
    )


# ── Lead helpers ───────────────────────────────────────────────────────


async def marks_for_user(
    session, user_id: int, lead_ids: list
) -> dict:
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


def to_lead_response(lead: Lead, mark_color: str | None):
    from leadgen.adapters.web_api.schemas import LeadResponse

    payload = LeadResponse.model_validate(lead)
    payload.mark_color = mark_color
    payload.email = pick_lead_email(lead)
    return payload


def pick_lead_email(lead: Lead) -> str | None:
    """First non-generic email from the scraped website_meta, if any."""
    meta = lead.website_meta or {}
    if not isinstance(meta, dict):
        return None
    emails = meta.get("emails")
    if not isinstance(emails, list):
        return None
    for value in emails:
        if isinstance(value, str) and "@" in value:
            return value.strip()
    return None


def temp(score: float | None) -> str:
    """Bucket a 0–100 AI score into prototype temperature tiers."""
    if score is None:
        return "cold"
    if score >= 75:
        return "hot"
    if score >= 50:
        return "warm"
    return "cold"


# ── Password hashing ───────────────────────────────────────────────────


_password_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    return _password_hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _password_hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False
    except Exception:  # noqa: BLE001
        return False


# ── Request / audit ────────────────────────────────────────────────────


def request_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    if request.client and request.client.host:
        return request.client.host[:64]
    return None


async def record_audit(
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


# ── OAuth state cache ──────────────────────────────────────────────────
# Maps state-token → (user_id, issued_at). 10-minute TTL. Held in
# process — survives one consent round-trip but not deploys; that's
# fine, the user just hits "Connect" again.
oauth_state_cache: dict[str, tuple[int, datetime]] = {}
OAUTH_STATE_TTL = timedelta(minutes=10)


def gc_oauth_state_cache() -> None:
    """Drop expired entries. Cheap O(n) sweep, called on every issue."""
    cutoff = datetime.now(timezone.utc) - OAUTH_STATE_TTL
    stale = [s for s, (_, ts) in oauth_state_cache.items() if ts < cutoff]
    for s in stale:
        oauth_state_cache.pop(s, None)


def google_redirect_uri(request: Request) -> str:
    """The ``redirect_uri`` registered with Google Cloud Console.

    Prefers ``PUBLIC_API_URL`` so the value is deterministic in prod;
    falls back to the request's own scheme+host for local dev.
    """
    base = (get_settings().public_api_url or "").rstrip("/")
    if not base:
        base = f"{request.url.scheme}://{request.url.netloc}"
    return f"{base}/api/v1/integrations/google/callback"


# ── Email verification flow ────────────────────────────────────────────


async def issue_and_send_verification(session, user: User) -> bool:
    """Mint a fresh verification token and email the user.

    Invalidates earlier outstanding tokens so there's only one live
    link at a time. Returns True iff Resend actually dispatched the
    message — the log-only fallback returns False so callers can
    surface a "we couldn't email you" warning to the SPA.
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
    html, text = _render_verification_email(name=name, verify_url=verify_url)
    if not user.email:
        return False
    result = await send_email(
        to=user.email,
        subject="Подтвердите email — Convioo",
        html=html,
        text=text,
    )
    return result.dispatched


async def issue_and_send_change_email(
    session, user: User, new_email: str
) -> bool:
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
    html, text = _render_verification_email(name=name, verify_url=verify_url)
    result = await send_email(
        to=new_email,
        subject="Подтвердите новый email — Convioo",
        html=html,
        text=text,
    )
    return result.dispatched


# ── User helpers ───────────────────────────────────────────────────────


def is_onboarded(user: User) -> bool:
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


def to_profile(user: User) -> UserProfile:
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
        onboarded=is_onboarded(user),
        queries_used=int(user.queries_used or 0),
        queries_limit=int(user.queries_limit or 0),
    )


# ── Team helpers ───────────────────────────────────────────────────────


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


async def membership(
    session, team_id, user_id: int
) -> TeamMembership | None:
    result = await session.execute(
        select(TeamMembership)
        .where(TeamMembership.team_id == team_id)
        .where(TeamMembership.user_id == user_id)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def resolve_team_view(
    session,
    team_id,
    caller_user_id: int,
    member_user_id: int | None,
) -> int:
    """Decide whose data the caller is allowed to read in a team view.

    Members only ever see their own. The owner can pass an explicit
    ``member_user_id`` to drill into a teammate's CRM; everyone else
    gets a 403 if they try the same.
    """
    caller = await membership(session, team_id, caller_user_id)
    if caller is None:
        raise HTTPException(status_code=403, detail="not a team member")

    if member_user_id is None or member_user_id == caller_user_id:
        return caller_user_id

    if caller.role != "owner":
        raise HTTPException(
            status_code=403,
            detail="only the team owner can view another member",
        )
    target = await membership(session, team_id, member_user_id)
    if target is None:
        raise HTTPException(
            status_code=404, detail="that user isn't a team member"
        )
    return member_user_id


async def team_prior_searches(
    session,
    team_id,
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
    for i, (membership_row, user) in enumerate(rows):
        display = (
            user.display_name
            or " ".join(filter(None, [user.first_name, user.last_name]))
            or f"User {user.id}"
        )
        initials = (
            "".join(part[:1].upper() for part in display.split() if part)[:2]
            or display[:1].upper()
        )
        members.append(
            TeamMemberResponse(
                id=user.id,
                name=display,
                role=membership_row.role,
                description=membership_row.description,
                initials=initials,
                color=DEMO_TEAM_COLORS[i % len(DEMO_TEAM_COLORS)],
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


# ── Henry assistant background work ────────────────────────────────────


async def summarise_and_store(
    user_id: int,
    team_id,
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
