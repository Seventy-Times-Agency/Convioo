"""``/api/v1/auth/*`` and ``/api/v1/api-keys`` — authentication.

Email + password sign-up / login, email verification, password reset,
forgot-email recovery, session listing/revocation, recovery email,
API key issuance.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import func, select, update
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
from leadgen.adapters.web_api.routes._helpers import (
    hash_password,
    is_onboarded,
    issue_and_send_verification,
    record_audit,
    to_profile,
    verify_password,
)
from leadgen.adapters.web_api.schemas import (
    ApiKeyCreatedResponse,
    ApiKeyCreateRequest,
    ApiKeyListResponse,
    ApiKeySchema,
    AuthUser,
    ForgotEmailRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutAllResponse,
    RecoveryEmailUpdate,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SessionInfo,
    SessionListResponse,
    UserProfile,
    VerifyEmailRequest,
)
from leadgen.config import get_settings
from leadgen.core.services import (
    mask_email,
    render_account_locked_email,
    render_email_changed_alert,
    render_email_recovery_email,
    render_new_device_login_email,
    render_password_changed_email,
    render_password_reset_email,
    send_email,
)
from leadgen.db.models import (
    AffiliateCode,
    EmailVerificationToken,
    Referral,
    User,
    UserApiKey,
    UserSession,
)
from leadgen.db.session import session_factory
from leadgen.utils.rate_limit import (
    forgot_email_limiter,
    forgot_password_limiter,
    login_limiter,
    register_limiter,
    resend_verification_limiter,
    reset_password_limiter,
)

router = APIRouter(tags=["auth"])


@router.post("/api/v1/auth/register", response_model=AuthUser)
async def register(
    body: RegisterRequest, request: Request, response: Response
) -> AuthUser:
    """Sign up with email + password + first/last name (+ optional age)."""
    ip = request_ip(request)
    enforce_rate_limit(register_limiter, f"ip:{ip or '?'}", retry_hint=3600)

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

    password_hash = hash_password(body.password)
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

        await issue_and_send_verification(session, user)
        await record_audit(
            session,
            user_id=user.id,
            action="auth.register",
            request=request,
            payload={"email": email},
        )
        token, _sess = await create_session(
            session, user_id=user.id, request=request
        )

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


@router.post("/api/v1/auth/login", response_model=AuthUser)
async def login(
    body: LoginRequest, request: Request, response: Response
) -> AuthUser:
    """Email + password login. Issues an httpOnly session cookie."""
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
            raise invalid

        if is_locked(user):
            await record_audit(
                session,
                user_id=user.id,
                action="auth.login_locked",
                request=request,
            )
            await session.commit()
            raise invalid

        if not verify_password(body.password, user.password_hash):
            just_locked = record_failed_login(user)
            await record_audit(
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

        clear_failed_logins(user)
        ua = request_user_agent(request)
        fingerprint = device_fingerprint(ip, ua)
        new_device = not await is_known_device(
            session, user_id=user.id, fingerprint=fingerprint
        )
        token, _sess = await create_session(
            session, user_id=user.id, request=request
        )
        await record_audit(
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
            onboarded=is_onboarded(user),
        )


@router.post("/api/v1/auth/verify-email", response_model=AuthUser)
async def verify_email(body: VerifyEmailRequest) -> AuthUser:
    """Confirm a pending email-verification token."""
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

        if already_used and not expired:
            if token_row.kind == "verify" and user.email_verified_at is not None:
                return AuthUser(
                    user_id=user.id,
                    first_name=user.first_name or "",
                    last_name=user.last_name or "",
                    email=user.email,
                    email_verified=True,
                    onboarded=is_onboarded(user),
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
                    onboarded=is_onboarded(user),
                )

        if already_used:
            raise HTTPException(status_code=410, detail="token already used")
        if expired:
            raise HTTPException(status_code=410, detail="token expired")

        token_row.used_at = now
        old_email: str | None = None
        email_actually_changed = False
        if token_row.kind == "change_email" and token_row.pending_email:
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
            await revoke_all_sessions(session, user_id=user.id)
        elif user.email_verified_at is None:
            user.email_verified_at = now
        await session.commit()

        if email_actually_changed and old_email:
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
            onboarded=is_onboarded(user),
        )


@router.post("/api/v1/auth/resend-verification")
async def resend_verification(
    body: ResendVerificationRequest, request: Request
) -> dict[str, bool]:
    """Resend the verification email for a not-yet-verified account."""
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
            await issue_and_send_verification(session, user)
    return {"sent": True}


@router.post("/api/v1/auth/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest, request: Request
) -> dict[str, bool]:
    """Mint a 1-hour password-reset link and email it."""
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
            await record_audit(
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


@router.post("/api/v1/auth/reset-password", response_model=AuthUser)
async def reset_password(
    body: ResetPasswordRequest, request: Request, response: Response
) -> AuthUser:
    """Consume a password-reset token and set the new password."""
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
        user.password_hash = hash_password(body.new_password)
        clear_failed_logins(user)
        await revoke_all_sessions(session, user_id=user.id)
        new_token, _sess = await create_session(
            session, user_id=user.id, request=request
        )
        await record_audit(
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
        onboarded=is_onboarded(user),
    )


@router.post("/api/v1/auth/forgot-email")
async def forgot_email(
    body: ForgotEmailRequest, request: Request
) -> dict[str, bool]:
    """Help a user remember which email their account is on."""
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
            session.add(
                EmailVerificationToken(
                    user_id=user.id,
                    kind="email_recovery",
                    token=token,
                    pending_email=user.recovery_email,
                    expires_at=expires,
                )
            )
            await record_audit(
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


@router.post("/api/v1/auth/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    sid = current_session_id(request)
    async with session_factory() as session:
        if sid is not None:
            await revoke_session(session, sid)
            await record_audit(
                session,
                user_id=current_user.id,
                action="auth.logout",
                request=request,
            )
            await session.commit()
    clear_session_cookie(response, request=request)
    return {"ok": True}


@router.post("/api/v1/auth/logout-all", response_model=LogoutAllResponse)
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
        await record_audit(
            session,
            user_id=current_user.id,
            action="auth.logout_all",
            request=request,
            payload={"revoked": count},
        )
        await session.commit()
    return LogoutAllResponse(revoked=int(count))


@router.get("/api/v1/auth/me", response_model=AuthUser)
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
        onboarded=is_onboarded(current_user),
        onboarding_tour_completed=current_user.onboarding_completed_at
        is not None,
    )


@router.patch("/api/v1/users/me/onboarding-complete", response_model=AuthUser)
async def complete_onboarding_tour(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> AuthUser:
    """Stamp the moment the user finishes (or skips) the product tour."""
    async with session_factory() as session:
        user = await session.get(User, current_user.id)
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")
        if user.onboarding_completed_at is None:
            user.onboarding_completed_at = datetime.now(timezone.utc)
            await record_audit(
                session,
                user_id=user.id,
                action="onboarding.tour_completed",
                request=request,
            )
            await session.commit()
        return AuthUser(
            user_id=user.id,
            first_name=user.first_name or "",
            last_name=user.last_name or "",
            email=user.email,
            email_verified=user.email_verified_at is not None,
            onboarded=is_onboarded(user),
            onboarding_tour_completed=user.onboarding_completed_at
            is not None,
        )


@router.get("/api/v1/auth/sessions", response_model=SessionListResponse)
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


@router.delete("/api/v1/auth/sessions/{session_id}")
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
        await record_audit(
            session,
            user_id=current_user.id,
            action="auth.session_revoked",
            request=request,
            payload={"session_id": str(session_id)},
        )
        await session.commit()
    if sid == session_id:
        clear_session_cookie(response, request=request)
    return {"ok": True}


@router.patch("/api/v1/auth/recovery-email", response_model=UserProfile)
async def update_recovery_email(
    body: RecoveryEmailUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> UserProfile:
    """Set or clear the optional secondary mailbox."""
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
        await record_audit(
            session,
            user_id=user.id,
            action="auth.recovery_email_set" if new_value else "auth.recovery_email_cleared",
            request=request,
        )
        await session.commit()
        await session.refresh(user)
        return to_profile(user)


# ── /api/v1/auth/api-keys (issue / revoke bearer tokens) ───────────


@router.get("/api/v1/auth/api-keys", response_model=ApiKeyListResponse)
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


@router.post(
    "/api/v1/auth/api-keys", response_model=ApiKeyCreatedResponse
)
async def create_api_key(
    body: ApiKeyCreateRequest,
    current_user: User = Depends(get_current_user),
) -> ApiKeyCreatedResponse:
    """Mint a new long-lived bearer token for this user."""
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


@router.delete("/api/v1/auth/api-keys/{key_id}")
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


# ── /api/v1/api-keys (canonical alias of /auth/api-keys) ───────────


@router.get("/api/v1/api-keys", response_model=ApiKeyListResponse)
async def list_api_keys_alias(
    current_user: User = Depends(get_current_user),
) -> ApiKeyListResponse:
    return await list_api_keys(current_user=current_user)


@router.post("/api/v1/api-keys", response_model=ApiKeyCreatedResponse)
async def create_api_key_alias(
    body: ApiKeyCreateRequest,
    current_user: User = Depends(get_current_user),
) -> ApiKeyCreatedResponse:
    return await create_api_key(body=body, current_user=current_user)


@router.delete("/api/v1/api-keys/{key_id}")
async def revoke_api_key_alias(
    key_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    return await revoke_api_key(
        key_id=key_id, current_user=current_user
    )
