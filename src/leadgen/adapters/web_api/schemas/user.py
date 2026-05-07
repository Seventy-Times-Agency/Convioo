"""User profile and notification schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    """Full personalisation profile that feeds Claude during analysis.

    Mirrors the fields the Telegram bot collects in its 6-step
    onboarding so web searches reach the same prompt quality.
    """

    user_id: int
    first_name: str
    last_name: str
    display_name: str | None
    age_range: str | None
    gender: str | None
    business_size: str | None
    profession: str | None
    service_description: str | None
    home_region: str | None
    niches: list[str] | None
    language_code: str | None
    calendly_url: str | None = None
    onboarded: bool
    onboarding_tour_completed: bool = False
    email: str | None = None
    email_verified: bool = False
    # Optional secondary mailbox the user trusts to always reach them.
    # Used by the forgot-email recovery flow. Only the masked form is
    # exposed back to the SPA so an XSS leak doesn't yield the address.
    recovery_email_masked: str | None = None
    # Search quota — surfaced on the dashboard as a progress bar so
    # users see how close they are to the limit before they hit it.
    queries_used: int = 0
    queries_limit: int = 0


class UserProfileUpdate(BaseModel):
    """PATCH payload for /api/v1/users/{id}. All fields optional.

    Sending ``service_description`` triggers a Claude normalisation pass
    on the server so ``profession`` ends up clean and short, matching
    what the Telegram bot stores.
    """

    display_name: str | None = Field(default=None, max_length=128)
    age_range: str | None = Field(default=None, max_length=16)
    gender: str | None = Field(default=None, max_length=16)
    business_size: str | None = Field(default=None, max_length=32)
    # Cap at 800 chars — Pydantic rejects with a clear 422 if the user
    # bypasses the frontend counter, and the DB column is now TEXT
    # (migration 0017) so there's no silent overflow at the SQL layer.
    service_description: str | None = Field(default=None, max_length=800)
    home_region: str | None = Field(default=None, max_length=200)
    niches: list[str] | None = Field(default=None, max_length=20)
    language_code: str | None = Field(default=None, max_length=8)
    calendly_url: str | None = Field(default=None, max_length=500)


class NotificationPrefsResponse(BaseModel):
    daily_digest_enabled: bool
    email_reply_tracking_enabled: bool
    email_reply_last_checked_at: datetime | None = None


class NotificationPrefsUpdate(BaseModel):
    daily_digest_enabled: bool | None = None
    email_reply_tracking_enabled: bool | None = None
