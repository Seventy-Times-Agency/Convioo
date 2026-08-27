"""``/api/v1/users/me/*`` — profile, audit log, GDPR export, deletion."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from leadgen.adapters.web_api.auth import (
    current_session_id,
    get_current_user,
    request_ip,
    request_user_agent,
    revoke_all_sessions,
)
from leadgen.adapters.web_api.routes._helpers import (
    hash_password,
    is_onboarded,
    issue_and_send_change_email,
    record_audit,
    to_profile,
    verify_password,
)
from leadgen.adapters.web_api.schemas import (
    AccountDeleteRequest,
    AccountDeleteResponse,
    AuditLogEntry,
    AuditLogListResponse,
    AuthUser,
    ChangeEmailRequest,
    ChangePasswordRequest,
    UserProfile,
    UserProfileUpdate,
)
from leadgen.analysis.ai_analyzer import AIAnalyzer
from leadgen.core.services import (
    render_password_changed_email,
    send_email,
)
from leadgen.db.models import (
    AssistantMemory,
    Lead,
    LeadActivity,
    LeadCustomField,
    LeadMark,
    LeadTask,
    OutreachTemplate,
    SearchQuery,
    User,
    UserAuditLog,
)
from leadgen.db.session import session_factory
from leadgen.utils.locale_text import SUPPORTED_LANGS, normalize_lang, pick

logger = logging.getLogger(__name__)

router = APIRouter(tags=["users"])


@router.get("/api/v1/users/me", response_model=UserProfile)
async def get_user_me(
    current_user: User = Depends(get_current_user),
) -> UserProfile:
    async with session_factory() as session:
        user = await session.get(User, current_user.id)
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")
        return to_profile(user)


async def _update_user_impl(
    user_id: int, body: UserProfileUpdate
) -> UserProfile:
    """Update onboarding profile."""
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
            code = (data["language_code"] or "").strip().lower() or None
            if code is not None and code not in SUPPORTED_LANGS:
                raise HTTPException(
                    status_code=400,
                    detail="language_code must be one of: ru, uk, en",
                )
            user.language_code = code
        if "calendly_url" in data:
            url = (data["calendly_url"] or "").strip() or None
            user.calendly_url = url
        if "niches" in data:
            cleaned = [
                n.strip() for n in (data["niches"] or []) if isinstance(n, str) and n.strip()
            ]
            user.niches = cleaned or None
        if "service_description" in data:
            raw = (data["service_description"] or "").strip()
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
                        "normalize_profession failed/timed out; storing raw text"
                    )
                    user.profession = raw
            else:
                user.service_description = None
                user.profession = None

        if user.onboarded_at is None and (
            user.display_name or user.first_name
        ):
            user.onboarded_at = datetime.now(timezone.utc)

        await session.commit()
        await session.refresh(user)
        return to_profile(user)


@router.patch("/api/v1/users/me", response_model=UserProfile)
async def update_user_me(
    body: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
) -> UserProfile:
    return await _update_user_impl(current_user.id, body)


@router.post("/api/v1/users/me/change-email", response_model=AuthUser)
async def change_email(
    body: ChangeEmailRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> AuthUser:
    """Initiate an email change."""
    user_id = current_user.id
    new_email = body.new_email.strip().lower()
    if "@" not in new_email or "." not in new_email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="invalid email")

    async with session_factory() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")
        if not user.password_hash or not verify_password(
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

        await issue_and_send_change_email(session, user, new_email)
        await record_audit(
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
        onboarded=is_onboarded(user),
    )


@router.post("/api/v1/users/me/change-password", response_model=AuthUser)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> AuthUser:
    """Update the password. Requires the current one."""
    user_id = current_user.id
    async with session_factory() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")
        if not user.password_hash or not verify_password(
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
        user.password_hash = hash_password(body.new_password)
        await revoke_all_sessions(
            session,
            user_id=user.id,
            except_session_id=current_session_id(request),
        )
        await record_audit(
            session,
            user_id=user.id,
            action="auth.password_changed",
            request=request,
        )
        await session.commit()

    if user.email:
        lang = normalize_lang(user.language_code)
        html, text = render_password_changed_email(
            name=user.first_name or user.display_name or "",
            ip=request_ip(request),
            user_agent=request_user_agent(request),
            when_iso=datetime.now(timezone.utc).isoformat(),
            lang=lang,
        )
        await send_email(
            to=user.email,
            subject=pick(
                lang,
                ru="Пароль изменён — Convioo",
                uk="Пароль змінено — Convioo",
                en="Password changed — Convioo",
            ),
            html=html,
            text=text,
        )

    return AuthUser(
        user_id=user.id,
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        email=user.email,
        email_verified=user.email_verified_at is not None,
        onboarded=is_onboarded(user),
    )


# ── /api/v1/users/{id}/gdpr ───────────────────────────────────────


@router.get(
    "/api/v1/users/me/audit-log", response_model=AuditLogListResponse
)
async def list_audit_log(
    current_user: User = Depends(get_current_user),
) -> AuditLogListResponse:
    """Return the most recent 200 audit-log entries for the user."""
    user_id = current_user.id
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


@router.get("/api/v1/users/me/export")
async def gdpr_export(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> JSONResponse:
    """Download a JSON dump of everything we store about this user."""
    user_id = current_user.id
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
        session_ids = [s.id for s in sessions]
        if session_ids:
            leads = list(
                (
                    await session.execute(
                        select(Lead).where(Lead.query_id.in_(session_ids))
                    )
                ).scalars()
            )
        else:
            leads = []
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

        await record_audit(
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


@router.post("/api/v1/users/me/icp-profile")
async def upload_icp_profile(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Upload a CSV of best clients → Claude extracts ICP → stored on user profile."""
    from leadgen.core.services.icp_analyzer import analyze_client_csv  # noqa: PLC0415

    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted")

    content = await file.read()
    try:
        csv_text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        csv_text = content.decode("latin-1")

    try:
        icp = await analyze_client_csv(csv_text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    async with session_factory() as session:
        user = await session.get(User, current_user.id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        user.icp_profile = icp
        await session.commit()

    return {"icp_profile": icp}


@router.get("/api/v1/users/me/icp-profile")
async def get_icp_profile(
    current_user: User = Depends(get_current_user),
) -> dict:
    return {"icp_profile": current_user.icp_profile}


@router.delete(
    "/api/v1/users/me",
    response_model=AccountDeleteResponse,
)
async def delete_account(
    body: AccountDeleteRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> AccountDeleteResponse:
    """Hard-delete a user account."""
    user_id = current_user.id
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
            or not verify_password(body.password, user.password_hash)
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
