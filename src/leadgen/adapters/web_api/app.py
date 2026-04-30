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
import io
import json
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import sqlalchemy as sa
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest
from sqlalchemy import func, select, update
from sqlalchemy import text as sa_text
from sqlalchemy.exc import IntegrityError

from leadgen.adapters.web_api.schemas import (
    WEB_DEMO_USER_ID,
    AccountDeleteRequest,
    AccountDeleteResponse,
    AssistantMemoryDeleteResponse,
    AssistantMemoryItem,
    AssistantMemoryListResponse,
    AssistantRequest,
    AssistantResponse,
    AuditLogEntry,
    AuditLogListResponse,
    AuthUser,
    ChangeEmailRequest,
    ChangePasswordRequest,
    ConsultRequest,
    ConsultResponse,
    CsvImportRequest,
    CsvImportResponse,
    DashboardStats,
    DecisionMaker,
    DecisionMakersResponse,
    HealthResponse,
    InviteAcceptRequest,
    InviteCreateRequest,
    InvitePreview,
    InviteResponse,
    LeadActivityListResponse,
    LeadBulkUpdateRequest,
    LeadBulkUpdateResponse,
    LeadCustomFieldsResponse,
    LeadCustomFieldUpsert,
    LeadEmailDraftRequest,
    LeadEmailDraftResponse,
    LeadListResponse,
    LeadMarkRequest,
    LeadResponse,
    LeadTaskCreate,
    LeadTaskListResponse,
    LeadTaskUpdate,
    LeadUpdate,
    LoginRequest,
    MembershipUpdateRequest,
    NicheSuggestionsResponse,
    OutreachTemplateCreate,
    OutreachTemplateListResponse,
    OutreachTemplateUpdate,
    PendingAction,
    PriorTeamSearch,
    RegisterRequest,
    ResendVerificationRequest,
    SearchAxesResponse,
    SearchAxisOption,
    SearchCreate,
    SearchCreateResponse,
    SearchPreflightResponse,
    SearchSummary,
    TeamCreateRequest,
    TeamDetailResponse,
    TeamMemberResponse,
    TeamMemberSummary,
    TeamSummary,
    TeamUpdateRequest,
    UserProfile,
    UserProfileUpdate,
    VerifyEmailRequest,
    WeeklyCheckinResponse,
)
from leadgen.adapters.web_api.schemas import (
    LeadActivity as LeadActivitySchema,
)
from leadgen.adapters.web_api.schemas import (
    LeadCustomField as LeadCustomFieldSchema,
)
from leadgen.adapters.web_api.schemas import (
    LeadTask as LeadTaskSchema,
)
from leadgen.adapters.web_api.schemas import (
    OutreachTemplate as OutreachTemplateSchema,
)
from leadgen.adapters.web_api.sinks import WebDeliverySink
from leadgen.analysis.ai_analyzer import AIAnalyzer
from leadgen.config import get_settings
from leadgen.core.services import (
    BillingService,
    default_broker,
    render_verification_email,
    send_email,
)
from leadgen.core.services.assistant_memory import (
    load_memories,
    prune_old,
    record_memory,
    should_summarise,
)
from leadgen.core.services.progress_broker import BrokerProgressSink
from leadgen.db.models import (
    AssistantMemory,
    EmailVerificationToken,
    Lead,
    LeadActivity,
    LeadCustomField,
    LeadMark,
    LeadTask,
    OutreachTemplate,
    SearchQuery,
    Team,
    TeamInvite,
    TeamMembership,
    User,
    UserAuditLog,
)
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
    async def register(body: RegisterRequest, request: Request) -> AuthUser:
        """Sign up with email + password + first/last name (+ optional age).

        Minimal registration: name + email + password are required, an
        age range is optional. The user lands directly on /app — the
        rest of the profile (what they sell, niches, region) is filled
        from the workspace via a soft nudge banner or with Henry. The
        ``onboarded_at`` timestamp is stamped here so the gate check
        treats the account as ready immediately.
        """
        first = body.first_name.strip()
        last = body.last_name.strip()
        email = body.email.strip().lower()
        age_range = (body.age_range or "").strip() or None
        gender = (body.gender or "").strip().lower() or None
        if gender not in {None, "male", "female", "other"}:
            gender = None
        if not first or not last:
            raise HTTPException(
                status_code=400, detail="first_name and last_name are required"
            )
        if "@" not in email or "." not in email.split("@")[-1]:
            raise HTTPException(status_code=400, detail="invalid email")
        if len(body.password) < 8:
            raise HTTPException(
                status_code=400, detail="password must be at least 8 characters"
            )

        password_hash = _hash_password(body.password)
        now = datetime.now(timezone.utc)

        async with session_factory() as session:
            existing = (
                await session.execute(
                    select(User).where(func.lower(User.email) == email).limit(1)
                )
            ).scalar_one_or_none()
            if existing is not None:
                raise HTTPException(
                    status_code=409, detail="an account with this email already exists"
                )

            user: User | None = None
            for _ in range(5):
                new_id = -secrets.randbelow(2**53) - 1
                candidate = User(
                    id=new_id,
                    first_name=first,
                    last_name=last,
                    display_name=f"{first} {last}".strip(),
                    email=email,
                    password_hash=password_hash,
                    age_range=age_range,
                    gender=gender,
                    queries_used=0,
                    queries_limit=100000,
                    onboarded_at=now,
                )
                session.add(candidate)
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    continue
                user = candidate
                break
            if user is None:
                raise HTTPException(
                    status_code=500, detail="failed to allocate a user id"
                )

            await _issue_and_send_verification(session, user)
            await _record_audit(
                session,
                user_id=user.id,
                action="auth.register",
                request=request,
                payload={"email": email},
            )
            await session.commit()

        return AuthUser(
            user_id=user.id,
            first_name=first,
            last_name=last,
            email=email,
            email_verified=False,
            onboarded=True,
        )

    @app.post("/api/v1/auth/login", response_model=AuthUser)
    async def login(body: LoginRequest, request: Request) -> AuthUser:
        """Email + password login. Returns the shared AuthUser shape."""
        email = body.email.strip().lower()
        async with session_factory() as session:
            user = (
                await session.execute(
                    select(User).where(func.lower(User.email) == email).limit(1)
                )
            ).scalar_one_or_none()
            if (
                user is None
                or not user.password_hash
                or not _verify_password(body.password, user.password_hash)
            ):
                # Same generic error for missing user / bad password
                # so the endpoint isn't an email-existence oracle.
                raise HTTPException(
                    status_code=401, detail="invalid email or password"
                )
            await _record_audit(
                session,
                user_id=user.id,
                action="auth.login",
                request=request,
            )
            await session.commit()
            return AuthUser(
                user_id=user.id,
                first_name=user.first_name or "",
                last_name=user.last_name or "",
                email=user.email,
                email_verified=user.email_verified_at is not None,
                onboarded=_is_onboarded(user),
            )

    @app.post("/api/v1/auth/verify-email", response_model=AuthUser)
    async def verify_email(body: VerifyEmailRequest) -> AuthUser:
        """Confirm a pending email-verification token.

        Single-use: marks the token spent, stamps the user's
        email_verified_at, and returns the refreshed AuthUser so the
        frontend can swap its local state.
        """
        async with session_factory() as session:
            row = (
                await session.execute(
                    select(EmailVerificationToken, User)
                    .join(User, User.id == EmailVerificationToken.user_id)
                    .where(EmailVerificationToken.token == body.token)
                    .where(
                        EmailVerificationToken.kind.in_(
                            ["verify", "change_email"]
                        )
                    )
                    .limit(1)
                )
            ).first()
            if row is None:
                raise HTTPException(status_code=404, detail="token not found")
            token_row, user = row
            now = datetime.now(timezone.utc)
            already_used = token_row.used_at is not None
            expires = token_row.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            expired = now >= expires

            # Idempotent re-click: if the token is already used AND
            # the user is already verified (or in change_email mode,
            # the pending email already landed on the user row), treat
            # the request as success. This neutralises the email-
            # scanner-burns-token problem: the scanner spent the token
            # while pre-fetching, the user's actual click then sees
            # "already used" — but the verification did happen, so
            # we shouldn't block them.
            if already_used and not expired:
                if token_row.kind == "verify" and user.email_verified_at is not None:
                    return AuthUser(
                        user_id=user.id,
                        first_name=user.first_name or "",
                        last_name=user.last_name or "",
                        email=user.email,
                        email_verified=True,
                        onboarded=_is_onboarded(user),
                    )
                if (
                    token_row.kind == "change_email"
                    and token_row.pending_email
                    and user.email
                    and user.email.lower() == token_row.pending_email.lower()
                ):
                    return AuthUser(
                        user_id=user.id,
                        first_name=user.first_name or "",
                        last_name=user.last_name or "",
                        email=user.email,
                        email_verified=True,
                        onboarded=_is_onboarded(user),
                    )

            if already_used:
                raise HTTPException(status_code=410, detail="token already used")
            if expired:
                raise HTTPException(status_code=410, detail="token expired")

            token_row.used_at = now
            if token_row.kind == "change_email" and token_row.pending_email:
                # Make sure the address is still free (someone may have
                # registered it in the time between request and click).
                conflict = (
                    await session.execute(
                        select(User)
                        .where(
                            func.lower(User.email)
                            == token_row.pending_email.lower()
                        )
                        .where(User.id != user.id)
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if conflict is not None:
                    raise HTTPException(
                        status_code=409,
                        detail="this email is already taken",
                    )
                user.email = token_row.pending_email
                user.email_verified_at = now
            elif user.email_verified_at is None:
                user.email_verified_at = now
            await session.commit()

            return AuthUser(
                user_id=user.id,
                first_name=user.first_name or "",
                last_name=user.last_name or "",
                email=user.email,
                email_verified=True,
                onboarded=_is_onboarded(user),
            )

    @app.post("/api/v1/auth/resend-verification")
    async def resend_verification(body: ResendVerificationRequest) -> dict[str, bool]:
        """Resend the verification email for a not-yet-verified account.

        Always returns ``{"sent": true}`` — even if the email isn't on
        file — so this endpoint can't be used to enumerate accounts.
        """
        email = body.email.strip().lower()
        async with session_factory() as session:
            user = (
                await session.execute(
                    select(User).where(func.lower(User.email) == email).limit(1)
                )
            ).scalar_one_or_none()
            if user is not None and user.email_verified_at is None:
                await _issue_and_send_verification(session, user)
        return {"sent": True}

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
            if "gender" in data:
                g = (data["gender"] or "").strip().lower() or None
                user.gender = g if g in {"male", "female", "other"} else None
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
                    # Bound Anthropic normalisation tightly so the PATCH
                    # never blocks the browser on a slow LLM round-trip.
                    # If we can't get a polished version in 8s we keep
                    # the raw text — the AI pipeline survives raw input
                    # and the user's save still feels instantaneous.
                    try:
                        user.profession = (
                            await asyncio.wait_for(
                                AIAnalyzer().normalize_profession(raw),
                                timeout=8.0,
                            )
                        ) or raw
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "normalize_profession failed/timed out; storing raw text"
                        )
                        user.profession = raw
                else:
                    user.service_description = None
                    user.profession = None

            # Backfill onboarded_at for legacy accounts that registered
            # before the relaxed gate landed. Newly-registered web users
            # already have it set on /auth/register.
            if user.onboarded_at is None and (
                user.display_name or user.first_name
            ):
                user.onboarded_at = datetime.now(timezone.utc)

            await session.commit()
            await session.refresh(user)
            return _to_profile(user)

    @app.post("/api/v1/users/{user_id}/change-email", response_model=AuthUser)
    async def change_email(
        user_id: int, body: ChangeEmailRequest
    ) -> AuthUser:
        """Initiate an email change.

        Validates the current password (so a stolen session can't
        silently swap the recovery address), checks the new address
        isn't already in use, and emails a confirmation link to the
        NEW address. The user's actual email only changes after that
        link is clicked — until then login keeps working with the old
        address.
        """
        new_email = body.new_email.strip().lower()
        if "@" not in new_email or "." not in new_email.split("@")[-1]:
            raise HTTPException(status_code=400, detail="invalid email")

        async with session_factory() as session:
            user = await session.get(User, user_id)
            if user is None:
                raise HTTPException(status_code=404, detail="user not found")
            if not user.password_hash or not _verify_password(
                body.password, user.password_hash
            ):
                raise HTTPException(
                    status_code=401, detail="password is incorrect"
                )
            if user.email and user.email.lower() == new_email:
                raise HTTPException(
                    status_code=400,
                    detail="that's already your current email",
                )
            existing = (
                await session.execute(
                    select(User)
                    .where(func.lower(User.email) == new_email)
                    .where(User.id != user.id)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if existing is not None:
                raise HTTPException(
                    status_code=409,
                    detail="this email is already taken",
                )

            await _issue_and_send_change_email(session, user, new_email)

        return AuthUser(
            user_id=user.id,
            first_name=user.first_name or "",
            last_name=user.last_name or "",
            email=user.email,
            email_verified=user.email_verified_at is not None,
            onboarded=_is_onboarded(user),
        )

    @app.post("/api/v1/users/{user_id}/change-password", response_model=AuthUser)
    async def change_password(
        user_id: int, body: ChangePasswordRequest
    ) -> AuthUser:
        """Update the password. Requires the current one."""
        async with session_factory() as session:
            user = await session.get(User, user_id)
            if user is None:
                raise HTTPException(status_code=404, detail="user not found")
            if not user.password_hash or not _verify_password(
                body.current_password, user.password_hash
            ):
                raise HTTPException(
                    status_code=401, detail="current password is incorrect"
                )
            if len(body.new_password) < 8:
                raise HTTPException(
                    status_code=400,
                    detail="new password must be at least 8 characters",
                )
            user.password_hash = _hash_password(body.new_password)
            await session.commit()

        return AuthUser(
            user_id=user.id,
            first_name=user.first_name or "",
            last_name=user.last_name or "",
            email=user.email,
            email_verified=user.email_verified_at is not None,
            onboarded=_is_onboarded(user),
        )

    # ── /api/v1/users/{id}/gdpr ───────────────────────────────────────

    @app.get("/api/v1/users/{user_id}/audit-log", response_model=AuditLogListResponse)
    async def list_audit_log(user_id: int) -> AuditLogListResponse:
        """Return the most recent 200 audit-log entries for a user."""
        async with session_factory() as session:
            user = await session.get(User, user_id)
            if user is None:
                raise HTTPException(status_code=404, detail="user not found")
            rows = (
                (
                    await session.execute(
                        select(UserAuditLog)
                        .where(UserAuditLog.user_id == user_id)
                        .order_by(UserAuditLog.created_at.desc())
                        .limit(200)
                    )
                )
                .scalars()
                .all()
            )
            return AuditLogListResponse(
                items=[AuditLogEntry.model_validate(r) for r in rows]
            )

    @app.get("/api/v1/users/{user_id}/export")
    async def gdpr_export(user_id: int, request: Request) -> JSONResponse:
        """Download a JSON dump of everything we store about this user.

        Covers: profile, sessions, leads, custom fields, activity, tasks,
        memories, marks, outreach templates, audit log. The file is a
        plain JSON document the user can save / forward; we also write
        an audit-log entry so the export itself is recorded.
        """
        async with session_factory() as session:
            user = await session.get(User, user_id)
            if user is None:
                raise HTTPException(status_code=404, detail="user not found")

            sessions = list(
                (
                    await session.execute(
                        select(SearchQuery).where(SearchQuery.user_id == user_id)
                    )
                ).scalars()
            )
            leads = list(
                (
                    await session.execute(
                        select(Lead).where(Lead.user_id == user_id)
                    )
                ).scalars()
            )
            custom_fields = list(
                (
                    await session.execute(
                        select(LeadCustomField).where(
                            LeadCustomField.user_id == user_id
                        )
                    )
                ).scalars()
            )
            activities = list(
                (
                    await session.execute(
                        select(LeadActivity).where(LeadActivity.user_id == user_id)
                    )
                ).scalars()
            )
            tasks = list(
                (
                    await session.execute(
                        select(LeadTask).where(LeadTask.user_id == user_id)
                    )
                ).scalars()
            )
            memories = list(
                (
                    await session.execute(
                        select(AssistantMemory).where(
                            AssistantMemory.user_id == user_id
                        )
                    )
                ).scalars()
            )
            marks = list(
                (
                    await session.execute(
                        select(LeadMark).where(LeadMark.user_id == user_id)
                    )
                ).scalars()
            )
            templates = list(
                (
                    await session.execute(
                        select(OutreachTemplate).where(
                            OutreachTemplate.user_id == user_id
                        )
                    )
                ).scalars()
            )
            audit = list(
                (
                    await session.execute(
                        select(UserAuditLog)
                        .where(UserAuditLog.user_id == user_id)
                        .order_by(UserAuditLog.created_at.desc())
                    )
                ).scalars()
            )

            def _dt(value: Any) -> Any:
                if isinstance(value, datetime):
                    return value.isoformat()
                if isinstance(value, uuid.UUID):
                    return str(value)
                return value

            def _row(obj: Any) -> dict[str, Any]:
                return {
                    c.name: _dt(getattr(obj, c.name))
                    for c in obj.__table__.columns
                }

            payload = {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "user": _row(user),
                "sessions": [_row(s) for s in sessions],
                "leads": [_row(lead) for lead in leads],
                "lead_custom_fields": [_row(c) for c in custom_fields],
                "lead_activities": [_row(a) for a in activities],
                "lead_tasks": [_row(t) for t in tasks],
                "assistant_memories": [_row(m) for m in memories],
                "lead_marks": [_row(m) for m in marks],
                "outreach_templates": [_row(t) for t in templates],
                "audit_log": [_row(a) for a in audit],
            }

            await _record_audit(
                session,
                user_id=user_id,
                action="gdpr.export",
                request=request,
                payload={
                    "leads": len(leads),
                    "sessions": len(sessions),
                },
            )
            await session.commit()

            filename = f"convioo-export-user-{user_id}.json"
            return JSONResponse(
                content=payload,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"'
                },
            )

    @app.delete(
        "/api/v1/users/{user_id}",
        response_model=AccountDeleteResponse,
    )
    async def delete_account(
        user_id: int,
        body: AccountDeleteRequest,
        request: Request,
    ) -> AccountDeleteResponse:
        """Hard-delete a user account.

        Requires the caller to confirm by retyping their email; if the
        user has a password, that's verified too. ``ondelete=CASCADE``
        on the FKs takes care of leads, sessions, custom fields and
        the rest of the per-user data. The audit log row is written
        BEFORE the cascade because deleting the user wipes its own
        history. We log to a separate ``logger.warning`` line so ops
        can still see deletions in the application logs.
        """
        async with session_factory() as session:
            user = await session.get(User, user_id)
            if user is None:
                raise HTTPException(status_code=404, detail="user not found")

            confirm = body.confirm_email.strip().lower()
            if not user.email or confirm != user.email.lower():
                raise HTTPException(
                    status_code=400,
                    detail="email does not match the account",
                )
            if user.password_hash and (
                not body.password
                or not _verify_password(body.password, user.password_hash)
            ):
                raise HTTPException(
                    status_code=401, detail="password is incorrect"
                )

            logger.warning(
                "account deletion: user_id=%s email=%s ip=%s",
                user.id,
                user.email,
                _request_ip(request),
            )

            await session.delete(user)
            await session.commit()

        return AccountDeleteResponse(deleted=True)

    # ── /api/v1/teams ──────────────────────────────────────────────────

    @app.post("/api/v1/teams", response_model=TeamDetailResponse)
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
            await session.commit()
            await session.refresh(team)

            return await _team_detail(session, team, owner.id)

    @app.get("/api/v1/teams", response_model=list[TeamSummary])
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
            for membership, team in rows:
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
                        role=membership.role,
                        member_count=int(count or 0),
                        created_at=team.created_at,
                    )
                )
            return results

    @app.get("/api/v1/teams/{team_id}", response_model=TeamDetailResponse)
    async def get_team(team_id: uuid.UUID, user_id: int) -> TeamDetailResponse:
        async with session_factory() as session:
            team = await session.get(Team, team_id)
            if team is None:
                raise HTTPException(status_code=404, detail="team not found")
            return await _team_detail(session, team, user_id)

    @app.patch("/api/v1/teams/{team_id}", response_model=TeamDetailResponse)
    async def update_team(
        team_id: uuid.UUID, body: TeamUpdateRequest
    ) -> TeamDetailResponse:
        """Owner-only PATCH for the team's name + description."""
        async with session_factory() as session:
            team = await session.get(Team, team_id)
            if team is None:
                raise HTTPException(status_code=404, detail="team not found")
            membership = await _membership(session, team_id, body.by_user_id)
            if membership is None or membership.role != "owner":
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
            return await _team_detail(session, team, body.by_user_id)

    @app.patch(
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
            caller = await _membership(session, team_id, body.by_user_id)
            if caller is None or caller.role != "owner":
                raise HTTPException(
                    status_code=403,
                    detail="only the team owner can edit members",
                )
            target = await _membership(session, team_id, member_user_id)
            if target is None:
                raise HTTPException(
                    status_code=404, detail="that user isn't a team member"
                )

            data = body.model_dump(exclude_unset=True)
            if "description" in data:
                desc = (data["description"] or "").strip()
                target.description = desc or None
            if "role" in data and data["role"]:
                # Don't let an owner accidentally demote themselves into
                # an ownerless team — re-promotion would need DB access.
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
            return await _team_detail(session, team, body.by_user_id)

    @app.post("/api/v1/teams/{team_id}/invites", response_model=InviteResponse)
    async def create_invite(
        team_id: uuid.UUID, body: InviteCreateRequest
    ) -> InviteResponse:
        async with session_factory() as session:
            team = await session.get(Team, team_id)
            if team is None:
                raise HTTPException(status_code=404, detail="team not found")

            membership = await _membership(session, team_id, body.by_user_id)
            if membership is None or membership.role != "owner":
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

    @app.get("/api/v1/teams/invites/{token}", response_model=InvitePreview)
    async def preview_invite(token: str) -> InvitePreview:
        async with session_factory() as session:
            invite, team = await _load_invite(session, token)
            return InvitePreview(
                team_id=team.id,
                team_name=team.name,
                role=invite.role,
                expires_at=invite.expires_at,
                expired=_invite_expired(invite),
                accepted=invite.accepted_at is not None,
            )

    @app.post(
        "/api/v1/teams/invites/{token}/accept",
        response_model=TeamDetailResponse,
    )
    async def accept_invite(
        token: str, body: InviteAcceptRequest
    ) -> TeamDetailResponse:
        async with session_factory() as session:
            invite, team = await _load_invite(session, token)
            if invite.accepted_at is not None:
                raise HTTPException(
                    status_code=410, detail="invite already used"
                )
            if _invite_expired(invite):
                raise HTTPException(
                    status_code=410, detail="invite expired"
                )

            user = await session.get(User, body.user_id)
            if user is None:
                raise HTTPException(status_code=404, detail="user not found")

            existing = await _membership(session, team.id, user.id)
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
            return await _team_detail(session, team, user.id)

    # ── /api/v1/search/consult ─────────────────────────────────────────

    @app.post("/api/v1/search/consult", response_model=ConsultResponse)
    async def search_consult(body: ConsultRequest) -> ConsultResponse:
        """One turn of the search-composer dialogue.

        The client owns the conversation; on every user message it
        POSTs the full history. Backend asks Claude to pick the next
        question and to refresh its best-guess slot values, then
        returns both. Falls back to a heuristic prompt if the model
        is unavailable so the chat never freezes.
        """
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

    @app.post("/api/v1/assistant/chat", response_model=AssistantResponse)
    async def assistant_chat(body: AssistantRequest) -> AssistantResponse:
        """Floating in-product assistant — Henry, confirm-before-write.

        Personal mode (no team_id): Henry helps with product Q&A,
        sales coaching, and profile editing.
        Team mode (team_id set): Henry knows the team + member roster.
        Owners additionally can confirm team / per-member description
        edits.

        Confirm-before-write flow: Henry never mutates state silently.
        He returns ``pending_actions``; the client echoes them back on
        the next turn and if the user replied with «да / yes / ок»
        we apply them here without another LLM round-trip. «Нет» short-
        circuits to a brief refusal so Henry can refine on the next
        turn.
        """
        team_context: dict[str, Any] | None = None
        async with session_factory() as session:
            if body.team_id is not None:
                team = await session.get(Team, body.team_id)
                if team is None:
                    raise HTTPException(status_code=404, detail="team not found")
                membership = await _membership(
                    session, body.team_id, body.user_id
                )
                if membership is None:
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
                for m, u in rows:
                    display = (
                        u.display_name
                        or " ".join(filter(None, [u.first_name, u.last_name]))
                        or f"User {u.id}"
                    )
                    members_payload.append(
                        {
                            "user_id": u.id,
                            "name": display,
                            "role": m.role,
                            "description": m.description,
                        }
                    )
                team_context = {
                    "team_id": str(team.id),
                    "name": team.name,
                    "description": team.description,
                    "is_owner": membership.role == "owner",
                    "viewer_user_id": body.user_id,
                    "members": members_payload,
                }

        is_team = bool(team_context)
        is_owner = bool(team_context and team_context.get("is_owner"))
        mode = (
            "team_owner" if is_owner else "team_member" if is_team else "personal"
        )

        # Confirm-before-write short-circuit — if the user's whole
        # message is "да" / "нет" AND the client echoed back the actions
        # Henry proposed last turn, we apply (or refuse) without an LLM
        # call. The reply is canned so it stays snappy.
        last_user_text = ""
        for m in reversed(body.messages):
            if m.role == "user":
                last_user_text = m.content.strip()
                break

        if body.pending_actions and last_user_text:
            verdict = _detect_confirmation(last_user_text)
            if verdict == "confirm":
                async with session_factory() as session:
                    user = await session.get(User, body.user_id)
                    applied = await _apply_pending_actions(
                        session, user, team_context, body.pending_actions
                    )
                if applied:
                    return AssistantResponse(
                        reply="Готово — записал. Что-то ещё?",
                        mode=mode,
                        applied_actions=applied,
                        awaiting_field=None,
                    )
                # Fall through if nothing applied (e.g. stale payload).
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

        # Workspace isolation: in team mode Henry must NOT see the
        # caller's personal profile (what they sell, their personal
        # niches, region) — that's a different workspace and bleeding
        # personal context into team chat is exactly what the user
        # asked us to stop. We still pass display_name / gender so
        # Henry can address the person properly.
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

        pending = _result_to_pending_actions(result, mode)

        # Best-effort summarisation in the background — every N user
        # messages we ask Henry to distill the recent dialogue into a
        # summary + facts and persist them. The chat reply ships back
        # immediately; the memory write happens after.
        if should_summarise(history):
            asyncio.create_task(
                _summarise_and_store(
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

    @app.get(
        "/api/v1/users/{user_id}/assistant-memory",
        response_model=AssistantMemoryListResponse,
    )
    async def list_assistant_memory(
        user_id: int,
        team_id: uuid.UUID | None = None,
    ) -> AssistantMemoryListResponse:
        """Surface what Henry remembers about this user.

        Personal call (no team_id) — only the personal memories.
        Team call — personal + team-scoped (matches the prompt-time
        union so what the user sees here equals what Henry sees).
        """
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

    @app.delete(
        "/api/v1/users/{user_id}/assistant-memory",
        response_model=AssistantMemoryDeleteResponse,
    )
    async def clear_assistant_memory(
        user_id: int,
        team_id: uuid.UUID | None = None,
    ) -> AssistantMemoryDeleteResponse:
        """Wipe Henry's memory for this user (and optionally for a team).

        Personal call clears personal memories only — team-scoped
        rows are preserved (a team member can't single-handedly erase
        notes the team relies on).
        Team call (team_id set) clears both that user's personal
        memories AND team-scoped rows authored by them.
        """
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

    @app.post(
        "/api/v1/search/suggest-axes",
        response_model=SearchAxesResponse,
    )
    async def suggest_search_axes(user_id: int) -> SearchAxesResponse:
        """Henry-proposed ready-to-launch search configurations.

        Returns up to 4 ``{niche, region, ideal_customer, exclusions,
        rationale}`` cards based on what we know about the user. Used
        by the "Подобрать с Henry" button on /app/search to one-click
        prefill the form when the user doesn't want to type.
        """
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

    @app.get(
        "/api/v1/users/{user_id}/weekly-checkin",
        response_model=WeeklyCheckinResponse,
    )
    async def weekly_checkin(
        user_id: int,
        team_id: uuid.UUID | None = None,
        member_user_id: int | None = None,
    ) -> WeeklyCheckinResponse:
        """Henry's short read on the user's recent CRM activity.

        Computes a fresh stats snapshot from the lead / search tables
        scoped to the active workspace (personal / team / view-as)
        and feeds it to ``AIAnalyzer.weekly_checkin`` for a
        human-friendly summary + 1-3 highlight chips.
        """
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        cutoff_14 = now - timedelta(days=14)

        async with session_factory() as session:
            user = await session.get(User, user_id)
            if user is None:
                raise HTTPException(status_code=404, detail="user not found")

            if team_id is not None:
                target_user = await _resolve_team_view(
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

    # ── /api/v1/templates ──────────────────────────────────────────────

    @app.get(
        "/api/v1/templates",
        response_model=OutreachTemplateListResponse,
    )
    async def list_templates(
        user_id: int,
        team_id: uuid.UUID | None = None,
    ) -> OutreachTemplateListResponse:
        """User-managed outreach template library.

        Personal call returns only the caller's personal templates.
        Team call (team_id set) unions personal + every template
        scoped to that team — same pattern as memory / leads.
        """
        async with session_factory() as session:
            stmt = select(OutreachTemplate).where(
                OutreachTemplate.user_id == user_id
            )
            if team_id is not None:
                stmt = stmt.where(
                    (OutreachTemplate.team_id == team_id)
                    | (OutreachTemplate.team_id.is_(None))
                )
            else:
                stmt = stmt.where(OutreachTemplate.team_id.is_(None))
            stmt = stmt.order_by(OutreachTemplate.updated_at.desc())
            rows = (await session.execute(stmt)).scalars().all()
            items = [OutreachTemplateSchema.model_validate(r) for r in rows]
        return OutreachTemplateListResponse(items=items)

    @app.post("/api/v1/templates", response_model=OutreachTemplateSchema)
    async def create_template(
        body: OutreachTemplateCreate,
        user_id: int,
    ) -> OutreachTemplateSchema:
        """Create a new outreach template owned by ``user_id``."""
        async with session_factory() as session:
            row = OutreachTemplate(
                user_id=user_id,
                team_id=body.team_id,
                name=body.name.strip(),
                subject=(body.subject or "").strip() or None,
                body=body.body.strip(),
                tone=(body.tone or "professional").strip().lower() or "professional",
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return OutreachTemplateSchema.model_validate(row)

    @app.patch(
        "/api/v1/templates/{template_id}",
        response_model=OutreachTemplateSchema,
    )
    async def update_template(
        template_id: uuid.UUID,
        body: OutreachTemplateUpdate,
        user_id: int,
    ) -> OutreachTemplateSchema:
        async with session_factory() as session:
            row = await session.get(OutreachTemplate, template_id)
            if row is None or row.user_id != user_id:
                raise HTTPException(status_code=404, detail="template not found")
            data = body.model_dump(exclude_unset=True)
            if "name" in data and data["name"]:
                row.name = data["name"].strip()
            if "subject" in data:
                row.subject = (data["subject"] or "").strip() or None
            if "body" in data and data["body"]:
                row.body = data["body"].strip()
            if "tone" in data and data["tone"]:
                row.tone = data["tone"].strip().lower()
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(row)
            return OutreachTemplateSchema.model_validate(row)

    @app.delete("/api/v1/templates/{template_id}")
    async def delete_template(
        template_id: uuid.UUID,
        user_id: int,
    ) -> dict[str, bool]:
        async with session_factory() as session:
            row = await session.get(OutreachTemplate, template_id)
            if row is None or row.user_id != user_id:
                raise HTTPException(status_code=404, detail="template not found")
            await session.delete(row)
            await session.commit()
        return {"deleted": True}

    @app.post(
        "/api/v1/leads/{lead_id}/enrich/decision-makers",
        response_model=DecisionMakersResponse,
    )
    async def enrich_decision_makers(
        lead_id: uuid.UUID,
        user_id: int = WEB_DEMO_USER_ID,
    ) -> DecisionMakersResponse:
        """Henry pulls decision-maker contacts from the lead's site.

        Best-effort: empty list when the lead has no website, no API
        key, or the site refuses to load. Successfully extracted
        people are also written into ``lead_custom_fields`` (one row
        per person, key = ``decision_maker_N``) so they show up on
        the lead detail timeline + are exportable via CSV.
        """
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

        # Persist into custom fields so the timeline shows what Henry
        # found and the data survives session refreshes.
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

    @app.post(
        "/api/v1/searches/import-csv",
        response_model=CsvImportResponse,
    )
    async def import_search_csv(body: CsvImportRequest) -> CsvImportResponse:
        """Bulk-import a list of companies as a synthetic search session.

        The frontend parses the user's CSV client-side and posts the
        cleaned rows here. We create one ``SearchQuery`` row to act
        as the parent session (so the leads show up under
        ``/app/sessions/{id}``) and one ``Lead`` row per CSV row.
        Anything beyond the standard columns ends up as custom fields.
        Web-source so the existing CRM / dedup paths handle them.

        AI scoring is NOT triggered automatically on import — the
        caller can run ``research_lead_for_outreach`` /
        ``draft-email`` per row when needed. Keeps the import fast
        for 100+ row uploads and predictable on cost.
        """
        if body.team_id is not None:
            async with session_factory() as session:
                membership = await _membership(
                    session, body.team_id, body.user_id
                )
                if membership is None:
                    raise HTTPException(
                        status_code=403, detail="not a team member"
                    )

        async with session_factory() as session:
            # First non-empty region in the rows wins as the parent
            # search's region, with a sane fallback so /app/sessions
            # has something readable in the breadcrumb.
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

                # Stuff every "extra" CSV column into custom fields so
                # the user keeps full visibility on what they
                # imported.
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

    @app.post(
        "/api/v1/users/{user_id}/suggest-niches",
        response_model=NicheSuggestionsResponse,
    )
    async def suggest_niches(user_id: int) -> NicheSuggestionsResponse:
        """Henry-proposed target niches based on the user's offer.

        Reads ``service_description`` (falling back to ``profession``)
        and asks Claude for up to 8 fresh niche ideas — short
        Maps-friendly phrases that match what the user actually sells.
        Already-saved niches are excluded server-side so the user
        always sees options they don't yet have.
        """
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

    # ── /api/v1/searches ───────────────────────────────────────────────

    @app.get(
        "/api/v1/searches/preflight",
        response_model=SearchPreflightResponse,
    )
    async def search_preflight(
        user_id: int,
        niche: str,
        region: str,
        team_id: uuid.UUID | None = None,
    ) -> SearchPreflightResponse:
        """Tell the UI whether this niche+region combo is safe to run.

        In personal mode it's always safe (no cross-user collision
        rule). In team mode the same combo is hard-blocked — return
        the prior matches so the UI can show "already done by Иван"
        instead of letting the user click Launch.
        """
        if team_id is None:
            return SearchPreflightResponse(blocked=False, matches=[])
        async with session_factory() as session:
            membership = await _membership(session, team_id, user_id)
            if membership is None:
                raise HTTPException(status_code=403, detail="not a team member")
            matches = await _team_prior_searches(session, team_id, niche, region)
        return SearchPreflightResponse(blocked=bool(matches), matches=matches)

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
            # Email-verification gate. Web users (id < 0) must confirm
            # the email on file before they can launch a search. Telegram
            # users (id > 0) and the seeded demo (id = 0) bypass — they
            # don't have an email column populated.
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
                membership = await _membership(session, team_id, body.user_id)
                if membership is None:
                    raise HTTPException(
                        status_code=403,
                        detail="user is not a member of this team",
                    )
                prior = await _team_prior_searches(
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
            # No Redis → run inline. Fire-and-forget; progress is streamed
            # over the broker, so the HTTP response can return immediately.
            asyncio.create_task(
                _run_web_search_inline(query.id, user_profile or None),
                name=f"convioo-web-search-{query.id}",
            )

        return SearchCreateResponse(id=query.id, queued=queued)

    @app.get("/api/v1/searches", response_model=list[SearchSummary])
    async def list_searches(
        user_id: int = WEB_DEMO_USER_ID,
        team_id: uuid.UUID | None = None,
        member_user_id: int | None = None,
        limit: int = 50,
    ) -> list[SearchSummary]:
        """List searches for a workspace.

        Personal mode (``team_id`` unset): caller's own ``team_id IS NULL`` rows.
        Team mode (``team_id`` set): caller's own rows inside that team
        by default. ``member_user_id`` lets a team owner peek into a
        specific teammate's CRM; non-owners get 403.
        """
        limit = max(1, min(limit, 200))
        async with session_factory() as session:
            stmt = (
                select(SearchQuery)
                .order_by(SearchQuery.created_at.desc())
                .limit(limit)
            )
            if team_id is not None:
                target_user = await _resolve_team_view(
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
        user_id: int = WEB_DEMO_USER_ID,
    ) -> list[LeadResponse]:
        """All leads for one search. Optional ?temp=hot|warm|cold filter
        (computed from score_ai, not a DB column, so it happens in Python).

        ``user_id`` selects whose private colour marks to attach via
        the ``mark_color`` field on each row.
        """
        async with session_factory() as session:
            result = await session.execute(
                select(Lead)
                .where(Lead.query_id == search_id)
                .order_by(Lead.score_ai.desc().nullslast(), Lead.rating.desc().nullslast())
            )
            leads = list(result.scalars().all())
            marks = await _marks_for_user(
                session, user_id, [lead.id for lead in leads]
            )

        if temp in {"hot", "warm", "cold"}:
            leads = [lead for lead in leads if _temp(lead.score_ai) == temp]
        return [_to_lead_response(lead, marks.get(lead.id)) for lead in leads]

    @app.get("/api/v1/leads", response_model=LeadListResponse)
    async def list_all_leads(
        user_id: int = WEB_DEMO_USER_ID,
        team_id: uuid.UUID | None = None,
        member_user_id: int | None = None,
        lead_status: str | None = None,
        temp: str | None = None,
        created_after: datetime | None = None,
        untouched_days: int | None = None,
        limit: int = 200,
    ) -> LeadListResponse:
        """Cross-session CRM listing.

        Personal mode → caller's own leads. Team mode → caller's own
        leads inside that team by default. Team owners can pass
        ``member_user_id`` to inspect a specific teammate's CRM.

        Filter knobs the frontend's smart-filter chips lean on:
        - ``temp`` ∈ {"hot","warm","cold"} → filters by score buckets
          (hot ≥ 75, warm 50-74, cold < 50).
        - ``created_after`` → ISO timestamp; "новые сегодня" / "за неделю".
        - ``untouched_days`` → leads whose ``last_touched_at`` is older
          than N days (or never touched at all). "Без касания 14+ дней".

        ``mark_color`` on each row is always the *caller's* private
        mark (never the viewed-as user's), so an owner browsing a
        teammate's CRM still sees their own colour codes.
        """
        limit = max(1, min(limit, 500))
        async with session_factory() as session:
            stmt = (
                select(Lead, SearchQuery.niche, SearchQuery.region)
                .join(SearchQuery, SearchQuery.id == Lead.query_id)
                .where(SearchQuery.source == "web")
                .order_by(Lead.score_ai.desc().nullslast(), Lead.created_at.desc())
                .limit(limit)
            )
            total_stmt = (
                select(func.count(Lead.id))
                .join(SearchQuery, SearchQuery.id == Lead.query_id)
                .where(SearchQuery.source == "web")
            )
            if team_id is not None:
                target_user = await _resolve_team_view(
                    session, team_id, user_id, member_user_id
                )
                stmt = stmt.where(SearchQuery.team_id == team_id).where(
                    SearchQuery.user_id == target_user
                )
                total_stmt = total_stmt.where(
                    SearchQuery.team_id == team_id
                ).where(SearchQuery.user_id == target_user)
            else:
                stmt = stmt.where(SearchQuery.user_id == user_id).where(
                    SearchQuery.team_id.is_(None)
                )
                total_stmt = total_stmt.where(
                    SearchQuery.user_id == user_id
                ).where(SearchQuery.team_id.is_(None))
            if lead_status:
                stmt = stmt.where(Lead.lead_status == lead_status)
                total_stmt = total_stmt.where(Lead.lead_status == lead_status)
            if temp == "hot":
                stmt = stmt.where(Lead.score_ai >= 75)
                total_stmt = total_stmt.where(Lead.score_ai >= 75)
            elif temp == "warm":
                stmt = stmt.where(Lead.score_ai >= 50).where(Lead.score_ai < 75)
                total_stmt = total_stmt.where(Lead.score_ai >= 50).where(
                    Lead.score_ai < 75
                )
            elif temp == "cold":
                stmt = stmt.where(
                    (Lead.score_ai < 50) | (Lead.score_ai.is_(None))
                )
                total_stmt = total_stmt.where(
                    (Lead.score_ai < 50) | (Lead.score_ai.is_(None))
                )
            if created_after is not None:
                stmt = stmt.where(Lead.created_at >= created_after)
                total_stmt = total_stmt.where(Lead.created_at >= created_after)
            if untouched_days and untouched_days > 0:
                cutoff = datetime.now(timezone.utc) - timedelta(
                    days=untouched_days
                )
                stmt = stmt.where(
                    (Lead.last_touched_at < cutoff)
                    | (Lead.last_touched_at.is_(None))
                )
                total_stmt = total_stmt.where(
                    (Lead.last_touched_at < cutoff)
                    | (Lead.last_touched_at.is_(None))
                )
            rows = (await session.execute(stmt)).all()

            total = int((await session.execute(total_stmt)).scalar() or 0)
            marks = await _marks_for_user(
                session, user_id, [lead.id for lead, _n, _r in rows]
            )

        leads: list[LeadResponse] = []
        sessions_by_id: dict[str, dict[str, Any]] = {}
        for lead, niche, region in rows:
            leads.append(_to_lead_response(lead, marks.get(lead.id)))
            sessions_by_id[str(lead.query_id)] = {"niche": niche, "region": region}
        return LeadListResponse(leads=leads, total=total, sessions_by_id=sessions_by_id)

    @app.get("/api/v1/leads/export.csv", include_in_schema=False)
    async def export_leads_csv(
        user_id: int = WEB_DEMO_USER_ID,
        team_id: uuid.UUID | None = None,
        member_user_id: int | None = None,
    ) -> Response:
        """Export the caller's CRM rows as a CSV file.

        Mirrors the same scoping as the JSON list endpoint (personal /
        team / view-as) but ignores the smart-filter knobs — export
        is always "everything in this scope" so the file is the
        complete copy.
        """
        async with session_factory() as session:
            stmt = (
                select(Lead, SearchQuery.niche, SearchQuery.region)
                .join(SearchQuery, SearchQuery.id == Lead.query_id)
                .where(SearchQuery.source == "web")
                .order_by(Lead.score_ai.desc().nullslast(), Lead.created_at.desc())
                .limit(5000)
            )
            if team_id is not None:
                target_user = await _resolve_team_view(
                    session, team_id, user_id, member_user_id
                )
                stmt = stmt.where(SearchQuery.team_id == team_id).where(
                    SearchQuery.user_id == target_user
                )
            else:
                stmt = stmt.where(SearchQuery.user_id == user_id).where(
                    SearchQuery.team_id.is_(None)
                )
            rows = (await session.execute(stmt)).all()

        # Hand-rolled CSV — keeps the deps tight (no openpyxl/pandas in
        # the request path) and the columns are intentionally narrow:
        # the things you'd actually paste into another CRM.
        import csv as _csv
        import io as _io

        buf = _io.StringIO()
        writer = _csv.writer(buf, quoting=_csv.QUOTE_MINIMAL)
        writer.writerow(
            [
                "name",
                "niche",
                "region",
                "score",
                "lead_status",
                "rating",
                "reviews_count",
                "phone",
                "website",
                "address",
                "category",
                "notes",
                "last_touched_at",
                "created_at",
            ]
        )
        for lead, niche, region in rows:
            writer.writerow(
                [
                    lead.name or "",
                    niche or "",
                    region or "",
                    "" if lead.score_ai is None else int(round(lead.score_ai)),
                    lead.lead_status or "",
                    "" if lead.rating is None else lead.rating,
                    "" if lead.reviews_count is None else lead.reviews_count,
                    lead.phone or "",
                    lead.website or "",
                    lead.address or "",
                    lead.category or "",
                    (lead.notes or "").replace("\n", " "),
                    lead.last_touched_at.isoformat() if lead.last_touched_at else "",
                    lead.created_at.isoformat() if lead.created_at else "",
                ]
            )
        # UTF-8 BOM so Excel on Windows opens Cyrillic columns cleanly.
        body = "﻿" + buf.getvalue()
        filename = f"convioo-leads-{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
        return Response(
            content=body,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    @app.get(
        "/api/v1/searches/{query_id}/export.xlsx", include_in_schema=False
    )
    async def export_session_xlsx(query_id: uuid.UUID) -> Response:
        """Export one search session as a styled Excel workbook.

        One sheet, header row formatted bold, frozen first row, columns
        auto-fit-ish. The deliberately narrow column set matches the CSV
        export so the user gets the same shape they're used to plus the
        extra polish (cell types, no BOM hack) that Excel users expect.
        """
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        async with session_factory() as session:
            query = await session.get(SearchQuery, query_id)
            if query is None:
                raise HTTPException(status_code=404, detail="search not found")
            rows = list(
                (
                    await session.execute(
                        select(Lead)
                        .where(Lead.query_id == query_id)
                        .order_by(
                            Lead.score_ai.desc().nullslast(),
                            Lead.created_at.desc(),
                        )
                    )
                )
                .scalars()
                .all()
            )

        wb = Workbook()
        ws = wb.active
        ws.title = (query.niche or "leads")[:30]

        headers = [
            "Name",
            "Score",
            "Status",
            "Rating",
            "Reviews",
            "Phone",
            "Website",
            "Address",
            "Category",
            "Notes",
            "Last touched",
            "Created",
        ]
        ws.append(headers)
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(
            start_color="3D5AFE", end_color="3D5AFE", fill_type="solid"
        )
        header_align = Alignment(vertical="center")
        for col_idx, _ in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align

        for lead in rows:
            ws.append(
                [
                    lead.name or "",
                    "" if lead.score_ai is None else int(round(lead.score_ai)),
                    lead.lead_status or "",
                    "" if lead.rating is None else lead.rating,
                    "" if lead.reviews_count is None else lead.reviews_count,
                    lead.phone or "",
                    lead.website or "",
                    lead.address or "",
                    lead.category or "",
                    (lead.notes or "").replace("\n", " "),
                    lead.last_touched_at.isoformat()
                    if lead.last_touched_at
                    else "",
                    lead.created_at.isoformat() if lead.created_at else "",
                ]
            )

        widths = [32, 8, 12, 8, 10, 18, 36, 36, 22, 40, 22, 22]
        for i, width in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = width
        ws.freeze_panes = "A2"
        ws.row_dimensions[1].height = 22

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        slug = (query.niche or "session").replace(" ", "-").lower()[:40]
        date = datetime.now(timezone.utc).strftime("%Y%m%d")
        filename = f"convioo-{slug}-{date}.xlsx"
        return Response(
            content=buffer.getvalue(),
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    @app.patch("/api/v1/leads/{lead_id}", response_model=LeadResponse)
    async def update_lead(
        lead_id: uuid.UUID,
        body: LeadUpdate,
        actor_user_id: int = WEB_DEMO_USER_ID,
    ) -> LeadResponse:
        """Partial update: status, owner, notes. Touches last_touched_at.

        Now also writes an entry to ``lead_activities`` per changed
        field so the timeline + team feed have something to render.
        ``actor_user_id`` (query string) is the user making the change;
        defaults to the demo user when unset.
        """
        if body.lead_status is not None and body.lead_status not in {
            "new",
            "contacted",
            "replied",
            "won",
            "archived",
        }:
            raise HTTPException(
                status_code=400,
                detail="lead_status must be one of new/contacted/replied/won/archived",
            )

        async with session_factory() as session:
            lead = await session.get(Lead, lead_id)
            if lead is None:
                raise HTTPException(status_code=404, detail="lead not found")

            # Capture before/after so we can write meaningful activity
            # rows. The fields list mirrors what LeadUpdate exposes —
            # if a new field gets added there, add it here too.
            activities: list[dict[str, Any]] = []
            now = datetime.now(timezone.utc)

            if body.lead_status is not None and body.lead_status != lead.lead_status:
                activities.append(
                    {
                        "kind": "status",
                        "payload": {
                            "from": lead.lead_status,
                            "to": body.lead_status,
                        },
                    }
                )
                lead.lead_status = body.lead_status
            if "owner_user_id" in body.model_fields_set:
                if body.owner_user_id != lead.owner_user_id:
                    activities.append(
                        {
                            "kind": "assigned",
                            "payload": {
                                "from": lead.owner_user_id,
                                "to": body.owner_user_id,
                            },
                        }
                    )
                lead.owner_user_id = body.owner_user_id
            if body.notes is not None and body.notes != (lead.notes or ""):
                activities.append(
                    {
                        "kind": "notes",
                        "payload": {"len": len(body.notes)},
                    }
                )
                lead.notes = body.notes

            if not activities and (
                body.lead_status is None
                and body.notes is None
                and "owner_user_id" not in body.model_fields_set
            ):
                raise HTTPException(status_code=400, detail="no fields to update")

            lead.last_touched_at = now

            # Pull team_id off the parent search query so the activity
            # row can land in the team feed when the lead is shared.
            search = await session.get(SearchQuery, lead.query_id)
            team_id_for_activity = search.team_id if search else None

            for act in activities:
                session.add(
                    LeadActivity(
                        lead_id=lead.id,
                        user_id=actor_user_id,
                        team_id=team_id_for_activity,
                        kind=act["kind"],
                        payload=act["payload"],
                    )
                )
            await session.commit()
            await session.refresh(lead)
            return LeadResponse.model_validate(lead)

    # ── /api/v1/leads/{id}/custom-fields ────────────────────────────────

    @app.get(
        "/api/v1/leads/{lead_id}/custom-fields",
        response_model=LeadCustomFieldsResponse,
    )
    async def list_lead_custom_fields(
        lead_id: uuid.UUID,
        user_id: int,
    ) -> LeadCustomFieldsResponse:
        async with session_factory() as session:
            stmt = (
                select(LeadCustomField)
                .where(LeadCustomField.lead_id == lead_id)
                .where(LeadCustomField.user_id == user_id)
                .order_by(LeadCustomField.key)
            )
            rows = (await session.execute(stmt)).scalars().all()
            items = [
                LeadCustomFieldSchema.model_validate(r) for r in rows
            ]
        return LeadCustomFieldsResponse(items=items)

    @app.put(
        "/api/v1/leads/{lead_id}/custom-fields",
        response_model=LeadCustomFieldSchema,
    )
    async def upsert_lead_custom_field(
        lead_id: uuid.UUID,
        body: LeadCustomFieldUpsert,
        user_id: int,
    ) -> LeadCustomFieldSchema:
        """Create or update one (key, value) pair on this lead.

        Schemaless — the user picks any key from the UI. ``value`` may
        be NULL, which acts as a soft-delete on the row (we still keep
        the row so the timeline can reference the historical key).
        """
        key = body.key.strip()
        if not key:
            raise HTTPException(status_code=400, detail="key is required")
        value = body.value if body.value is None else body.value.strip()
        async with session_factory() as session:
            existing = (
                await session.execute(
                    select(LeadCustomField)
                    .where(LeadCustomField.lead_id == lead_id)
                    .where(LeadCustomField.user_id == user_id)
                    .where(LeadCustomField.key == key)
                    .limit(1)
                )
            ).scalar_one_or_none()
            now = datetime.now(timezone.utc)
            search = (
                await session.execute(
                    select(SearchQuery)
                    .join(Lead, Lead.query_id == SearchQuery.id)
                    .where(Lead.id == lead_id)
                    .limit(1)
                )
            ).scalar_one_or_none()
            team_id_for_activity = search.team_id if search else None
            if existing is None:
                existing = LeadCustomField(
                    lead_id=lead_id,
                    user_id=user_id,
                    key=key,
                    value=value,
                )
                session.add(existing)
            else:
                existing.value = value
                existing.updated_at = now
            session.add(
                LeadActivity(
                    lead_id=lead_id,
                    user_id=user_id,
                    team_id=team_id_for_activity,
                    kind="custom_field",
                    payload={"key": key, "value": value},
                )
            )
            await session.commit()
            await session.refresh(existing)
            return LeadCustomFieldSchema.model_validate(existing)

    @app.delete("/api/v1/leads/{lead_id}/custom-fields/{key}")
    async def delete_lead_custom_field(
        lead_id: uuid.UUID,
        key: str,
        user_id: int,
    ) -> dict[str, bool]:
        async with session_factory() as session:
            row = (
                await session.execute(
                    select(LeadCustomField)
                    .where(LeadCustomField.lead_id == lead_id)
                    .where(LeadCustomField.user_id == user_id)
                    .where(LeadCustomField.key == key)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if row is None:
                return {"deleted": False}
            await session.delete(row)
            await session.commit()
        return {"deleted": True}

    # ── /api/v1/leads/{id}/activity ─────────────────────────────────────

    @app.get(
        "/api/v1/leads/{lead_id}/activity",
        response_model=LeadActivityListResponse,
    )
    async def list_lead_activity(
        lead_id: uuid.UUID,
        limit: int = 50,
    ) -> LeadActivityListResponse:
        limit = max(1, min(limit, 200))
        async with session_factory() as session:
            stmt = (
                select(LeadActivity)
                .where(LeadActivity.lead_id == lead_id)
                .order_by(LeadActivity.created_at.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            items = [LeadActivitySchema.model_validate(r) for r in rows]
        return LeadActivityListResponse(items=items)

    # ── /api/v1/leads/{id}/tasks ────────────────────────────────────────

    @app.get(
        "/api/v1/leads/{lead_id}/tasks",
        response_model=LeadTaskListResponse,
    )
    async def list_lead_tasks(
        lead_id: uuid.UUID,
        user_id: int,
    ) -> LeadTaskListResponse:
        async with session_factory() as session:
            stmt = (
                select(LeadTask)
                .where(LeadTask.lead_id == lead_id)
                .where(LeadTask.user_id == user_id)
                .order_by(
                    LeadTask.done_at.is_(None).desc(),
                    LeadTask.due_at.asc().nullslast(),
                    LeadTask.created_at.desc(),
                )
            )
            rows = (await session.execute(stmt)).scalars().all()
            items = [LeadTaskSchema.model_validate(r) for r in rows]
        return LeadTaskListResponse(items=items)

    @app.post(
        "/api/v1/leads/{lead_id}/tasks",
        response_model=LeadTaskSchema,
    )
    async def create_lead_task(
        lead_id: uuid.UUID,
        body: LeadTaskCreate,
        user_id: int,
    ) -> LeadTaskSchema:
        async with session_factory() as session:
            row = LeadTask(
                lead_id=lead_id,
                user_id=user_id,
                content=body.content.strip(),
                due_at=body.due_at,
            )
            session.add(row)
            search = (
                await session.execute(
                    select(SearchQuery)
                    .join(Lead, Lead.query_id == SearchQuery.id)
                    .where(Lead.id == lead_id)
                    .limit(1)
                )
            ).scalar_one_or_none()
            session.add(
                LeadActivity(
                    lead_id=lead_id,
                    user_id=user_id,
                    team_id=search.team_id if search else None,
                    kind="task",
                    payload={
                        "content": body.content.strip()[:200],
                        "due_at": body.due_at.isoformat() if body.due_at else None,
                    },
                )
            )
            await session.commit()
            await session.refresh(row)
            return LeadTaskSchema.model_validate(row)

    @app.patch(
        "/api/v1/tasks/{task_id}",
        response_model=LeadTaskSchema,
    )
    async def update_lead_task(
        task_id: uuid.UUID,
        body: LeadTaskUpdate,
        user_id: int,
    ) -> LeadTaskSchema:
        async with session_factory() as session:
            row = await session.get(LeadTask, task_id)
            if row is None or row.user_id != user_id:
                raise HTTPException(status_code=404, detail="task not found")
            data = body.model_dump(exclude_unset=True)
            if "content" in data and data["content"]:
                row.content = data["content"].strip()
            if "due_at" in data:
                row.due_at = data["due_at"]
            if "done" in data and data["done"] is not None:
                row.done_at = (
                    datetime.now(timezone.utc) if data["done"] else None
                )
            await session.commit()
            await session.refresh(row)
            return LeadTaskSchema.model_validate(row)

    @app.delete("/api/v1/tasks/{task_id}")
    async def delete_lead_task(
        task_id: uuid.UUID,
        user_id: int,
    ) -> dict[str, bool]:
        async with session_factory() as session:
            row = await session.get(LeadTask, task_id)
            if row is None or row.user_id != user_id:
                return {"deleted": False}
            await session.delete(row)
            await session.commit()
        return {"deleted": True}

    @app.get(
        "/api/v1/users/{user_id}/tasks",
        response_model=LeadTaskListResponse,
    )
    async def list_my_tasks(
        user_id: int,
        open_only: bool = True,
        limit: int = 100,
    ) -> LeadTaskListResponse:
        """Today's-tasks widget feed: open tasks across every lead."""
        limit = max(1, min(limit, 500))
        async with session_factory() as session:
            stmt = select(LeadTask).where(LeadTask.user_id == user_id)
            if open_only:
                stmt = stmt.where(LeadTask.done_at.is_(None))
            stmt = stmt.order_by(
                LeadTask.due_at.asc().nullslast(),
                LeadTask.created_at.desc(),
            ).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            items = [LeadTaskSchema.model_validate(r) for r in rows]
        return LeadTaskListResponse(items=items)

    @app.post(
        "/api/v1/leads/{lead_id}/draft-email",
        response_model=LeadEmailDraftResponse,
    )
    async def draft_lead_email(
        lead_id: uuid.UUID, body: LeadEmailDraftRequest
    ) -> LeadEmailDraftResponse:
        """Generate a personalised cold-email draft for one lead.

        The frontend opens the draft inline in the lead modal — the
        salesperson can copy the subject + body (or regenerate with a
        different tone) and paste into Gmail. Real send-via-Gmail
        ships once the OAuth connector lands.
        """
        async with session_factory() as session:
            lead = await session.get(Lead, lead_id)
            if lead is None:
                raise HTTPException(status_code=404, detail="lead not found")
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

        lead_payload = {
            "name": lead.name,
            "category": lead.category,
            "address": lead.address,
            "website": lead.website,
            "rating": lead.rating,
            "reviews_count": lead.reviews_count,
            "score_ai": lead.score_ai,
            "summary": lead.summary,
            "advice": lead.advice,
            "strengths": list(lead.strengths) if lead.strengths else None,
            "weaknesses": list(lead.weaknesses) if lead.weaknesses else None,
            "red_flags": list(lead.red_flags) if lead.red_flags else None,
        }

        analyzer = AIAnalyzer()

        # Optional: deep research pass — fresh website fetch + Claude
        # extraction of notable facts. Threaded into ``extra_context``
        # so the existing email prompt naturally cites the lead's own
        # site instead of leaning on cached enrichment.
        notable_facts: list[str] = []
        recent_signal: str | None = None
        merged_extra = body.extra_context
        if body.deep_research:
            research = await analyzer.research_lead_for_outreach(
                lead_payload,
                user_profile=user_profile or None,
            )
            notable_facts = list(research.get("notable_facts") or [])
            recent_signal = research.get("recent_signal")
            opener = research.get("suggested_opener")
            research_block_parts: list[str] = []
            if notable_facts:
                research_block_parts.append(
                    "Свежие факты с сайта (можно цитировать в opener):"
                )
                for fact in notable_facts:
                    research_block_parts.append(f"- {fact}")
            if recent_signal:
                research_block_parts.append(
                    f"Recent signal (что-то новое у них): {recent_signal}"
                )
            if opener:
                research_block_parts.append(
                    f"Подсказанный opener: {opener}"
                )
            if research_block_parts:
                research_block = "\n".join(research_block_parts)
                merged_extra = (
                    f"{body.extra_context}\n\n{research_block}"
                    if body.extra_context
                    else research_block
                )

        result = await analyzer.generate_cold_email(
            lead_payload,
            user_profile=user_profile or None,
            tone=body.tone,
            extra_context=merged_extra,
        )
        return LeadEmailDraftResponse(
            subject=result["subject"],
            body=result["body"],
            tone=result["tone"],
            notable_facts=notable_facts,
            recent_signal=recent_signal,
        )

    @app.patch(
        "/api/v1/leads/bulk", response_model=LeadBulkUpdateResponse
    )
    async def bulk_update_leads(
        body: LeadBulkUpdateRequest,
    ) -> LeadBulkUpdateResponse:
        """Apply ``lead_status`` and/or the caller's mark to many leads
        in one round-trip. The CRM bulk-toolbar uses this so the user
        can sweep dozens of rows in one click.
        """
        if not body.lead_status and not body.set_mark_color:
            raise HTTPException(
                status_code=400, detail="nothing to update"
            )
        if body.lead_status and body.lead_status not in {
            "new",
            "contacted",
            "replied",
            "won",
            "archived",
        }:
            raise HTTPException(
                status_code=400,
                detail="lead_status must be new/contacted/replied/won/archived",
            )

        async with session_factory() as session:
            updated = 0
            if body.lead_status:
                result = await session.execute(
                    update(Lead)
                    .where(Lead.id.in_(body.lead_ids))
                    .values(
                        lead_status=body.lead_status,
                        last_touched_at=datetime.now(timezone.utc),
                    )
                )
                updated = max(updated, result.rowcount or 0)

            if body.set_mark_color:
                color = (body.mark_color or "").strip() or None
                if color is None:
                    await session.execute(
                        sa.delete(LeadMark)
                        .where(LeadMark.user_id == body.user_id)
                        .where(LeadMark.lead_id.in_(body.lead_ids))
                    )
                else:
                    # Per-row upsert. Postgres ON CONFLICT keeps it cheap;
                    # SQLite (test harness) iterates Python-side.
                    from sqlalchemy.dialects.postgresql import (
                        insert as pg_insert,
                    )

                    rows = [
                        {
                            "user_id": body.user_id,
                            "lead_id": lid,
                            "color": color,
                            "updated_at": datetime.now(timezone.utc),
                        }
                        for lid in body.lead_ids
                    ]
                    if session.bind.dialect.name == "postgresql":
                        stmt = pg_insert(LeadMark).values(rows)
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["user_id", "lead_id"],
                            set_={
                                "color": color,
                                "updated_at": datetime.now(timezone.utc),
                            },
                        )
                        await session.execute(stmt)
                    else:
                        for r in rows:
                            existing = (
                                await session.execute(
                                    select(LeadMark)
                                    .where(LeadMark.user_id == r["user_id"])
                                    .where(LeadMark.lead_id == r["lead_id"])
                                )
                            ).scalar_one_or_none()
                            if existing:
                                existing.color = color
                                existing.updated_at = r["updated_at"]
                            else:
                                session.add(LeadMark(**r))

            await session.commit()

            # Final count of touched rows: how many of the requested
            # lead_ids actually exist in the DB (cheap SELECT).
            result = await session.execute(
                select(func.count(Lead.id)).where(Lead.id.in_(body.lead_ids))
            )
            return LeadBulkUpdateResponse(updated=int(result.scalar() or 0))

    @app.put("/api/v1/leads/{lead_id}/mark", response_model=LeadResponse)
    async def set_lead_mark(
        lead_id: uuid.UUID, body: LeadMarkRequest
    ) -> LeadResponse:
        """Set or clear the caller's private colour mark on a lead.

        Pass ``color: null`` to remove. The mark is only ever visible
        to ``user_id``; teammates see their own marks (or none).
        """
        async with session_factory() as session:
            lead = await session.get(Lead, lead_id)
            if lead is None:
                raise HTTPException(status_code=404, detail="lead not found")

            existing = (
                await session.execute(
                    select(LeadMark)
                    .where(LeadMark.user_id == body.user_id)
                    .where(LeadMark.lead_id == lead_id)
                    .limit(1)
                )
            ).scalar_one_or_none()

            color = (body.color or "").strip() or None
            if color is None:
                if existing is not None:
                    await session.delete(existing)
                final_color: str | None = None
            elif existing is None:
                session.add(
                    LeadMark(user_id=body.user_id, lead_id=lead_id, color=color)
                )
                final_color = color
            else:
                existing.color = color
                existing.updated_at = datetime.now(timezone.utc)
                final_color = color

            await session.commit()
            await session.refresh(lead)
            return _to_lead_response(lead, final_color)

    @app.get(
        "/api/v1/teams/{team_id}/members-summary",
        response_model=list[TeamMemberSummary],
    )
    async def team_members_summary(
        team_id: uuid.UUID, user_id: int
    ) -> list[TeamMemberSummary]:
        """Owner-only roll-up: per-member sessions/leads/hot counts.

        Powers the "see each teammate's CRM" panel — the owner picks a
        row and the workspace switches to viewing that member via
        ``member_user_id`` on the list endpoints.
        """
        async with session_factory() as session:
            caller = await _membership(session, team_id, user_id)
            if caller is None or caller.role != "owner":
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

            results: list[TeamMemberSummary] = []
            for membership, member in rows:
                sessions_total = int(
                    (
                        await session.execute(
                            select(func.count(SearchQuery.id))
                            .where(SearchQuery.team_id == team_id)
                            .where(SearchQuery.user_id == member.id)
                        )
                    ).scalar()
                    or 0
                )
                lead_scores = [
                    s
                    for s, in (
                        await session.execute(
                            select(Lead.score_ai)
                            .join(SearchQuery, SearchQuery.id == Lead.query_id)
                            .where(SearchQuery.team_id == team_id)
                            .where(SearchQuery.user_id == member.id)
                        )
                    ).all()
                ]
                hot = sum(1 for s in lead_scores if s is not None and s >= 75)
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
                        sessions_total=sessions_total,
                        leads_total=len(lead_scores),
                        hot_total=hot,
                    )
                )
            return results

    @app.get("/api/v1/stats", response_model=DashboardStats)
    async def dashboard_stats(
        user_id: int = WEB_DEMO_USER_ID,
        team_id: uuid.UUID | None = None,
        member_user_id: int | None = None,
    ) -> DashboardStats:
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


def _to_lead_response(lead: Lead, mark_color: str | None) -> LeadResponse:
    payload = LeadResponse.model_validate(lead)
    payload.mark_color = mark_color
    return payload


def _temp(score: float | None) -> str:
    """Bucket a 0–100 AI score into prototype temperature tiers."""
    if score is None:
        return "cold"
    if score >= 75:
        return "hot"
    if score >= 50:
        return "warm"
    return "cold"


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


def _request_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    if request.client and request.client.host:
        return request.client.host[:64]
    return None


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
                ip=_request_ip(request),
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

    if caller.role != "owner":
        raise HTTPException(
            status_code=403, detail="only the team owner can view another member"
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


async def _membership(
    session, team_id: uuid.UUID, user_id: int
) -> TeamMembership | None:
    result = await session.execute(
        select(TeamMembership)
        .where(TeamMembership.team_id == team_id)
        .where(TeamMembership.user_id == user_id)
        .limit(1)
    )
    return result.scalar_one_or_none()


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
        onboarded=_is_onboarded(user),
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


def _detect_confirmation(text: str) -> str | None:
    """Return ``"confirm"`` / ``"refuse"`` / ``None`` for a reply.

    Only fires when the user's whole message is a one-word
    confirmation; anything more substantial falls through to the LLM
    so Henry handles it properly.
    """
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
                    asyncio.create_task(
                        _run_web_search_inline(
                            new_query.id, user_profile_for_run
                        ),
                        name=f"leadgen-henry-search-{new_query.id}",
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
                        summary=(
                            f"Запустить поиск: {niche} в {region}"
                        ),
                        payload=payload,
                    )
                )

    return out
