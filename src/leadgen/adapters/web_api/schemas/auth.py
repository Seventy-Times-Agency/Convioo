"""Auth-related request / response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RegisterRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=128)
    last_name: str = Field(..., min_length=1, max_length=128)
    email: str = Field(..., min_length=4, max_length=255)
    password: str = Field(..., min_length=8, max_length=200)
    age_range: str | None = Field(default=None, max_length=16)
    gender: str | None = Field(default=None, max_length=16)
    # Invite code. When REGISTRATION_PASSWORD env var is set on the
    # server, this MUST match — otherwise registration is rejected.
    # Lets the founder keep the public-facing site closed while still
    # demoing the product to invited people.
    registration_password: str | None = Field(default=None, max_length=200)
    # Affiliate / referral attribution. SPA reads it from the
    # ``convioo_ref`` cookie set by the public ``/r/{code}`` landing
    # page and forwards it here. Unknown / inactive codes are
    # silently ignored — never blocks registration.
    referral_code: str | None = Field(default=None, max_length=64)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=4, max_length=255)
    password: str = Field(..., min_length=1, max_length=200)


class VerifyEmailRequest(BaseModel):
    token: str = Field(..., min_length=8, max_length=128)


class ResendVerificationRequest(BaseModel):
    email: str = Field(..., min_length=4, max_length=255)


class ChangeEmailRequest(BaseModel):
    """Initiate an email change. Requires the current password to
    confirm the request actually came from the signed-in user."""

    new_email: str = Field(..., min_length=4, max_length=255)
    password: str = Field(..., min_length=1, max_length=200)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=200)
    new_password: str = Field(..., min_length=8, max_length=200)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., min_length=4, max_length=255)


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=8, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=200)


class ForgotEmailRequest(BaseModel):
    """Request a recovery email pointing back at the registered address."""

    recovery_email: str = Field(..., min_length=4, max_length=255)


class RecoveryEmailUpdate(BaseModel):
    """Set or clear the recovery email on the signed-in account."""

    recovery_email: str | None = Field(default=None, max_length=255)


class SessionInfo(BaseModel):
    id: uuid.UUID
    ip: str | None = None
    user_agent: str | None = None
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    current: bool = False


class SessionListResponse(BaseModel):
    sessions: list[SessionInfo]
    count: int


class LogoutAllResponse(BaseModel):
    revoked: int


class AuthUser(BaseModel):
    """Trimmed user payload returned to the SPA after register/login.

    The session JWT is set as an httpOnly cookie by the backend. The
    JSON payload only carries the data the SPA needs to render: who
    the user is, whether their email is verified (gates search
    creation), and whether they finished onboarding.
    """

    user_id: int
    first_name: str
    last_name: str
    email: str | None = None
    email_verified: bool = False
    onboarded: bool = False
    # True once the user has finished or skipped the in-app product
    # tour. The SPA reads this to decide whether to auto-open the tour
    # on the next /app visit.
    onboarding_tour_completed: bool = False


class AccountDeleteRequest(BaseModel):
    """Confirmation payload for account deletion.

    The user types their email into the modal; we compare against the
    stored value before purging anything.
    """

    confirm_email: str = Field(..., min_length=3, max_length=320)
    password: str | None = Field(default=None, max_length=200)


class AccountDeleteResponse(BaseModel):
    deleted: bool


class AuditLogEntry(BaseModel):
    """Single row from ``user_audit_logs`` for the profile page."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action: str
    ip: str | None = None
    user_agent: str | None = None
    payload: dict | None = None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogEntry]
