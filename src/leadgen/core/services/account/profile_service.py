"""Client-agnostic operations on a ``User``'s profile.

The Telegram onboarding handlers and the future web onboarding form
both go through this service so the rules live in one place:
- what a "complete" profile looks like (``is_onboarded``)
- which fields an AI parser touches vs. raw text
- how a profile gets wiped (``reset``)

Keeps handlers.py shorter and the web API one step from trivial.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.db.models import User


@dataclass(slots=True)
class ProfileUpdate:
    """Patch-style update: only fields present are applied."""

    display_name: str | None = None
    age_range: str | None = None
    business_size: str | None = None
    profession: str | None = None
    service_description: str | None = None
    home_region: str | None = None
    niches: list[str] | None = None

    def fields(self) -> dict[str, Any]:
        """Return only fields the caller explicitly set (non-None)."""
        out: dict[str, Any] = {}
        for name in (
            "display_name",
            "age_range",
            "business_size",
            "profession",
            "service_description",
            "home_region",
            "niches",
        ):
            value = getattr(self, name)
            if value is not None:
                out[name] = value
        return out


class ProfileService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def is_onboarded(user: User) -> bool:
        """Minimal bar for a usable profile: profession + at least one niche."""
        return (
            user.onboarded_at is not None
            and bool(user.profession)
            and bool(user.niches)
        )

    async def apply(self, user_id: int, patch: ProfileUpdate) -> User:
        """Apply a partial update and touch ``onboarded_at`` once the bar is met."""
        user = await self.session.get(User, user_id)
        if user is None:
            raise KeyError(f"user {user_id} not found")
        for key, value in patch.fields().items():
            setattr(user, key, value)
        # First time every required field is filled → stamp onboarded_at.
        # `is_onboarded` itself requires `onboarded_at is not None`, so we
        # check the prerequisites directly here to avoid circular logic.
        profile_complete = bool(user.profession) and bool(user.niches)
        if user.onboarded_at is None and profile_complete:
            user.onboarded_at = datetime.now(timezone.utc)
        await self.session.commit()
        return user

    async def reset(self, user_id: int) -> User:
        """Wipe every profile field so the user goes back through onboarding.

        The ``User`` row itself stays (id, username, Telegram identity,
        queries_used history) — only the content the user supplied is
        cleared. SearchQuery rows survive for analytics.
        """
        user = await self.session.get(User, user_id)
        if user is None:
            raise KeyError(f"user {user_id} not found")
        user.display_name = None
        user.age_range = None
        user.business_size = None
        user.profession = None
        user.service_description = None
        user.home_region = None
        user.niches = None
        user.onboarded_at = None
        await self.session.commit()
        return user
