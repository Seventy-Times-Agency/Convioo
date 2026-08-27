"""Daily lead-volume caps by tariff plan.

The legacy ``BillingService`` gates *number of searches per month* —
useful, but it doesn't stop a single power user from running 50
back-to-back searches in an hour and burning $30 of API spend before
anyone notices. This module adds the second predicate: a rolling
24-hour cap on *leads delivered* keyed off the user's plan.

Why daily not monthly here:
    Variable cost (Google Places + Claude) is per-lead, so the unit
    that ought to be metered is leads. A plan that allows 9 000
    leads/month must still cap a single day around 300 — without that
    a 5 000-lead morning blows through the entire month's budget.

Why rolling not midnight-bucketed:
    Bucketed limits are abusable: 500 leads at 23:59 + 500 at 00:01
    is "two days" by the calendar but one continuous burst by cost.
    A trailing-24h window is what the API spend actually tracks.

Storage reuses ``leadgen.utils.cache`` so we don't add another
backend dependency. Counters are written under namespace ``daily``
keyed by ``(subject, day_bucket)`` — multiple buckets summed across
the trailing 24h give the rolling count.

**Subject = user OR team.** When a user runs a personal search the
subject is their ``user_id``. When a team owner / member runs a
team-mode search the subject becomes ``team:{team_id}`` so the
whole workspace shares one quota bucket — that's how a 5-seat
agency on the Team plan splits 300 leads/day across teammates
instead of each seat getting their own. The team's ``plan`` column
drives the cap, not the individual member's.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from leadgen.utils import cache as _cache

logger = logging.getLogger(__name__)


# Source-of-truth for plan → daily lead cap. The numbers line up with
# the pricing tiers we floated to the user (Solo / Agency / Power).
# ``free`` is the unauth / trial floor — generous enough to feel the
# product, tight enough to not be exploitable.
PLAN_DAILY_LEAD_CAP: dict[str, int] = {
    "free": 50,
    "trial": 100,
    "solo": 100,
    "agency": 300,
    "pro": 300,  # legacy alias
    "power": 500,
    "unlimited": 25_000,  # fair-use ceiling, not "really" unlimited
}

# Counters live for ~48h so the rolling 24h sum always has tomorrow's
# bucket worth of headroom even with timezone wiggle.
_BUCKET_TTL_SEC = 48 * 60 * 60

# We bucket per-hour so the rolling window has 24 slices instead of a
# single coarse "today" — sliding the window past midnight is then
# accurate to the hour without chunky cliff effects.
_BUCKET_GRANULARITY_HOURS = 1


@dataclass(slots=True)
class TariffVerdict:
    allowed: bool
    plan: str
    used_24h: int
    cap_24h: int
    requested: int

    @property
    def remaining(self) -> int:
        return max(0, self.cap_24h - self.used_24h)


def cap_for_plan(plan: str | None) -> int:
    """Look up a plan's daily cap, falling back to ``free``."""
    if not plan:
        return PLAN_DAILY_LEAD_CAP["free"]
    return PLAN_DAILY_LEAD_CAP.get(plan.lower(), PLAN_DAILY_LEAD_CAP["free"])


def _subject_key(*, user_id: int | str | None, team_id: str | None) -> str:
    """Return the cache-namespace key for a quota subject.

    Team mode wins when both are set — a team-mode search counts
    against the workspace bucket, not the individual member's. The
    ``team:`` prefix keeps team buckets in their own namespace so
    pre-existing user counters don't double-count when a user joins
    a team.
    """
    if team_id:
        return f"team:{team_id}"
    return str(user_id) if user_id is not None else "anon"


def _bucket_keys(subject: str) -> list[str]:
    """Return the 24 hourly bucket keys covering the trailing 24h."""
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    keys = []
    for i in range(24 // _BUCKET_GRANULARITY_HOURS):
        slot = now.fromtimestamp(
            now.timestamp() - i * _BUCKET_GRANULARITY_HOURS * 3600,
            tz=timezone.utc,
        )
        keys.append(f"{subject}:{slot.strftime('%Y%m%d%H')}")
    return keys


def _current_bucket_key(subject: str) -> str:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return f"{subject}:{now.strftime('%Y%m%d%H')}"


async def _sum_window(subject: str) -> int:
    total = 0
    for key in _bucket_keys(subject):
        try:
            value = await _cache.get_json("daily", key)
        except Exception as exc:  # noqa: BLE001 — telemetry must not raise
            logger.debug("tariff_limits: get failed key=%s err=%s", key, exc)
            value = None
        if isinstance(value, (int, float)):
            total += int(value)
    return total


async def check_daily_lead_quota(
    user_id: int | str,
    plan: str | None,
    *,
    requested: int = 0,
    is_admin: bool = False,
    team_id: str | None = None,
) -> TariffVerdict:
    """Return a verdict for a planned ``requested``-lead operation.

    Pass ``requested=0`` for a pure read (e.g. show "X / Y left
    today" in the UI) — the verdict's ``allowed`` flag still answers
    "can the user run *anything* right now?".

    Platform admins (``users.is_admin = true``) bypass the cap so the
    operator account can run as many searches as it wants for testing,
    demos, or backfills. We still record actual usage for telemetry —
    the bypass only flips ``allowed`` to ``True`` regardless of headroom.

    Pass ``team_id`` (and the team's ``plan``) for a team-mode search:
    the bucket then aggregates across all teammates, and the verdict's
    plan label is reported as the team's plan so the UI can render
    "Team plan, 240/300 today" instead of the member's personal cap.
    """
    cap = cap_for_plan(plan)
    subject = _subject_key(user_id=user_id, team_id=team_id)
    used = await _sum_window(subject)
    if is_admin:
        return TariffVerdict(
            allowed=True,
            plan="admin",
            used_24h=used,
            cap_24h=max(cap, used + max(0, requested)),
            requested=requested,
        )
    fits = used + max(0, requested) <= cap
    return TariffVerdict(
        allowed=fits,
        plan=(plan or "free").lower(),
        used_24h=used,
        cap_24h=cap,
        requested=requested,
    )


async def record_lead_usage(
    user_id: int | str,
    count: int,
    *,
    team_id: str | None = None,
) -> None:
    """Bump the current hour bucket by ``count`` leads.

    Called after a search completes — we count what was actually
    delivered, not what was requested, so partial-result searches
    don't over-charge the user's daily window. ``team_id`` switches
    the counter to the workspace bucket (mirrors
    :func:`check_daily_lead_quota`).
    """
    if count <= 0:
        return
    subject = _subject_key(user_id=user_id, team_id=team_id)
    key = _current_bucket_key(subject)
    try:
        existing = await _cache.get_json("daily", key)
        current = int(existing) if isinstance(existing, (int, float)) else 0
        await _cache.set_json("daily", key, current + count, _BUCKET_TTL_SEC)
    except Exception as exc:  # noqa: BLE001
        logger.debug("tariff_limits: record failed key=%s err=%s", key, exc)
