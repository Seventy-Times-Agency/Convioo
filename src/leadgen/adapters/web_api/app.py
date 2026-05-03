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
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest
from sqlalchemy import func, select, update
from sqlalchemy import text as sa_text
from sqlalchemy.exc import IntegrityError

from leadgen.adapters.web_api.auth import (
    clear_failed_logins,
    clear_session_cookie,
    create_session,
    current_session_id,
    device_fingerprint,
    enforce_rate_limit,
    get_current_user,
    hash_token,
    is_known_device,
    is_locked,
    record_failed_login,
    request_ip,
    request_user_agent,
    revoke_all_sessions,
    revoke_session,
    set_session_cookie,
)
from leadgen.adapters.web_api.schemas import (
    WEB_DEMO_USER_ID,
    AccountDeleteRequest,
    AccountDeleteResponse,
    AffiliateCodeCreateRequest,
    AffiliateCodeSchema,
    AffiliateCodeUpdate,
    AffiliateOverview,
    ApiKeyCreatedResponse,
    ApiKeyCreateRequest,
    ApiKeyListResponse,
    ApiKeySchema,
    AssistantMemoryDeleteResponse,
    AssistantMemoryItem,
    AssistantMemoryListResponse,
    AssistantRequest,
    AssistantResponse,
    AuditLogEntry,
    AuditLogListResponse,
    AuthUser,
    BillingSubscriptionResponse,
    BulkDraftEmailItem,
    BulkDraftEmailRequest,
    BulkDraftEmailResponse,
    ChangeEmailRequest,
    ChangePasswordRequest,
    CheckoutRequest,
    CheckoutResponse,
    CityEntryResponse,
    CityListResponse,
    ConsultRequest,
    ConsultResponse,
    CsvImportRequest,
    CsvImportResponse,
    DashboardStats,
    DecisionMaker,
    DecisionMakersResponse,
    ForgotEmailRequest,
    ForgotPasswordRequest,
    GmailAuthorizeResponse,
    GmailIntegrationStatus,
    GmailSendRequest,
    GmailSendResponse,
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
    LeadSegmentCreate,
    LeadSegmentListResponse,
    LeadSegmentSchema,
    LeadSegmentUpdate,
    LeadStatusCreate,
    LeadStatusListResponse,
    LeadStatusReorderRequest,
    LeadStatusSchema,
    LeadStatusUpdate,
    LeadTagCreate,
    LeadTagListResponse,
    LeadTagsAssignRequest,
    LeadTagSchema,
    LeadTagUpdate,
    LeadTaskCreate,
    LeadTaskListResponse,
    LeadTaskUpdate,
    LeadUpdate,
    LoginRequest,
    LogoutAllResponse,
    MembershipUpdateRequest,
    NicheSuggestionsResponse,
    NicheTaxonomyEntry,
    NicheTaxonomyResponse,
    NotionConnectRequest,
    NotionExportItem,
    NotionExportRequest,
    NotionExportResponse,
    NotionIntegrationStatus,
    OutreachTemplateCreate,
    OutreachTemplateListResponse,
    OutreachTemplateUpdate,
    PendingAction,
    PortalRequest,
    PortalResponse,
    PriorTeamSearch,
    RecoveryEmailUpdate,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SearchAxesResponse,
    SearchAxisOption,
    SearchCreate,
    SearchCreateResponse,
    SearchPreflightResponse,
    SearchSummary,
    SessionInfo,
    SessionListResponse,
    TeamCreateRequest,
    TeamDetailResponse,
    TeamMemberResponse,
    TeamMemberSummary,
    TeamSummary,
    TeamUpdateRequest,
    UserProfile,
    UserProfileUpdate,
    VerifyEmailRequest,
    WebhookCreatedResponse,
    WebhookCreateRequest,
    WebhookListResponse,
    WebhookSchema,
    WebhookUpdateRequest,
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
    mask_email,
    render_account_locked_email,
    render_email_changed_alert,
    render_email_recovery_email,
    render_new_device_login_email,
    render_password_changed_email,
    render_password_reset_email,
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
from leadgen.core.services.webhooks import (
    ALLOWED_EVENTS as WEBHOOK_ALLOWED_EVENTS,
)
from leadgen.core.services.webhooks import (
    emit_event_sync as emit_webhook_event_sync,
)
from leadgen.core.services.webhooks import (
    generate_secret as generate_webhook_secret,
)
from leadgen.core.services.webhooks import (
    serialize_lead as serialize_lead_for_webhook,
)
from leadgen.db.models import (
    AffiliateCode,
    AssistantMemory,
    EmailVerificationToken,
    Lead,
    LeadActivity,
    LeadCustomField,
    LeadMark,
    LeadSegment,
    LeadStatus,
    LeadTag,
    LeadTagAssignment,
    LeadTask,
    OAuthCredential,
    OutreachTemplate,
    Referral,
    SearchQuery,
    StripeEvent,
    Team,
    TeamInvite,
    TeamMembership,
    TeamSeenLead,
    User,
    UserApiKey,
    UserAuditLog,
    UserIntegrationCredential,
    UserSeenLead,
    UserSession,
    Webhook,
)
from leadgen.db.session import _get_engine, session_factory
from leadgen.pipeline.search import run_search_with_sinks
from leadgen.queue import enqueue_search, is_queue_enabled
from leadgen.utils.rate_limit import (
    assistant_team_limiter,
    assistant_user_limiter,
    forgot_email_limiter,
    forgot_password_limiter,
    login_limiter,
    register_limiter,
    resend_verification_limiter,
    reset_password_limiter,
    search_ip_limiter,
    search_team_limiter,
    search_user_limiter,
)

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


def _seed_default_lead_statuses(session, team_id) -> None:
    """Insert the five default statuses for a freshly-created team.

    Caller commits. Safe to call against a team that already has
    rows because the unique ``(team_id, key)`` constraint plus the
    pre-check inside the per-row insert path silently no-ops on
    duplicates — but the standard call site (just-created team)
    will never collide.
    """
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
    async def register(
        body: RegisterRequest, request: Request, response: Response
    ) -> AuthUser:
        """Sign up with email + password + first/last name (+ optional age).

        Minimal registration: name + email + password are required, an
        age range is optional. The user lands directly on /app — the
        rest of the profile (what they sell, niches, region) is filled
        from the workspace via a soft nudge banner or with Henry. The
        ``onboarded_at`` timestamp is stamped here so the gate check
        treats the account as ready immediately. A session cookie is
        issued so the SPA stays signed-in without juggling tokens.
        """
        ip = request_ip(request)
        enforce_rate_limit(register_limiter, f"ip:{ip or '?'}", retry_hint=3600)

        # Invite-code gate. When REGISTRATION_PASSWORD is set on the
        # server, the SPA must echo the same value — otherwise public
        # registration is closed.
        required_code = (get_settings().registration_password or "").strip()
        if required_code:
            supplied = (body.registration_password or "").strip()
            if supplied != required_code:
                raise HTTPException(
                    status_code=403,
                    detail="registration is currently closed; an invite code is required",
                )

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

            trial_days = max(0, get_settings().stripe_trial_days)
            trial_ends_at = (
                now + timedelta(days=trial_days) if trial_days else None
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
                    trial_ends_at=trial_ends_at,
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
            token, _sess = await create_session(
                session, user_id=user.id, request=request
            )

            # Attribution: if a referral_code rode in (set on the
            # registration form by the public /r/{code} landing page
            # via cookie), record the signup against the matching
            # active affiliate code. Unknown / inactive codes are
            # silently dropped — never blocks registration.
            ref_code = (body.referral_code or "").strip().lower()
            if ref_code:
                affiliate = (
                    await session.execute(
                        select(AffiliateCode)
                        .where(AffiliateCode.code == ref_code)
                        .where(AffiliateCode.active.is_(True))
                        .where(AffiliateCode.owner_user_id != user.id)
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if affiliate is not None:
                    session.add(
                        Referral(
                            code=affiliate.code,
                            referred_user_id=user.id,
                        )
                    )
            await session.commit()

        set_session_cookie(response, token, request=request)
        return AuthUser(
            user_id=user.id,
            first_name=first,
            last_name=last,
            email=email,
            email_verified=False,
            onboarded=True,
        )

    @app.post("/api/v1/auth/login", response_model=AuthUser)
    async def login(
        body: LoginRequest, request: Request, response: Response
    ) -> AuthUser:
        """Email + password login. Issues an httpOnly session cookie.

        Returns 401 with the same generic error for missing user /
        wrong password / locked account so the endpoint can't be used
        to enumerate accounts. After ``LOCKOUT_THRESHOLD`` failed
        attempts the account is locked for ``LOCKOUT_DURATION`` and a
        notification email is sent so the real owner knows someone is
        trying to break in.
        """
        email = body.email.strip().lower()
        ip = request_ip(request)
        enforce_rate_limit(
            login_limiter, f"ip:{ip or '?'}", f"email:{email}", retry_hint=60
        )
        invalid = HTTPException(
            status_code=401, detail="invalid email or password"
        )
        async with session_factory() as session:
            user = (
                await session.execute(
                    select(User).where(func.lower(User.email) == email).limit(1)
                )
            ).scalar_one_or_none()
            if user is None or not user.password_hash:
                # No row, or the row was created via Telegram and never
                # set a password — same generic 401 either way.
                raise invalid

            if is_locked(user):
                # Don't reveal lockout state to the attacker; just keep
                # rejecting like any other bad-password attempt.
                await _record_audit(
                    session,
                    user_id=user.id,
                    action="auth.login_locked",
                    request=request,
                )
                await session.commit()
                raise invalid

            if not _verify_password(body.password, user.password_hash):
                just_locked = record_failed_login(user)
                await _record_audit(
                    session,
                    user_id=user.id,
                    action="auth.login_fail",
                    request=request,
                    payload={"attempts": user.failed_login_attempts},
                )
                await session.commit()
                if just_locked and user.email:
                    unlock_iso = user.locked_until.isoformat() if user.locked_until else ""
                    html, text = render_account_locked_email(
                        name=user.first_name or user.display_name or "",
                        unlock_iso=unlock_iso,
                    )
                    await send_email(
                        to=user.email,
                        subject="Аккаунт временно заблокирован — Convioo",
                        html=html,
                        text=text,
                    )
                raise invalid

            # Successful login: reset counters, mint session, alert if new device.
            clear_failed_logins(user)
            ua = request_user_agent(request)
            fingerprint = device_fingerprint(ip, ua)
            new_device = not await is_known_device(
                session, user_id=user.id, fingerprint=fingerprint
            )
            token, _sess = await create_session(
                session, user_id=user.id, request=request
            )
            await _record_audit(
                session,
                user_id=user.id,
                action="auth.login",
                request=request,
                payload={"new_device": new_device} if new_device else None,
            )
            await session.commit()

            if new_device and user.email:
                html, text = render_new_device_login_email(
                    name=user.first_name or user.display_name or "",
                    ip=ip,
                    user_agent=ua,
                    when_iso=datetime.now(timezone.utc).isoformat(),
                )
                await send_email(
                    to=user.email,
                    subject="Вход с нового устройства — Convioo",
                    html=html,
                    text=text,
                )

            set_session_cookie(response, token, request=request)
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
            old_email: str | None = None
            email_actually_changed = False
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
                old_email = user.email
                user.email = token_row.pending_email
                user.email_verified_at = now
                email_actually_changed = True
                # An email change effectively re-authenticates the
                # account: revoke every session (including this click's
                # sender, if any) so anyone signed in on the old address
                # has to log in again with the new one.
                await revoke_all_sessions(session, user_id=user.id)
            elif user.email_verified_at is None:
                user.email_verified_at = now
            await session.commit()

            if email_actually_changed and old_email:
                # Security alert to the OLD inbox — last chance for the
                # real owner to notice an unauthorised swap.
                html, text = render_email_changed_alert(
                    name=user.first_name or user.display_name or "",
                    new_email_masked=mask_email(user.email),
                    when_iso=now.isoformat(),
                )
                await send_email(
                    to=old_email,
                    subject="Email вашего аккаунта изменён — Convioo",
                    html=html,
                    text=text,
                )

            return AuthUser(
                user_id=user.id,
                first_name=user.first_name or "",
                last_name=user.last_name or "",
                email=user.email,
                email_verified=True,
                onboarded=_is_onboarded(user),
            )

    @app.post("/api/v1/auth/resend-verification")
    async def resend_verification(
        body: ResendVerificationRequest, request: Request
    ) -> dict[str, bool]:
        """Resend the verification email for a not-yet-verified account.

        Always returns ``{"sent": true}`` — even if the email isn't on
        file — so this endpoint can't be used to enumerate accounts.
        """
        email = body.email.strip().lower()
        enforce_rate_limit(
            resend_verification_limiter,
            f"email:{email}",
            f"ip:{request_ip(request) or '?'}",
            retry_hint=3600,
        )
        async with session_factory() as session:
            user = (
                await session.execute(
                    select(User).where(func.lower(User.email) == email).limit(1)
                )
            ).scalar_one_or_none()
            if user is not None and user.email_verified_at is None:
                await _issue_and_send_verification(session, user)
        return {"sent": True}

    @app.post("/api/v1/auth/forgot-password")
    async def forgot_password(
        body: ForgotPasswordRequest, request: Request
    ) -> dict[str, bool]:
        """Mint a 1-hour password-reset link and email it.

        Always returns ``{"sent": true}`` so the response can't be used
        to enumerate accounts. If the email is registered we invalidate
        any earlier outstanding reset tokens (so only the freshest link
        works) and issue a new one.
        """
        email = body.email.strip().lower()
        enforce_rate_limit(
            forgot_password_limiter,
            f"email:{email}",
            f"ip:{request_ip(request) or '?'}",
            retry_hint=3600,
        )
        async with session_factory() as session:
            user = (
                await session.execute(
                    select(User).where(func.lower(User.email) == email).limit(1)
                )
            ).scalar_one_or_none()
            if user is not None and user.email:
                await session.execute(
                    update(EmailVerificationToken)
                    .where(EmailVerificationToken.user_id == user.id)
                    .where(EmailVerificationToken.kind == "password_reset")
                    .where(EmailVerificationToken.used_at.is_(None))
                    .values(used_at=datetime.now(timezone.utc))
                )
                token = secrets.token_urlsafe(32)
                expires = datetime.now(timezone.utc) + timedelta(hours=1)
                session.add(
                    EmailVerificationToken(
                        user_id=user.id,
                        kind="password_reset",
                        token=token,
                        expires_at=expires,
                    )
                )
                await _record_audit(
                    session,
                    user_id=user.id,
                    action="auth.forgot_password_requested",
                    request=request,
                )
                await session.commit()
                base = get_settings().public_app_url.rstrip("/")
                reset_url = f"{base}/reset-password/{token}"
                html, text = render_password_reset_email(
                    name=user.first_name or user.display_name or "",
                    reset_url=reset_url,
                )
                await send_email(
                    to=user.email,
                    subject="Сброс пароля — Convioo",
                    html=html,
                    text=text,
                )
        return {"sent": True}

    @app.post("/api/v1/auth/reset-password", response_model=AuthUser)
    async def reset_password(
        body: ResetPasswordRequest, request: Request, response: Response
    ) -> AuthUser:
        """Consume a password-reset token and set the new password.

        Side effects on success:
          - mark the token spent
          - revoke EVERY existing session (so a stolen cookie elsewhere
            stops working at the moment the user takes back control)
          - email a "password changed" security alert
          - issue a fresh session cookie so the user is signed in on
            the device they just reset from
        """
        if len(body.new_password) < 8:
            raise HTTPException(
                status_code=400,
                detail="new password must be at least 8 characters",
            )
        enforce_rate_limit(
            reset_password_limiter,
            f"ip:{request_ip(request) or '?'}",
            retry_hint=3600,
        )

        async with session_factory() as session:
            row = (
                await session.execute(
                    select(EmailVerificationToken, User)
                    .join(User, User.id == EmailVerificationToken.user_id)
                    .where(EmailVerificationToken.token == body.token)
                    .where(EmailVerificationToken.kind == "password_reset")
                    .limit(1)
                )
            ).first()
            if row is None:
                raise HTTPException(status_code=404, detail="token not found")
            token_row, user = row
            now = datetime.now(timezone.utc)
            if token_row.used_at is not None:
                raise HTTPException(status_code=410, detail="token already used")
            expires = token_row.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if now >= expires:
                raise HTTPException(status_code=410, detail="token expired")

            token_row.used_at = now
            user.password_hash = _hash_password(body.new_password)
            clear_failed_logins(user)
            await revoke_all_sessions(session, user_id=user.id)
            new_token, _sess = await create_session(
                session, user_id=user.id, request=request
            )
            await _record_audit(
                session,
                user_id=user.id,
                action="auth.password_reset",
                request=request,
            )
            await session.commit()

        if user.email:
            html, text = render_password_changed_email(
                name=user.first_name or user.display_name or "",
                ip=request_ip(request),
                user_agent=request_user_agent(request),
                when_iso=now.isoformat(),
            )
            await send_email(
                to=user.email,
                subject="Пароль изменён — Convioo",
                html=html,
                text=text,
            )

        set_session_cookie(response, new_token, request=request)
        return AuthUser(
            user_id=user.id,
            first_name=user.first_name or "",
            last_name=user.last_name or "",
            email=user.email,
            email_verified=user.email_verified_at is not None,
            onboarded=_is_onboarded(user),
        )

    @app.post("/api/v1/auth/forgot-email")
    async def forgot_email(
        body: ForgotEmailRequest, request: Request
    ) -> dict[str, bool]:
        """Help a user remember which email their account is on.

        Looks up by ``recovery_email``. If a matching account is found
        we send a reminder to the recovery address that includes a
        masked form of the primary email plus a link to swap it for
        the recovery one (1h token, ``email_recovery`` kind). Always
        returns ``{"sent": true}`` so attackers can't probe addresses.
        """
        recovery = body.recovery_email.strip().lower()
        enforce_rate_limit(
            forgot_email_limiter,
            f"email:{recovery}",
            f"ip:{request_ip(request) or '?'}",
            retry_hint=3600,
        )
        async with session_factory() as session:
            user = (
                await session.execute(
                    select(User)
                    .where(func.lower(User.recovery_email) == recovery)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if user is not None and user.email and user.recovery_email:
                await session.execute(
                    update(EmailVerificationToken)
                    .where(EmailVerificationToken.user_id == user.id)
                    .where(EmailVerificationToken.kind == "email_recovery")
                    .where(EmailVerificationToken.used_at.is_(None))
                    .values(used_at=datetime.now(timezone.utc))
                )
                token = secrets.token_urlsafe(32)
                expires = datetime.now(timezone.utc) + timedelta(hours=1)
                # Reuse the change_email plumbing: a token whose
                # pending_email is the recovery address. Clicking it
                # will swap user.email → recovery_email through the
                # existing /verify-email handler. We label kind
                # ``email_recovery`` so analytics can tell the flows
                # apart in the audit log.
                session.add(
                    EmailVerificationToken(
                        user_id=user.id,
                        kind="email_recovery",
                        token=token,
                        pending_email=user.recovery_email,
                        expires_at=expires,
                    )
                )
                await _record_audit(
                    session,
                    user_id=user.id,
                    action="auth.forgot_email_requested",
                    request=request,
                )
                await session.commit()
                base = get_settings().public_app_url.rstrip("/")
                change_url = f"{base}/verify-email/{token}"
                html, text = render_email_recovery_email(
                    name=user.first_name or user.display_name or "",
                    account_email_masked=mask_email(user.email),
                    change_url=change_url,
                )
                await send_email(
                    to=user.recovery_email,
                    subject="Восстановление доступа — Convioo",
                    html=html,
                    text=text,
                )
        return {"sent": True}

    @app.post("/api/v1/auth/logout")
    async def logout(
        request: Request,
        response: Response,
        current_user: User = Depends(get_current_user),
    ) -> dict[str, bool]:
        sid = current_session_id(request)
        async with session_factory() as session:
            if sid is not None:
                await revoke_session(session, sid)
                await _record_audit(
                    session,
                    user_id=current_user.id,
                    action="auth.logout",
                    request=request,
                )
                await session.commit()
        clear_session_cookie(response, request=request)
        return {"ok": True}

    @app.post("/api/v1/auth/logout-all", response_model=LogoutAllResponse)
    async def logout_all(
        request: Request,
        current_user: User = Depends(get_current_user),
    ) -> LogoutAllResponse:
        """Revoke every session except the one making the call."""
        sid = current_session_id(request)
        async with session_factory() as session:
            count = await revoke_all_sessions(
                session, user_id=current_user.id, except_session_id=sid
            )
            await _record_audit(
                session,
                user_id=current_user.id,
                action="auth.logout_all",
                request=request,
                payload={"revoked": count},
            )
            await session.commit()
        return LogoutAllResponse(revoked=int(count))

    @app.get("/api/v1/auth/me", response_model=AuthUser)
    async def auth_me(
        current_user: User = Depends(get_current_user),
    ) -> AuthUser:
        """Resolve the cookie session to ``AuthUser`` for the SPA."""
        return AuthUser(
            user_id=current_user.id,
            first_name=current_user.first_name or "",
            last_name=current_user.last_name or "",
            email=current_user.email,
            email_verified=current_user.email_verified_at is not None,
            onboarded=_is_onboarded(current_user),
        )

    @app.get("/api/v1/auth/sessions", response_model=SessionListResponse)
    async def list_sessions(
        request: Request,
        current_user: User = Depends(get_current_user),
    ) -> SessionListResponse:
        sid = current_session_id(request)
        async with session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(UserSession)
                        .where(UserSession.user_id == current_user.id)
                        .where(UserSession.revoked_at.is_(None))
                        .where(
                            UserSession.expires_at
                            > datetime.now(timezone.utc)
                        )
                        .order_by(UserSession.last_seen_at.desc())
                    )
                )
                .scalars()
                .all()
            )
        items = [
            SessionInfo(
                id=r.id,
                ip=r.ip,
                user_agent=r.user_agent,
                created_at=r.created_at,
                last_seen_at=r.last_seen_at,
                expires_at=r.expires_at,
                current=(r.id == sid),
            )
            for r in rows
        ]
        return SessionListResponse(sessions=items, count=len(items))

    @app.delete("/api/v1/auth/sessions/{session_id}")
    async def revoke_session_endpoint(
        session_id: uuid.UUID,
        request: Request,
        response: Response,
        current_user: User = Depends(get_current_user),
    ) -> dict[str, bool]:
        sid = current_session_id(request)
        async with session_factory() as session:
            row = await session.get(UserSession, session_id)
            if row is None or row.user_id != current_user.id:
                raise HTTPException(status_code=404, detail="session not found")
            if row.revoked_at is None:
                row.revoked_at = datetime.now(timezone.utc)
            await _record_audit(
                session,
                user_id=current_user.id,
                action="auth.session_revoked",
                request=request,
                payload={"session_id": str(session_id)},
            )
            await session.commit()
        # If the user just killed their own session, also drop the cookie.
        if sid == session_id:
            clear_session_cookie(response, request=request)
        return {"ok": True}

    @app.patch("/api/v1/auth/recovery-email", response_model=UserProfile)
    async def update_recovery_email(
        body: RecoveryEmailUpdate,
        request: Request,
        current_user: User = Depends(get_current_user),
    ) -> UserProfile:
        """Set or clear the optional secondary mailbox.

        The recovery email is what the forgot-email flow looks up; we
        only validate basic shape. Conflicts with the user's primary
        address are rejected so the recovery loop can never collapse
        into a self-reference.
        """
        new_value = (body.recovery_email or "").strip().lower() or None
        if new_value:
            if "@" not in new_value or "." not in new_value.split("@")[-1]:
                raise HTTPException(status_code=400, detail="invalid email")
            if current_user.email and current_user.email.lower() == new_value:
                raise HTTPException(
                    status_code=400,
                    detail="recovery email must differ from the primary one",
                )
        async with session_factory() as session:
            user = await session.get(User, current_user.id)
            if user is None:
                raise HTTPException(status_code=404, detail="user not found")
            user.recovery_email = new_value
            await _record_audit(
                session,
                user_id=user.id,
                action="auth.recovery_email_set" if new_value else "auth.recovery_email_cleared",
                request=request,
            )
            await session.commit()
            await session.refresh(user)
            return _to_profile(user)

    # ── /api/v1/auth/api-keys (issue / revoke bearer tokens) ───────────

    @app.get("/api/v1/auth/api-keys", response_model=ApiKeyListResponse)
    async def list_api_keys(
        current_user: User = Depends(get_current_user),
    ) -> ApiKeyListResponse:
        async with session_factory() as session:
            rows = list(
                (
                    await session.execute(
                        select(UserApiKey)
                        .where(UserApiKey.user_id == current_user.id)
                        .order_by(UserApiKey.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
        return ApiKeyListResponse(
            items=[
                ApiKeySchema(
                    id=r.id,
                    label=r.label,
                    token_preview=r.token_preview,
                    created_at=r.created_at,
                    last_used_at=r.last_used_at,
                    revoked=r.revoked_at is not None,
                )
                for r in rows
            ]
        )

    @app.post(
        "/api/v1/auth/api-keys", response_model=ApiKeyCreatedResponse
    )
    async def create_api_key(
        body: ApiKeyCreateRequest,
        current_user: User = Depends(get_current_user),
    ) -> ApiKeyCreatedResponse:
        """Mint a new long-lived bearer token for this user.

        Plaintext token is returned ONCE in the response — caller must
        copy it now. Storage keeps only the SHA-256 hash so a DB leak
        doesn't yield active tokens.
        """
        secret_part = secrets.token_urlsafe(32)
        plaintext = f"convioo_pk_{secret_part}"
        preview = f"{plaintext[:11]}…{plaintext[-4:]}"
        async with session_factory() as session:
            row = UserApiKey(
                user_id=current_user.id,
                token_hash=hash_token(plaintext),
                token_preview=preview,
                label=(body.label or "").strip() or None,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
        return ApiKeyCreatedResponse(
            id=row.id,
            token=plaintext,
            label=row.label,
            token_preview=row.token_preview,
            created_at=row.created_at,
        )

    @app.delete("/api/v1/auth/api-keys/{key_id}")
    async def revoke_api_key(
        key_id: uuid.UUID,
        current_user: User = Depends(get_current_user),
    ) -> dict[str, bool]:
        async with session_factory() as session:
            row = await session.get(UserApiKey, key_id)
            if row is None or row.user_id != current_user.id:
                raise HTTPException(status_code=404, detail="key not found")
            if row.revoked_at is None:
                row.revoked_at = datetime.now(timezone.utc)
                await session.commit()
        return {"ok": True}

    # ── /api/v1/webhooks (outbound subscriptions) ──────────────────────

    def _webhook_to_schema(row: Webhook) -> WebhookSchema:
        secret = row.secret or ""
        preview = (
            f"{secret[:4]}…{secret[-4:]}" if len(secret) >= 12 else "…"
        )
        return WebhookSchema(
            id=row.id,
            target_url=row.target_url,
            event_types=list(row.event_types or []),
            description=row.description,
            active=row.active,
            failure_count=row.failure_count,
            secret_preview=preview,
            last_delivery_at=row.last_delivery_at,
            last_delivery_status=row.last_delivery_status,
            last_failure_at=row.last_failure_at,
            last_failure_message=row.last_failure_message,
            created_at=row.created_at,
        )

    def _validate_webhook_input(
        target_url: str | None, event_types: list[str] | None
    ) -> None:
        if target_url is not None:
            cleaned = target_url.strip()
            if not cleaned.lower().startswith(("https://", "http://")):
                raise HTTPException(
                    status_code=400,
                    detail="target_url must start with http:// or https://",
                )
        if event_types is not None:
            unknown = [
                e for e in event_types if e not in WEBHOOK_ALLOWED_EVENTS
            ]
            if unknown:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"unknown event types: {', '.join(unknown)}. "
                        f"Allowed: {', '.join(WEBHOOK_ALLOWED_EVENTS)}."
                    ),
                )

    @app.get("/api/v1/webhooks", response_model=WebhookListResponse)
    async def list_webhooks(
        current_user: User = Depends(get_current_user),
    ) -> WebhookListResponse:
        async with session_factory() as session:
            rows = list(
                (
                    await session.execute(
                        select(Webhook)
                        .where(Webhook.user_id == current_user.id)
                        .order_by(Webhook.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
        return WebhookListResponse(
            items=[_webhook_to_schema(r) for r in rows]
        )

    @app.post(
        "/api/v1/webhooks", response_model=WebhookCreatedResponse
    )
    async def create_webhook(
        body: WebhookCreateRequest,
        current_user: User = Depends(get_current_user),
    ) -> WebhookCreatedResponse:
        _validate_webhook_input(body.target_url, body.event_types)
        secret_plaintext = generate_webhook_secret()
        async with session_factory() as session:
            row = Webhook(
                user_id=current_user.id,
                target_url=body.target_url.strip(),
                secret=secret_plaintext,
                event_types=list(dict.fromkeys(body.event_types)),
                description=(body.description or "").strip() or None,
                active=True,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
        schema = _webhook_to_schema(row)
        return WebhookCreatedResponse(
            **schema.model_dump(), secret=secret_plaintext
        )

    @app.patch(
        "/api/v1/webhooks/{webhook_id}", response_model=WebhookSchema
    )
    async def update_webhook(
        webhook_id: uuid.UUID,
        body: WebhookUpdateRequest,
        current_user: User = Depends(get_current_user),
    ) -> WebhookSchema:
        _validate_webhook_input(body.target_url, body.event_types)
        async with session_factory() as session:
            row = await session.get(Webhook, webhook_id)
            if row is None or row.user_id != current_user.id:
                raise HTTPException(status_code=404, detail="webhook not found")
            if body.target_url is not None:
                row.target_url = body.target_url.strip()
            if body.event_types is not None:
                row.event_types = list(dict.fromkeys(body.event_types))
            if body.description is not None:
                row.description = (body.description or "").strip() or None
            if body.active is not None:
                row.active = bool(body.active)
                # Re-enabling a disabled webhook resets the failure
                # counter so the next attempt isn't immediately the
                # 5th-and-disable.
                if body.active:
                    row.failure_count = 0
            await session.commit()
            await session.refresh(row)
        return _webhook_to_schema(row)

    @app.delete("/api/v1/webhooks/{webhook_id}")
    async def delete_webhook(
        webhook_id: uuid.UUID,
        current_user: User = Depends(get_current_user),
    ) -> dict[str, bool]:
        async with session_factory() as session:
            row = await session.get(Webhook, webhook_id)
            if row is None or row.user_id != current_user.id:
                raise HTTPException(status_code=404, detail="webhook not found")
            await session.delete(row)
            await session.commit()
        return {"ok": True}

    @app.post("/api/v1/webhooks/{webhook_id}/test")
    async def test_webhook(
        webhook_id: uuid.UUID,
        background_tasks: BackgroundTasks,
        current_user: User = Depends(get_current_user),
    ) -> dict[str, bool]:
        """Schedule a ``webhook.test`` event so the user can confirm
        their endpoint is reachable. The dispatcher itself reads from
        the DB; we just confirm the row belongs to the caller and
        kick the event."""
        async with session_factory() as session:
            row = await session.get(Webhook, webhook_id)
            if row is None or row.user_id != current_user.id:
                raise HTTPException(status_code=404, detail="webhook not found")
        background_tasks.add_task(
            emit_webhook_event_sync,
            current_user.id,
            "webhook.test",
            {
                "message": "ping from convioo",
                "webhook_id": str(webhook_id),
            },
        )
        return {"ok": True}

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
        user_id: int,
        body: ChangeEmailRequest,
        request: Request,
        current_user: User = Depends(get_current_user),
    ) -> AuthUser:
        """Initiate an email change.

        Validates the current password (so a stolen session can't
        silently swap the recovery address), checks the new address
        isn't already in use, and emails a confirmation link to the
        NEW address. The user's actual email only changes after that
        link is clicked — until then login keeps working with the old
        address.
        """
        if user_id != current_user.id:
            raise HTTPException(status_code=403, detail="forbidden")
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
            await _record_audit(
                session,
                user_id=user.id,
                action="auth.change_email_requested",
                request=request,
                payload={"new_email": new_email},
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

    @app.post("/api/v1/users/{user_id}/change-password", response_model=AuthUser)
    async def change_password(
        user_id: int,
        body: ChangePasswordRequest,
        request: Request,
        current_user: User = Depends(get_current_user),
    ) -> AuthUser:
        """Update the password. Requires the current one.

        On success: invalidates every OTHER live session (so a stolen
        cookie elsewhere stops working) and emails a security alert
        to the user's address.
        """
        if user_id != current_user.id:
            raise HTTPException(status_code=403, detail="forbidden")
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
            await revoke_all_sessions(
                session,
                user_id=user.id,
                except_session_id=current_session_id(request),
            )
            await _record_audit(
                session,
                user_id=user.id,
                action="auth.password_changed",
                request=request,
            )
            await session.commit()

        if user.email:
            html, text = render_password_changed_email(
                name=user.first_name or user.display_name or "",
                ip=request_ip(request),
                user_agent=request_user_agent(request),
                when_iso=datetime.now(timezone.utc).isoformat(),
            )
            await send_email(
                to=user.email,
                subject="Пароль изменён — Convioo",
                html=html,
                text=text,
            )

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
                request_ip(request),
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
            _seed_default_lead_statuses(session, team.id)
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

        Rate-limited per-user (60/min) and per-team (180/min) so a
        single tab spamming the chat can't drain the Anthropic budget.
        """
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
    async def create_search(
        body: SearchCreate, request: Request
    ) -> SearchCreateResponse:
        """Create a SearchQuery row + launch the pipeline.

        Execution path:
        1. Redis configured → enqueue on arq (worker does the heavy lifting).
        2. Redis NOT configured → spawn ``asyncio.create_task`` in this
           process. Runs fine for single-container Railway deployments with
           modest traffic; for production volume enable the queue.

        Rate-limit axes:
        - per-user (20/5min) so one juicy account can't burn the AI budget
        - per-team (60/5min) so one team can't choke a shared workspace
        - per-IP (30/5min) so a botted browser can't bypass auth
        """
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

            scope = (body.scope or "city").strip().lower()
            if scope not in {"city", "metro", "state", "country"}:
                scope = "city"
            radius_m_value: int | None = None
            if scope in {"city", "metro"} and body.radius_km is not None:
                radius_m_value = max(0, min(int(body.radius_km), 100)) * 1000

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
                .where(Lead.deleted_at.is_(None))
                .order_by(Lead.score_ai.desc().nullslast(), Lead.rating.desc().nullslast())
            )
            leads = list(result.scalars().all())
            lead_ids = [lead.id for lead in leads]
            marks = await _marks_for_user(session, user_id, lead_ids)
            tags_by_lead = await _tags_by_lead(session, lead_ids)

        if temp in {"hot", "warm", "cold"}:
            leads = [lead for lead in leads if _temp(lead.score_ai) == temp]
        return [
            _to_lead_response(
                lead, marks.get(lead.id), tags_by_lead.get(lead.id)
            )
            for lead in leads
        ]

    @app.get("/api/v1/leads", response_model=LeadListResponse)
    async def list_all_leads(
        user_id: int = WEB_DEMO_USER_ID,
        team_id: uuid.UUID | None = None,
        member_user_id: int | None = None,
        lead_status: str | None = None,
        temp: str | None = None,
        created_after: datetime | None = None,
        untouched_days: int | None = None,
        tag_id: uuid.UUID | None = None,
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
                .where(Lead.deleted_at.is_(None))
                .order_by(Lead.score_ai.desc().nullslast(), Lead.created_at.desc())
                .limit(limit)
            )
            total_stmt = (
                select(func.count(Lead.id))
                .join(SearchQuery, SearchQuery.id == Lead.query_id)
                .where(SearchQuery.source == "web")
                .where(Lead.deleted_at.is_(None))
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
            if tag_id is not None:
                tagged_subq = (
                    select(LeadTagAssignment.lead_id)
                    .where(LeadTagAssignment.tag_id == tag_id)
                    .subquery()
                )
                stmt = stmt.where(Lead.id.in_(select(tagged_subq.c.lead_id)))
                total_stmt = total_stmt.where(
                    Lead.id.in_(select(tagged_subq.c.lead_id))
                )
            rows = (await session.execute(stmt)).all()

            lead_ids = [lead.id for lead, _n, _r in rows]
            total = int((await session.execute(total_stmt)).scalar() or 0)
            marks = await _marks_for_user(session, user_id, lead_ids)
            tags_by_lead = await _tags_by_lead(session, lead_ids)

        leads: list[LeadResponse] = []
        sessions_by_id: dict[str, dict[str, Any]] = {}
        for lead, niche, region in rows:
            leads.append(
                _to_lead_response(
                    lead, marks.get(lead.id), tags_by_lead.get(lead.id)
                )
            )
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
                .where(Lead.deleted_at.is_(None))
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
                        .where(Lead.deleted_at.is_(None))
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
        background_tasks: BackgroundTasks,
        actor_user_id: int = WEB_DEMO_USER_ID,
    ) -> LeadResponse:
        """Partial update: status, owner, notes. Touches last_touched_at.

        Now also writes an entry to ``lead_activities`` per changed
        field so the timeline + team feed have something to render.
        ``actor_user_id`` (query string) is the user making the change;
        defaults to the demo user when unset.
        """
        async with session_factory() as session:
            lead = await session.get(Lead, lead_id)
            if lead is None:
                raise HTTPException(status_code=404, detail="lead not found")

            # Lead-status validation: team-mode searches use the
            # team's custom palette; personal-mode searches keep the
            # legacy hard-coded keys. Either way an unknown key fails.
            if body.lead_status is not None:
                search_for_status = await session.get(SearchQuery, lead.query_id)
                if search_for_status and search_for_status.team_id is not None:
                    valid_keys = {
                        k for (k,) in (
                            await session.execute(
                                select(LeadStatus.key).where(
                                    LeadStatus.team_id == search_for_status.team_id
                                )
                            )
                        ).all()
                    }
                else:
                    valid_keys = LEGACY_LEAD_STATUS_KEYS
                if body.lead_status not in valid_keys:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "lead_status must be one of "
                            + ", ".join(sorted(valid_keys))
                        ),
                    )

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

            # Emit lead.status_changed if the status moved this round.
            # We notify the search owner — they're who registered the
            # webhook against their account, regardless of who edited
            # it inside the team.
            status_change = next(
                (a for a in activities if a["kind"] == "status"), None
            )
            if status_change and search is not None:
                background_tasks.add_task(
                    emit_webhook_event_sync,
                    search.user_id,
                    "lead.status_changed",
                    {
                        "lead": serialize_lead_for_webhook(lead),
                        "from_status": status_change["payload"]["from"],
                        "to_status": status_change["payload"]["to"],
                        "actor_user_id": actor_user_id,
                    },
                )
            return LeadResponse.model_validate(lead)

    @app.delete("/api/v1/leads/{lead_id}")
    async def delete_lead(
        lead_id: uuid.UUID,
        forever: bool = False,
        current_user: User = Depends(get_current_user),
    ) -> dict[str, bool]:
        """Soft-delete a lead so it disappears from the CRM.

        ``forever=true`` additionally writes a row into the seen-leads
        table so future searches will treat the same place_id /
        phone / domain as already-delivered and skip it. Without
        ``forever``, the lead is just hidden — re-running a similar
        search may surface it again.

        Authorisation: caller must own the parent ``SearchQuery`` (or
        be a member of the team that owns it).
        """
        async with session_factory() as session:
            lead = await session.get(Lead, lead_id)
            if lead is None:
                raise HTTPException(status_code=404, detail="lead not found")
            search = await session.get(SearchQuery, lead.query_id)
            if search is None:
                raise HTTPException(status_code=404, detail="search not found")

            allowed = search.user_id == current_user.id
            if not allowed and search.team_id is not None:
                membership = await _membership(
                    session, search.team_id, current_user.id
                )
                allowed = membership is not None
            if not allowed:
                raise HTTPException(status_code=403, detail="forbidden")

            if lead.deleted_at is None:
                lead.deleted_at = datetime.now(timezone.utc)
            if forever:
                lead.blacklisted = True
                # Make sure the seen-leads record exists with all three
                # dedup axes filled, even if the lead came in before the
                # 0023 migration backfilled them.
                from leadgen.utils.dedup import (
                    domain_root as _domain_root,
                )
                from leadgen.utils.dedup import (
                    normalize_phone as _normalize_phone,
                )

                phone_key = _normalize_phone(lead.phone)
                domain_key = _domain_root(lead.website)

                if search.user_id != 0:
                    existing_user = (
                        await session.execute(
                            select(UserSeenLead)
                            .where(UserSeenLead.user_id == search.user_id)
                            .where(UserSeenLead.source == lead.source)
                            .where(UserSeenLead.source_id == lead.source_id)
                        )
                    ).scalar_one_or_none()
                    if existing_user is None:
                        session.add(
                            UserSeenLead(
                                user_id=search.user_id,
                                source=lead.source,
                                source_id=lead.source_id,
                                phone_e164=phone_key,
                                domain_root=domain_key,
                            )
                        )
                    else:
                        existing_user.phone_e164 = phone_key
                        existing_user.domain_root = domain_key
                if search.team_id is not None:
                    existing_team = (
                        await session.execute(
                            select(TeamSeenLead)
                            .where(TeamSeenLead.team_id == search.team_id)
                            .where(TeamSeenLead.source == lead.source)
                            .where(TeamSeenLead.source_id == lead.source_id)
                        )
                    ).scalar_one_or_none()
                    if existing_team is None:
                        session.add(
                            TeamSeenLead(
                                team_id=search.team_id,
                                source=lead.source,
                                source_id=lead.source_id,
                                phone_e164=phone_key,
                                domain_root=domain_key,
                                first_user_id=search.user_id,
                            )
                        )
                    else:
                        existing_team.phone_e164 = phone_key
                        existing_team.domain_root = domain_key

            session.add(
                LeadActivity(
                    lead_id=lead.id,
                    user_id=current_user.id,
                    team_id=search.team_id,
                    kind="deleted",
                    payload={"forever": bool(forever)},
                )
            )
            await session.commit()
        return {"ok": True, "forever": bool(forever)}

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

    @app.post(
        "/api/v1/leads/bulk-draft",
        response_model=BulkDraftEmailResponse,
    )
    async def bulk_draft_emails(
        body: BulkDraftEmailRequest,
        current_user: User = Depends(get_current_user),
    ) -> BulkDraftEmailResponse:
        """Generate cold-email drafts for up to 20 leads in one shot.

        The salesperson selects rows on /app/leads, hits "Написать
        всем", and gets back a stitched list ready for review. Per-
        lead errors don't take the whole batch down — failed entries
        come back with ``error`` populated.

        Concurrency is throttled (3 in-flight) so a 20-lead batch
        doesn't stampede Anthropic. Authorisation is per-lead: each
        lead must belong to a search the caller owns or is a member
        of via team.
        """
        async with session_factory() as session:
            user_profile: dict[str, Any] = {
                "display_name": current_user.display_name or current_user.first_name,
                "age_range": current_user.age_range,
                "gender": current_user.gender,
                "business_size": current_user.business_size,
                "profession": current_user.profession,
                "service_description": current_user.service_description,
                "home_region": current_user.home_region,
                "niches": list(current_user.niches or []),
                "language_code": current_user.language_code,
            }
            lead_rows = (
                (
                    await session.execute(
                        select(Lead, SearchQuery)
                        .join(SearchQuery, SearchQuery.id == Lead.query_id)
                        .where(Lead.id.in_(list(body.lead_ids)))
                    )
                )
                .all()
            )
            authorised: dict[uuid.UUID, Lead] = {}
            for lead, search in lead_rows:
                if search.user_id == current_user.id:
                    authorised[lead.id] = lead
                    continue
                if search.team_id is not None and (
                    await _membership(session, search.team_id, current_user.id)
                ):
                    authorised[lead.id] = lead

        analyzer = AIAnalyzer()
        sem = asyncio.Semaphore(3)
        tone = (body.tone or "professional").strip().lower()

        async def _one(lead_id: uuid.UUID) -> BulkDraftEmailItem:
            lead = authorised.get(lead_id)
            if lead is None:
                return BulkDraftEmailItem(
                    lead_id=lead_id, error="not authorised"
                )
            payload = {
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
            async with sem:
                try:
                    result = await analyzer.generate_cold_email(
                        payload,
                        user_profile=user_profile,
                        tone=tone,
                        extra_context=body.extra_context,
                    )
                    return BulkDraftEmailItem(
                        lead_id=lead_id,
                        subject=result.get("subject"),
                        body=result.get("body"),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "bulk-draft: failed for lead %s", lead_id
                    )
                    return BulkDraftEmailItem(
                        lead_id=lead_id, error=str(exc)[:200]
                    )

        items = await asyncio.gather(*(_one(lid) for lid in body.lead_ids))
        return BulkDraftEmailResponse(items=list(items))

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

        async with session_factory() as session:
            # Permissive validation: accept if matches a legacy key OR
            # any team's custom palette. Bulk operations span teams so
            # a strict per-team check would block mixed selections.
            if (
                body.lead_status
                and body.lead_status not in LEGACY_LEAD_STATUS_KEYS
            ):
                custom = (
                    await session.execute(
                        select(LeadStatus.key).where(
                            LeadStatus.key == body.lead_status
                        ).limit(1)
                    )
                ).scalar_one_or_none()
                if custom is None:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "lead_status is not a valid key in any "
                            "team palette or the default set"
                        ),
                    )
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

    # ── /api/v1/tags (user-defined CRM tags) ──────────────────────────

    @app.get("/api/v1/tags", response_model=LeadTagListResponse)
    async def list_tags(
        team_id: uuid.UUID | None = None,
        current_user: User = Depends(get_current_user),
    ) -> LeadTagListResponse:
        """Return the caller's tag palette.

        Personal palette by default; pass ``team_id`` to get the
        shared team palette. The endpoint enforces team membership
        so an outsider can't enumerate someone else's chips.
        """
        async with session_factory() as session:
            stmt = select(LeadTag).order_by(LeadTag.created_at.asc())
            if team_id is not None:
                membership = await _membership(session, team_id, current_user.id)
                if membership is None:
                    raise HTTPException(status_code=403, detail="forbidden")
                stmt = stmt.where(LeadTag.team_id == team_id)
            else:
                stmt = stmt.where(LeadTag.user_id == current_user.id).where(
                    LeadTag.team_id.is_(None)
                )
            rows = (await session.execute(stmt)).scalars().all()
        return LeadTagListResponse(
            items=[
                LeadTagSchema(
                    id=t.id, name=t.name, color=t.color, team_id=t.team_id
                )
                for t in rows
            ]
        )

    @app.post("/api/v1/tags", response_model=LeadTagSchema)
    async def create_tag(
        body: LeadTagCreate,
        current_user: User = Depends(get_current_user),
    ) -> LeadTagSchema:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        color = (body.color or "slate").strip().lower()
        async with session_factory() as session:
            if body.team_id is not None:
                membership = await _membership(
                    session, body.team_id, current_user.id
                )
                if membership is None:
                    raise HTTPException(status_code=403, detail="forbidden")
            # Standard SQL treats NULLs as distinct in unique
            # constraints, which would let two personal tags share a
            # name. Pre-check explicitly so the conflict surfaces the
            # same way on Postgres and SQLite.
            collision_stmt = select(LeadTag).where(
                func.lower(LeadTag.name) == name.lower()
            )
            if body.team_id is None:
                collision_stmt = collision_stmt.where(
                    LeadTag.user_id == current_user.id
                ).where(LeadTag.team_id.is_(None))
            else:
                collision_stmt = collision_stmt.where(
                    LeadTag.team_id == body.team_id
                )
            existing = (
                await session.execute(collision_stmt.limit(1))
            ).scalar_one_or_none()
            if existing is not None:
                raise HTTPException(
                    status_code=409,
                    detail="tag with this name already exists",
                )
            tag = LeadTag(
                user_id=current_user.id,
                team_id=body.team_id,
                name=name,
                color=color,
            )
            session.add(tag)
            await session.commit()
            await session.refresh(tag)
        return LeadTagSchema(
            id=tag.id, name=tag.name, color=tag.color, team_id=tag.team_id
        )

    @app.patch("/api/v1/tags/{tag_id}", response_model=LeadTagSchema)
    async def update_tag(
        tag_id: uuid.UUID,
        body: LeadTagUpdate,
        current_user: User = Depends(get_current_user),
    ) -> LeadTagSchema:
        async with session_factory() as session:
            tag = await session.get(LeadTag, tag_id)
            if tag is None:
                raise HTTPException(status_code=404, detail="tag not found")
            if not await _can_manage_tag(session, tag, current_user.id):
                raise HTTPException(status_code=403, detail="forbidden")
            if body.name is not None:
                cleaned = body.name.strip()
                if not cleaned:
                    raise HTTPException(
                        status_code=400, detail="name cannot be empty"
                    )
                # Same pre-check as create — make rename collisions
                # surface as 409 even on SQLite where NULL-distinct
                # unique constraints don't catch personal-tag dupes.
                collision_stmt = (
                    select(LeadTag.id)
                    .where(LeadTag.id != tag.id)
                    .where(func.lower(LeadTag.name) == cleaned.lower())
                )
                if tag.team_id is None:
                    collision_stmt = collision_stmt.where(
                        LeadTag.user_id == tag.user_id
                    ).where(LeadTag.team_id.is_(None))
                else:
                    collision_stmt = collision_stmt.where(
                        LeadTag.team_id == tag.team_id
                    )
                if (
                    await session.execute(collision_stmt.limit(1))
                ).scalar_one_or_none() is not None:
                    raise HTTPException(
                        status_code=409,
                        detail="tag with this name already exists",
                    )
                tag.name = cleaned
            if body.color is not None:
                tag.color = body.color.strip().lower() or "slate"
            await session.commit()
            await session.refresh(tag)
        return LeadTagSchema(
            id=tag.id, name=tag.name, color=tag.color, team_id=tag.team_id
        )

    @app.delete("/api/v1/tags/{tag_id}")
    async def delete_tag(
        tag_id: uuid.UUID,
        current_user: User = Depends(get_current_user),
    ) -> dict[str, bool]:
        async with session_factory() as session:
            tag = await session.get(LeadTag, tag_id)
            if tag is None:
                raise HTTPException(status_code=404, detail="tag not found")
            if not await _can_manage_tag(session, tag, current_user.id):
                raise HTTPException(status_code=403, detail="forbidden")
            await session.delete(tag)
            await session.commit()
        return {"ok": True}

    @app.put(
        "/api/v1/leads/{lead_id}/tags",
        response_model=LeadTagListResponse,
    )
    async def assign_lead_tags(
        lead_id: uuid.UUID,
        body: LeadTagsAssignRequest,
        current_user: User = Depends(get_current_user),
    ) -> LeadTagListResponse:
        """Replace the lead's tag set with the supplied list.

        Authorisation: caller must own the parent search query (or be
        a member of the team that does). Tag ids must belong to the
        caller (personal) or the same team — we don't allow attaching
        a foreign team's tag to a shared lead.
        """
        async with session_factory() as session:
            lead = await session.get(Lead, lead_id)
            if lead is None:
                raise HTTPException(status_code=404, detail="lead not found")
            search = await session.get(SearchQuery, lead.query_id)
            if search is None:
                raise HTTPException(status_code=404, detail="search not found")
            allowed = search.user_id == current_user.id
            if not allowed and search.team_id is not None:
                allowed = (
                    await _membership(session, search.team_id, current_user.id)
                ) is not None
            if not allowed:
                raise HTTPException(status_code=403, detail="forbidden")

            requested_ids = list(dict.fromkeys(body.tag_ids))  # preserve order, dedup
            tag_rows: list[LeadTag] = []
            if requested_ids:
                tags_stmt = select(LeadTag).where(LeadTag.id.in_(requested_ids))
                tag_rows = list((await session.execute(tags_stmt)).scalars().all())
                if len(tag_rows) != len(requested_ids):
                    raise HTTPException(
                        status_code=404, detail="some tags not found"
                    )
                for tag in tag_rows:
                    tag_owned_personally = (
                        tag.user_id == current_user.id and tag.team_id is None
                    )
                    tag_owned_by_lead_team = (
                        tag.team_id is not None
                        and tag.team_id == search.team_id
                    )
                    if not (tag_owned_personally or tag_owned_by_lead_team):
                        raise HTTPException(
                            status_code=403,
                            detail="tag is not available in this scope",
                        )

            await session.execute(
                LeadTagAssignment.__table__.delete().where(
                    LeadTagAssignment.lead_id == lead_id
                )
            )
            for tag in tag_rows:
                session.add(
                    LeadTagAssignment(lead_id=lead_id, tag_id=tag.id)
                )
            await session.commit()

        return LeadTagListResponse(
            items=[
                LeadTagSchema(
                    id=t.id, name=t.name, color=t.color, team_id=t.team_id
                )
                for t in tag_rows
            ]
        )

    # ── /api/v1/segments (saved CRM filter views) ──────────────────────

    def _segment_to_schema(row: LeadSegment) -> LeadSegmentSchema:
        return LeadSegmentSchema(
            id=str(row.id),
            name=row.name,
            team_id=str(row.team_id) if row.team_id else None,
            filter_json=row.filter_json or {},
            sort_order=row.sort_order,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @app.get(
        "/api/v1/segments", response_model=LeadSegmentListResponse
    )
    async def list_segments(
        current_user: User = Depends(get_current_user),
    ) -> LeadSegmentListResponse:
        """Return private segments + every team-scoped segment the user
        sees through their memberships, ordered by ``sort_order``."""
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
            stmt = select(LeadSegment).where(
                sa.or_(
                    sa.and_(
                        LeadSegment.user_id == current_user.id,
                        LeadSegment.team_id.is_(None),
                    ),
                    LeadSegment.team_id.in_(team_ids) if team_ids else sa.false(),
                )
            ).order_by(LeadSegment.sort_order, LeadSegment.created_at)
            rows = (await session.execute(stmt)).scalars().all()
        return LeadSegmentListResponse(
            items=[_segment_to_schema(r) for r in rows]
        )

    @app.post(
        "/api/v1/segments", response_model=LeadSegmentSchema
    )
    async def create_segment(
        body: LeadSegmentCreate,
        current_user: User = Depends(get_current_user),
    ) -> LeadSegmentSchema:
        """Save a new segment for the current user."""
        team_uuid: uuid.UUID | None = None
        if body.team_id:
            try:
                team_uuid = uuid.UUID(body.team_id)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400, detail="invalid team_id"
                ) from exc

        async with session_factory() as session:
            if team_uuid is not None:
                # Make sure the user actually belongs to that team —
                # otherwise they could attach a private bookmark to
                # somebody else's workspace.
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
            row = LeadSegment(
                user_id=current_user.id,
                team_id=team_uuid,
                name=body.name.strip(),
                filter_json=body.filter_json or {},
                sort_order=body.sort_order,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
        return _segment_to_schema(row)

    @app.patch(
        "/api/v1/segments/{segment_id}",
        response_model=LeadSegmentSchema,
    )
    async def update_segment(
        segment_id: uuid.UUID,
        body: LeadSegmentUpdate,
        current_user: User = Depends(get_current_user),
    ) -> LeadSegmentSchema:
        async with session_factory() as session:
            row = await session.get(LeadSegment, segment_id)
            if row is None or row.user_id != current_user.id:
                raise HTTPException(
                    status_code=404, detail="segment not found"
                )
            if body.name is not None:
                row.name = body.name.strip()
            if body.filter_json is not None:
                row.filter_json = body.filter_json
            if body.sort_order is not None:
                row.sort_order = body.sort_order
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(row)
        return _segment_to_schema(row)

    @app.delete("/api/v1/segments/{segment_id}")
    async def delete_segment(
        segment_id: uuid.UUID,
        current_user: User = Depends(get_current_user),
    ) -> dict[str, bool]:
        async with session_factory() as session:
            row = await session.get(LeadSegment, segment_id)
            if row is None or row.user_id != current_user.id:
                raise HTTPException(
                    status_code=404, detail="segment not found"
                )
            await session.delete(row)
            await session.commit()
        return {"ok": True}

    # ── /api/v1/integrations/notion ────────────────────────────────────

    @app.get(
        "/api/v1/integrations/notion",
        response_model=NotionIntegrationStatus,
    )
    async def get_notion_integration(
        current_user: User = Depends(get_current_user),
    ) -> NotionIntegrationStatus:
        async with session_factory() as session:
            row = (
                await session.execute(
                    select(UserIntegrationCredential)
                    .where(UserIntegrationCredential.user_id == current_user.id)
                    .where(UserIntegrationCredential.provider == "notion")
                )
            ).scalar_one_or_none()
        if row is None:
            return NotionIntegrationStatus(connected=False)
        from leadgen.core.services.secrets_vault import decrypt, mask_token

        try:
            preview = mask_token(decrypt(row.token_ciphertext))
        except ValueError:
            preview = None  # key rotated; UI will offer reconnect
        config = row.config or {}
        return NotionIntegrationStatus(
            connected=True,
            token_preview=preview,
            database_id=config.get("database_id"),
            workspace_name=config.get("workspace_name"),
            updated_at=row.updated_at,
        )

    @app.put(
        "/api/v1/integrations/notion",
        response_model=NotionIntegrationStatus,
    )
    async def connect_notion(
        body: NotionConnectRequest,
        current_user: User = Depends(get_current_user),
    ) -> NotionIntegrationStatus:
        """Save (or replace) the user's Notion credentials.

        We immediately probe the database to validate the token has
        access — saving an unworkable credential would just give the
        user a misleading "connected" badge.
        """
        from leadgen.core.services.secrets_vault import encrypt, mask_token
        from leadgen.integrations.notion import NotionClient, NotionError

        token = body.token.strip()
        database_id = body.database_id.strip()
        try:
            async with NotionClient(token) as client:
                schema = await client.get_database(database_id)
        except NotionError as exc:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Notion отказал в доступе к базе. Проверьте что "
                    "интеграция share-нута на эту базу и токен "
                    f"актуален. Подробности: {exc}"
                ),
            ) from exc

        workspace_name = (schema.get("title") or [{}])[0].get(
            "plain_text"
        ) or None
        ciphertext = encrypt(token)
        config: dict[str, Any] = {
            "database_id": database_id,
            "workspace_name": workspace_name,
        }
        async with session_factory() as session:
            existing = (
                await session.execute(
                    select(UserIntegrationCredential)
                    .where(
                        UserIntegrationCredential.user_id == current_user.id
                    )
                    .where(UserIntegrationCredential.provider == "notion")
                )
            ).scalar_one_or_none()
            if existing is None:
                row = UserIntegrationCredential(
                    user_id=current_user.id,
                    provider="notion",
                    token_ciphertext=ciphertext,
                    config=config,
                )
                session.add(row)
            else:
                existing.token_ciphertext = ciphertext
                existing.config = config
                existing.updated_at = datetime.now(timezone.utc)
                row = existing
            await session.commit()
            await session.refresh(row)

        return NotionIntegrationStatus(
            connected=True,
            token_preview=mask_token(token),
            database_id=database_id,
            workspace_name=workspace_name,
            updated_at=row.updated_at,
        )

    @app.delete("/api/v1/integrations/notion")
    async def disconnect_notion(
        current_user: User = Depends(get_current_user),
    ) -> dict[str, bool]:
        async with session_factory() as session:
            row = (
                await session.execute(
                    select(UserIntegrationCredential)
                    .where(
                        UserIntegrationCredential.user_id == current_user.id
                    )
                    .where(UserIntegrationCredential.provider == "notion")
                )
            ).scalar_one_or_none()
            if row is not None:
                await session.delete(row)
                await session.commit()
        return {"ok": True}

    @app.post(
        "/api/v1/leads/export-to-notion",
        response_model=NotionExportResponse,
    )
    async def export_leads_to_notion(
        body: NotionExportRequest,
        current_user: User = Depends(get_current_user),
    ) -> NotionExportResponse:
        """Push a batch of selected leads as new pages in the user's database.

        Authorisation is per-lead — only leads the caller owns (or can
        see via team membership) get pushed. Per-lead failures inline
        as ``error`` so a misconfigured property doesn't sink the
        whole batch.
        """
        from leadgen.core.services.secrets_vault import decrypt
        from leadgen.integrations.notion import (
            NotionClient,
            NotionError,
            NotionExportRow,
            resolve_property_map,
            row_to_properties,
        )

        async with session_factory() as session:
            cred = (
                await session.execute(
                    select(UserIntegrationCredential)
                    .where(
                        UserIntegrationCredential.user_id == current_user.id
                    )
                    .where(UserIntegrationCredential.provider == "notion")
                )
            ).scalar_one_or_none()
            if cred is None:
                raise HTTPException(
                    status_code=400,
                    detail="Notion is not connected. Connect it in Settings → Интеграции.",
                )
            try:
                token = decrypt(cred.token_ciphertext)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Saved Notion credentials are unreadable "
                        "(encryption key rotated). Reconnect in Settings."
                    ),
                ) from exc
            database_id = (cred.config or {}).get("database_id")
            if not database_id:
                raise HTTPException(
                    status_code=400,
                    detail="Notion database is not set; reconnect in Settings.",
                )

            # Lead authorisation join (same pattern as bulk-draft).
            lead_rows = (
                (
                    await session.execute(
                        select(Lead, SearchQuery)
                        .join(SearchQuery, SearchQuery.id == Lead.query_id)
                        .where(Lead.id.in_(list(body.lead_ids)))
                    )
                )
                .all()
            )
            authorised: dict[uuid.UUID, tuple[Lead, SearchQuery]] = {}
            for lead, search in lead_rows:
                if search.user_id == current_user.id:
                    authorised[lead.id] = (lead, search)
                    continue
                if search.team_id is not None and (
                    await _membership(session, search.team_id, current_user.id)
                ):
                    authorised[lead.id] = (lead, search)
            tags_by_lead = await _tags_by_lead(session, list(authorised))

        items: list[NotionExportItem] = []
        async with NotionClient(token) as client:
            try:
                schema = await client.get_database(database_id)
            except NotionError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Notion database is unreachable: {exc}",
                ) from exc
            mapping = resolve_property_map(schema)
            if "name" not in mapping:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Notion database must have a Title column. "
                        "Add one in Notion and try again."
                    ),
                )

            for lead_id in body.lead_ids:
                pair = authorised.get(lead_id)
                if pair is None:
                    items.append(
                        NotionExportItem(
                            lead_id=lead_id, error="not authorised"
                        )
                    )
                    continue
                lead, search = pair
                row = NotionExportRow(
                    name=lead.name or "(unnamed)",
                    score=int(round(lead.score_ai)) if lead.score_ai else None,
                    status=lead.lead_status,
                    rating=lead.rating,
                    reviews=lead.reviews_count,
                    phone=lead.phone,
                    website=lead.website,
                    address=lead.address,
                    category=lead.category,
                    notes=lead.notes,
                    niche=search.niche,
                    region=search.region,
                    tags=tuple(
                        tag.name
                        for tag in tags_by_lead.get(lead_id, ())
                    ),
                )
                properties = row_to_properties(row, mapping)
                try:
                    page = await client.create_page(
                        database_id=database_id, properties=properties
                    )
                    items.append(
                        NotionExportItem(
                            lead_id=lead_id,
                            notion_url=page.get("url"),
                        )
                    )
                except NotionError as exc:
                    logger.exception(
                        "notion export: failed for lead %s", lead_id
                    )
                    items.append(
                        NotionExportItem(lead_id=lead_id, error=str(exc)[:200])
                    )

        successes = sum(1 for it in items if it.notion_url)
        return NotionExportResponse(
            items=items,
            success_count=successes,
            failure_count=len(items) - successes,
        )

    # ── /api/v1/oauth/gmail (OAuth flow + send-as-user) ────────────────
    #
    # Stage-mode: empty GOOGLE_OAUTH_CLIENT_ID / _SECRET makes
    # /authorize, /callback and /leads/{id}/send-email respond 503,
    # leaving the rest of the API healthy.

    def _gmail_oauth_configured() -> bool:
        s = get_settings()
        return bool(s.google_oauth_client_id and s.google_oauth_client_secret)

    def _gmail_unavailable() -> HTTPException:
        return HTTPException(
            status_code=503,
            detail=(
                "Gmail OAuth is not configured on this deployment. "
                "Set GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET "
                "and GOOGLE_OAUTH_REDIRECT_URI to enable Gmail send."
            ),
        )

    @app.get(
        "/api/v1/oauth/gmail",
        response_model=GmailIntegrationStatus,
    )
    async def gmail_status(
        current_user: User = Depends(get_current_user),
    ) -> GmailIntegrationStatus:
        async with session_factory() as session:
            cred = (
                await session.execute(
                    select(OAuthCredential)
                    .where(OAuthCredential.user_id == current_user.id)
                    .where(OAuthCredential.provider == "gmail")
                )
            ).scalar_one_or_none()
        if cred is None:
            return GmailIntegrationStatus(connected=False)
        return GmailIntegrationStatus(
            connected=True,
            account_email=cred.account_email,
            scope=cred.scope,
            expires_at=cred.expires_at,
        )

    @app.get(
        "/api/v1/oauth/gmail/authorize",
        response_model=GmailAuthorizeResponse,
    )
    async def gmail_authorize(
        current_user: User = Depends(get_current_user),
    ) -> GmailAuthorizeResponse:
        """Mint a consent-screen URL the SPA redirects the user to.

        ``state`` is a random-but-deterministically-prefixed token
        carrying the user id so the callback can match the inbound
        code to the right account without any session storage.
        """
        if not _gmail_oauth_configured():
            raise _gmail_unavailable()
        from leadgen.integrations.gmail import build_authorize_url

        settings = get_settings()
        nonce = secrets.token_urlsafe(16)
        state = f"{current_user.id}:{nonce}"
        url = build_authorize_url(
            client_id=settings.google_oauth_client_id,
            redirect_uri=settings.google_oauth_redirect_uri,
            state=state,
        )
        return GmailAuthorizeResponse(url=url, state=state)

    @app.get("/api/v1/oauth/gmail/callback")
    async def gmail_callback(
        code: str = Query(..., min_length=10, max_length=512),
        state: str = Query(..., min_length=1, max_length=256),
    ) -> Response:
        """Receive Google's callback, exchange the code, store tokens.

        We don't go through ``get_current_user`` here because Google
        bounces back without our session cookie when the consent
        happens in a fresh browser context. The user-id is recovered
        from ``state`` (which we minted above), and ``state`` is
        otherwise opaque to Google.
        """
        if not _gmail_oauth_configured():
            raise _gmail_unavailable()
        from leadgen.core.services.oauth_store import save_tokens
        from leadgen.integrations.gmail import (
            GmailError,
            exchange_code_for_tokens,
            fetch_account_email,
        )

        try:
            user_id_str, _ = state.split(":", 1)
            user_id = int(user_id_str)
        except (ValueError, AttributeError) as exc:
            raise HTTPException(
                status_code=400, detail="invalid state"
            ) from exc

        settings = get_settings()
        try:
            tokens = await exchange_code_for_tokens(
                code,
                client_id=settings.google_oauth_client_id,
                client_secret=settings.google_oauth_client_secret,
                redirect_uri=settings.google_oauth_redirect_uri,
            )
        except GmailError as exc:
            raise HTTPException(
                status_code=400, detail=f"oauth: {exc}"
            ) from exc

        account_email = await fetch_account_email(tokens.access_token)
        async with session_factory() as session:
            await save_tokens(
                session,
                user_id=user_id,
                provider="gmail",
                tokens=tokens,
                account_email=account_email,
            )

        # Bounce back to the Settings page where the user kicked the
        # flow off. ``PUBLIC_APP_URL`` is the canonical front-end
        # origin so the redirect lands in their browser tab.
        return_to = (
            settings.public_app_url.rstrip("/") + "/app/settings?gmail=connected"
        )
        return Response(
            status_code=302,
            content="redirecting",
            headers={"Location": return_to},
        )

    @app.delete("/api/v1/oauth/gmail")
    async def gmail_disconnect(
        current_user: User = Depends(get_current_user),
    ) -> dict[str, bool]:
        async with session_factory() as session:
            cred = (
                await session.execute(
                    select(OAuthCredential)
                    .where(OAuthCredential.user_id == current_user.id)
                    .where(OAuthCredential.provider == "gmail")
                )
            ).scalar_one_or_none()
            if cred is not None:
                await session.delete(cred)
                await session.commit()
        return {"ok": True}

    @app.post(
        "/api/v1/leads/{lead_id}/send-email",
        response_model=GmailSendResponse,
    )
    async def gmail_send_email(
        lead_id: uuid.UUID,
        body: GmailSendRequest,
        current_user: User = Depends(get_current_user),
    ) -> GmailSendResponse:
        """Send an email through the user's Gmail account.

        Logs a ``LeadActivity`` of kind="email_sent" so the timeline
        on the lead modal shows the message went out — body is
        truncated to 4000 chars in the activity record so the JSONB
        column doesn't bloat over time.
        """
        if not _gmail_oauth_configured():
            raise _gmail_unavailable()
        from leadgen.core.services.oauth_store import (
            OAuthStoreError,
            ensure_fresh_token,
        )
        from leadgen.integrations.gmail import (
            GmailError,
            build_raw_message,
            send_message,
        )

        async with session_factory() as session:
            lead = await session.get(Lead, lead_id)
            if lead is None or lead.deleted_at is not None:
                raise HTTPException(status_code=404, detail="lead not found")
            # Use the explicit override or pull the first email out of
            # the website-meta blob; fail loudly if neither is set.
            recipient = body.to or _extract_lead_email(lead)
            if not recipient:
                raise HTTPException(
                    status_code=400,
                    detail="lead has no email address on file",
                )

            try:
                fresh = await ensure_fresh_token(
                    session, user_id=current_user.id, provider="gmail"
                )
            except OAuthStoreError as exc:
                raise HTTPException(
                    status_code=400, detail=str(exc)
                ) from exc

            from_addr = fresh.account_email or current_user.email or ""
            if not from_addr:
                raise HTTPException(
                    status_code=400,
                    detail="cannot determine sender address",
                )
            raw = build_raw_message(
                from_addr=from_addr,
                to_addr=recipient,
                subject=body.subject,
                body=body.body,
            )
            try:
                resp = await send_message(
                    access_token=fresh.access_token, raw_message=raw
                )
            except GmailError as exc:
                raise HTTPException(
                    status_code=502, detail=f"gmail send failed: {exc}"
                ) from exc

            now = datetime.now(timezone.utc)
            activity = LeadActivity(
                lead_id=lead_id,
                user_id=current_user.id,
                kind="email_sent",
                payload={
                    "to": recipient,
                    "subject": body.subject[:255],
                    "body": body.body[:4000],
                    "message_id": resp.get("id"),
                    "thread_id": resp.get("threadId"),
                },
                created_at=now,
            )
            session.add(activity)
            lead.last_touched_at = now
            await session.commit()

        return GmailSendResponse(
            message_id=resp.get("id") or "",
            thread_id=resp.get("threadId"),
            sent_at=now,
        )

    # ── /api/v1/billing (Stripe Checkout + Portal + webhooks) ──────────
    #
    # Stage-mode behavior: when STRIPE_SECRET_KEY is empty, all four
    # endpoints respond 503 with a friendly JSON body so the rest of
    # the API stays useful for development without billing keys.

    def _billing_configured() -> bool:
        s = get_settings()
        return bool(s.stripe_secret_key)

    def _stripe_unavailable() -> HTTPException:
        return HTTPException(
            status_code=503,
            detail=(
                "Stripe is not configured on this deployment. Set "
                "STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, "
                "STRIPE_PRICE_ID_PRO and STRIPE_PRICE_ID_AGENCY to "
                "enable billing."
            ),
        )

    @app.get(
        "/api/v1/billing/subscription",
        response_model=BillingSubscriptionResponse,
    )
    async def billing_subscription(
        current_user: User = Depends(get_current_user),
    ) -> BillingSubscriptionResponse:
        """Return the user's current plan / trial state.

        Cheap enough to call from anywhere — no Stripe round-trip,
        we just read the columns the webhook handler maintains.
        """

        async with session_factory() as session:
            user = await session.get(User, current_user.id)
            if user is None:
                raise HTTPException(status_code=404, detail="user not found")

            now = datetime.now(timezone.utc)
            trial_active = bool(
                user.trial_ends_at
                and (
                    user.trial_ends_at.replace(tzinfo=timezone.utc)
                    if user.trial_ends_at.tzinfo is None
                    else user.trial_ends_at
                )
                > now
            )
            paid_active = (
                user.plan != "free"
                and user.plan_until is not None
                and (
                    user.plan_until.replace(tzinfo=timezone.utc)
                    if user.plan_until.tzinfo is None
                    else user.plan_until
                )
                > now
            )
            return BillingSubscriptionResponse(
                plan=user.plan,
                plan_until=user.plan_until,
                trial_ends_at=user.trial_ends_at,
                trial_active=trial_active,
                paid_active=paid_active,
                has_stripe_customer=bool(user.stripe_customer_id),
                queries_used=user.queries_used,
                queries_limit=user.queries_limit,
            )

    @app.post(
        "/api/v1/billing/checkout", response_model=CheckoutResponse
    )
    async def billing_checkout(
        body: CheckoutRequest,
        current_user: User = Depends(get_current_user),
    ) -> CheckoutResponse:
        """Mint a Stripe Checkout Session and return its hosted URL."""
        if not _billing_configured():
            raise _stripe_unavailable()
        from leadgen.integrations.stripe_client import (
            StripeClient,
            StripeError,
        )

        settings = get_settings()
        if body.plan == "pro":
            price_id = settings.stripe_price_id_pro
        else:
            price_id = settings.stripe_price_id_agency
        if not price_id:
            raise HTTPException(
                status_code=503,
                detail=f"price id for plan '{body.plan}' is not set",
            )

        async with session_factory() as session:
            user = await session.get(User, current_user.id)
            if user is None:
                raise HTTPException(status_code=404, detail="user not found")
            customer_id = user.stripe_customer_id
            email = user.email

        try:
            async with StripeClient(settings.stripe_secret_key) as client:
                cs = await client.create_checkout_session(
                    price_id=price_id,
                    success_url=body.success_url,
                    cancel_url=body.cancel_url,
                    customer_id=customer_id,
                    customer_email=email if not customer_id else None,
                    client_reference_id=str(current_user.id),
                )
        except StripeError as exc:
            raise HTTPException(
                status_code=502, detail=f"stripe error: {exc}"
            ) from exc

        if cs.customer and not customer_id:
            async with session_factory() as session:
                await session.execute(
                    update(User)
                    .where(User.id == current_user.id)
                    .values(stripe_customer_id=cs.customer)
                )
                await session.commit()
        return CheckoutResponse(url=cs.url, session_id=cs.id)

    @app.post(
        "/api/v1/billing/portal", response_model=PortalResponse
    )
    async def billing_portal(
        body: PortalRequest,
        current_user: User = Depends(get_current_user),
    ) -> PortalResponse:
        """Mint a Customer Portal session for plan management."""
        if not _billing_configured():
            raise _stripe_unavailable()
        from leadgen.integrations.stripe_client import (
            StripeClient,
            StripeError,
        )

        async with session_factory() as session:
            user = await session.get(User, current_user.id)
            if user is None or not user.stripe_customer_id:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "No Stripe customer for this user yet — "
                        "run checkout first."
                    ),
                )
            customer_id = user.stripe_customer_id

        settings = get_settings()
        try:
            async with StripeClient(settings.stripe_secret_key) as client:
                portal = await client.create_portal_session(
                    customer_id=customer_id, return_url=body.return_url
                )
        except StripeError as exc:
            raise HTTPException(
                status_code=502, detail=f"stripe error: {exc}"
            ) from exc
        return PortalResponse(url=portal.url)

    @app.post("/api/v1/billing/webhook")
    async def billing_webhook(request: Request) -> Response:
        """Receive Stripe events and reflect plan changes onto users.

        Idempotent: every event id is recorded in ``stripe_events`` and
        a duplicate insert short-circuits to 200 so Stripe stops
        retrying. Signature verification is mandatory — without
        STRIPE_WEBHOOK_SECRET set we refuse every request.
        """
        if not _billing_configured():
            raise _stripe_unavailable()
        from leadgen.integrations.stripe_client import (
            StripeSignatureError,
            verify_webhook_signature,
        )

        settings = get_settings()
        body = await request.body()
        sig = request.headers.get("stripe-signature")
        try:
            verify_webhook_signature(body, sig, settings.stripe_webhook_secret)
        except StripeSignatureError as exc:
            raise HTTPException(
                status_code=400, detail=f"signature: {exc}"
            ) from exc

        try:
            event = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=400, detail="invalid json body"
            ) from exc

        event_id = event.get("id") or ""
        kind = event.get("type") or ""
        if not event_id or not kind:
            raise HTTPException(status_code=400, detail="missing id/type")

        async with session_factory() as session:
            session.add(StripeEvent(id=event_id, kind=kind))
            try:
                await session.commit()
            except IntegrityError:
                # Already processed — Stripe retried.
                await session.rollback()
                return Response(status_code=200, content="duplicate")

        data = (event.get("data") or {}).get("object") or {}
        await _apply_stripe_event(kind, data)
        return Response(status_code=200, content="ok")

    async def _apply_stripe_event(
        kind: str, obj: dict[str, Any]
    ) -> None:
        """Map the supported event types onto ``users`` columns."""
        from leadgen.integrations.stripe_client import plan_for_price

        settings = get_settings()
        # ``checkout.session.completed`` is where we first learn the
        # user-id (we passed it as ``client_reference_id``) AND the
        # customer id; bind them so subsequent subscription events can
        # find the user from ``customer`` alone.
        if kind == "checkout.session.completed":
            user_id_str = obj.get("client_reference_id")
            customer = obj.get("customer")
            if not user_id_str or not customer:
                return
            try:
                user_id = int(user_id_str)
            except ValueError:
                return
            async with session_factory() as session:
                await session.execute(
                    update(User)
                    .where(User.id == user_id)
                    .values(stripe_customer_id=customer)
                )
                await session.commit()
            return

        if kind in (
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
            "invoice.payment_succeeded",
            "invoice.payment_failed",
        ):
            customer = obj.get("customer")
            if not customer:
                return
            # Subscription objects carry items[].price.id directly;
            # invoice objects nest the same under ``lines.data``. We
            # accept either shape so a single handler works for both.
            price_id: str | None = None
            items = (obj.get("items") or {}).get("data") or []
            if items:
                price_id = (items[0].get("price") or {}).get("id")
            if price_id is None:
                lines = (obj.get("lines") or {}).get("data") or []
                if lines:
                    price_id = (lines[0].get("price") or {}).get("id")
            current_period_end = (
                obj.get("current_period_end") or obj.get("period_end")
            )
            status_value = obj.get("status") or ""

            new_plan = plan_for_price(
                price_id,
                pro_price_id=settings.stripe_price_id_pro,
                agency_price_id=settings.stripe_price_id_agency,
            )
            if kind == "customer.subscription.deleted" or status_value in (
                "canceled",
                "unpaid",
            ):
                new_plan = "free"
                plan_until = None
            else:
                plan_until = (
                    datetime.fromtimestamp(
                        int(current_period_end), tz=timezone.utc
                    )
                    if current_period_end
                    else None
                )

            async with session_factory() as session:
                await session.execute(
                    update(User)
                    .where(User.stripe_customer_id == customer)
                    .values(plan=new_plan, plan_until=plan_until)
                )
                await session.commit()

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

    # ── /api/v1/affiliate (per-user partner dashboard) ─────────────────

    @app.get("/api/v1/affiliate", response_model=AffiliateOverview)
    async def get_affiliate_overview(
        current_user: User = Depends(get_current_user),
    ) -> AffiliateOverview:
        async with session_factory() as session:
            codes = list(
                (
                    await session.execute(
                        select(AffiliateCode)
                        .where(AffiliateCode.owner_user_id == current_user.id)
                        .order_by(AffiliateCode.created_at.asc())
                    )
                )
                .scalars()
                .all()
            )
            counts: dict[str, tuple[int, int]] = {c.code: (0, 0) for c in codes}
            if codes:
                rows = (
                    await session.execute(
                        select(
                            Referral.code,
                            func.count(Referral.id),
                            func.count(Referral.first_paid_at),
                        )
                        .where(
                            Referral.code.in_([c.code for c in codes])
                        )
                        .group_by(Referral.code)
                    )
                ).all()
                for code, total, paid in rows:
                    counts[code] = (int(total or 0), int(paid or 0))

        items = [
            AffiliateCodeSchema(
                code=c.code,
                name=c.name,
                percent_share=c.percent_share,
                active=c.active,
                created_at=c.created_at,
                referrals_count=counts.get(c.code, (0, 0))[0],
                paid_referrals_count=counts.get(c.code, (0, 0))[1],
            )
            for c in codes
        ]
        return AffiliateOverview(
            codes=items,
            total_referrals=sum(i.referrals_count for i in items),
            total_paid_referrals=sum(i.paid_referrals_count for i in items),
        )

    @app.post(
        "/api/v1/affiliate/codes", response_model=AffiliateCodeSchema
    )
    async def create_affiliate_code(
        body: AffiliateCodeCreateRequest,
        current_user: User = Depends(get_current_user),
    ) -> AffiliateCodeSchema:
        """Create or claim an affiliate slug.

        Empty ``code`` → generate ~8-char URL-safe random slug. Caller-
        chosen slugs are normalised lowercase + restricted to
        ``[a-z0-9_-]`` so the public ``/r/{code}`` URL stays clean.
        """
        raw = (body.code or "").strip().lower()
        if raw:
            cleaned = "".join(
                ch for ch in raw if ch.isalnum() or ch in "-_"
            )
            if len(cleaned) < 3:
                raise HTTPException(
                    status_code=400,
                    detail="code must be at least 3 alphanumeric chars",
                )
            slug = cleaned[:64]
        else:
            slug = secrets.token_urlsafe(6).lower().replace("_", "").replace("-", "")[:8]
            if len(slug) < 3:
                slug = secrets.token_hex(4)
        async with session_factory() as session:
            existing = await session.get(AffiliateCode, slug)
            if existing is not None:
                raise HTTPException(
                    status_code=409, detail="this code is already taken"
                )
            row = AffiliateCode(
                code=slug,
                owner_user_id=current_user.id,
                name=(body.name or "").strip() or None,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
        return AffiliateCodeSchema(
            code=row.code,
            name=row.name,
            percent_share=row.percent_share,
            active=row.active,
            created_at=row.created_at,
        )

    @app.patch(
        "/api/v1/affiliate/codes/{code}",
        response_model=AffiliateCodeSchema,
    )
    async def update_affiliate_code(
        code: str,
        body: AffiliateCodeUpdate,
        current_user: User = Depends(get_current_user),
    ) -> AffiliateCodeSchema:
        async with session_factory() as session:
            row = await session.get(AffiliateCode, code.lower())
            if row is None or row.owner_user_id != current_user.id:
                raise HTTPException(status_code=404, detail="code not found")
            if body.name is not None:
                row.name = body.name.strip() or None
            if body.active is not None:
                row.active = bool(body.active)
            await session.commit()
            await session.refresh(row)
        return AffiliateCodeSchema(
            code=row.code,
            name=row.name,
            percent_share=row.percent_share,
            active=row.active,
            created_at=row.created_at,
        )

    @app.delete("/api/v1/affiliate/codes/{code}")
    async def delete_affiliate_code(
        code: str,
        current_user: User = Depends(get_current_user),
    ) -> dict[str, bool]:
        async with session_factory() as session:
            row = await session.get(AffiliateCode, code.lower())
            if row is None or row.owner_user_id != current_user.id:
                raise HTTPException(status_code=404, detail="code not found")
            await session.delete(row)
            await session.commit()
        return {"ok": True}

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
            owned = list(
                (
                    await session.execute(
                        select(LeadStatus).where(
                            LeadStatus.team_id == team_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            by_id = {s.id: s for s in owned}
            for index, sid in enumerate(body.ordered_ids):
                row = by_id.get(sid)
                if row is not None:
                    row.order_index = index
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


def _status_to_schema(row: LeadStatus) -> LeadStatusSchema:
    return LeadStatusSchema(
        id=row.id,
        key=row.key,
        label=row.label,
        color=row.color,
        order_index=row.order_index,
        is_terminal=row.is_terminal,
    )


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


async def _can_manage_tag(session, tag: LeadTag, user_id: int) -> bool:
    """Personal tags belong to one user; team tags need membership."""
    if tag.team_id is None:
        return tag.user_id == user_id
    return (await _membership(session, tag.team_id, user_id)) is not None


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
        onboarded=_is_onboarded(user),
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
