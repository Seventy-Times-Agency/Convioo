"""Quota / billing operations: the one place that mutates ``queries_used``.

Keeps atomicity and racy-counter prevention in a single spot so the bot
adapter, the future web API and any batch job all go through the same
path. Extending this to paid tiers, Stripe events or per-team quotas
becomes a change in one file.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.config import get_settings
from leadgen.db.models import User


def _is_paid_or_trialing(user: User, *, now: datetime | None = None) -> bool:
    """True when the user has either an active paid plan or an open trial."""
    moment = now or datetime.now(timezone.utc)
    plan_until = user.plan_until
    trial_ends = user.trial_ends_at
    if plan_until is not None:
        if plan_until.tzinfo is None:
            plan_until = plan_until.replace(tzinfo=timezone.utc)
        if user.plan and user.plan != "free" and plan_until > moment:
            return True
    if trial_ends is not None:
        if trial_ends.tzinfo is None:
            trial_ends = trial_ends.replace(tzinfo=timezone.utc)
        if trial_ends > moment:
            return True
    return False


class QuotaVerdict(StrEnum):
    ALLOWED = "allowed"
    EXHAUSTED = "exhausted"


@dataclass(slots=True)
class QuotaCheck:
    verdict: QuotaVerdict
    queries_used: int
    queries_limit: int

    @property
    def allowed(self) -> bool:
        return self.verdict == QuotaVerdict.ALLOWED

    @property
    def remaining(self) -> int:
        return max(0, self.queries_limit - self.queries_used)


class BillingError(RuntimeError):
    """Raised for unexpected billing/quota failures."""


class BillingService:
    """Atomic, race-safe operations on a user's search quota.

    The session lifecycle is owned by the caller — the service just
    issues SQL. This keeps unit tests simple (pass a test session) and
    lets adapters wrap several service calls in one transaction when
    they need to.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def try_consume(self, user_id: int) -> QuotaCheck:
        """Atomically consume one search credit if the user has headroom.

        Uses ``UPDATE ... WHERE queries_used < limit RETURNING`` so two
        concurrent callers can't both slip past a per-user limit. If the
        WHERE clause filters them out, nothing is updated and we report
        exhausted without mutating anything.

        When ``BILLING_ENFORCED=false`` (the default while we're iterating
        on the product internally), this short-circuits to always allow
        and still bumps the counter so analytics keeps working.
        """
        settings = get_settings()
        if not settings.billing_enforced:
            # Counter increments for usage telemetry; the verdict is
            # always ALLOWED so nobody gets blocked. Flip the env flag
            # to turn real gating back on.
            result = await self.session.execute(
                update(User)
                .where(User.id == user_id)
                .values(queries_used=User.queries_used + 1)
                .returning(User.queries_used, User.queries_limit)
            )
            row = result.first()
            if row is None:
                raise BillingError(f"user {user_id} not found")
            return QuotaCheck(
                verdict=QuotaVerdict.ALLOWED,
                queries_used=row[0],
                queries_limit=row[1],
            )

        # Active paid subscription or open trial bypasses the per-bucket
        # cap entirely — the cap exists for free-tier users only.
        user = await self.session.get(User, user_id)
        if user is None:
            raise BillingError(f"user {user_id} not found")
        if _is_paid_or_trialing(user):
            await self.session.execute(
                update(User)
                .where(User.id == user_id)
                .values(queries_used=User.queries_used + 1)
            )
            return QuotaCheck(
                verdict=QuotaVerdict.ALLOWED,
                queries_used=user.queries_used + 1,
                queries_limit=user.queries_limit,
            )

        result = await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .where(User.queries_used < User.queries_limit)
            .values(queries_used=User.queries_used + 1)
            .returning(User.queries_used, User.queries_limit)
        )
        row = result.first()
        if row is None:
            # WHERE clause filtered us out → user is at or over the limit.
            # Fetch the actual numbers so the caller can show them in the
            # "лимит исчерпан" copy.
            snapshot = await self.session.execute(
                select(User.queries_used, User.queries_limit).where(User.id == user_id)
            )
            srow = snapshot.first()
            used = srow[0] if srow else 0
            limit = srow[1] if srow else 0
            return QuotaCheck(
                verdict=QuotaVerdict.EXHAUSTED,
                queries_used=used,
                queries_limit=limit,
            )
        return QuotaCheck(
            verdict=QuotaVerdict.ALLOWED,
            queries_used=row[0],
            queries_limit=row[1],
        )

    async def refund(self, user_id: int) -> None:
        """Hand back a previously-consumed credit.

        Used when a follow-up step (e.g. creating the SearchQuery row)
        fails *after* ``try_consume`` already succeeded on its own
        transaction. When both live in a single transaction that rolls
        back together, no refund is needed.
        """
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .where(User.queries_used > 0)
            .values(queries_used=User.queries_used - 1)
        )

    async def snapshot(self, user_id: int) -> QuotaCheck:
        """Read-only view of the current quota state."""
        user = await self.session.get(User, user_id)
        if user is None:
            raise BillingError(f"user {user_id} not found")
        verdict = (
            QuotaVerdict.ALLOWED
            if user.queries_used < user.queries_limit
            else QuotaVerdict.EXHAUSTED
        )
        return QuotaCheck(
            verdict=verdict,
            queries_used=user.queries_used,
            queries_limit=user.queries_limit,
        )
