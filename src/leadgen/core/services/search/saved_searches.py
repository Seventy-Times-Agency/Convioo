"""Schedule + dispatch logic for ``SavedSearch`` rows.

Two operations live here:

1. ``next_run_after(label, now)`` — turn a coarse recurrence label
   ("daily" / "weekly" / "biweekly" / "monthly") into a concrete UTC
   timestamp. Used both at save time (compute the first run) and at
   dispatch time (advance the cursor after a successful run).
2. ``dispatch_due(...)`` — find every active row with
   ``next_run_at <= now`` and enqueue a fresh ``SearchQuery`` per
   row. Idempotency is delegated to the existing search pipeline:
   the new query gets its own UUID so reruns can't clobber each other.

Both the arq worker (cron mode) and the inline-dev fallback in
``leadgen.adapters.web_api.app`` call ``dispatch_due`` — the
behavior is identical, only the scheduler differs.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.db.models import SavedSearch, SearchQuery

logger = logging.getLogger(__name__)


# Map of human-readable recurrence label to the gap until the next run.
# ``"off"`` is normalized to ``None`` upstream — we never reach this
# table with that key.
_INTERVALS: dict[str, timedelta] = {
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
    "biweekly": timedelta(days=14),
    "monthly": timedelta(days=30),
}

VALID_SCHEDULES = frozenset(_INTERVALS.keys())


def next_run_after(
    schedule: str | None, *, now: datetime | None = None
) -> datetime | None:
    """Return the next run timestamp for ``schedule`` after ``now``.

    Returns ``None`` for an unrecognized label so callers can treat
    that as "manual-run only" without an extra branch.
    """
    if not schedule or schedule not in _INTERVALS:
        return None
    moment = now or datetime.now(timezone.utc)
    return moment + _INTERVALS[schedule]


# Type for the search-runner callback — exposes a single hook that
# the worker / inline path implements differently. Returning the
# created ``SearchQuery.id`` keeps the dispatcher generic.
RunSearchFn = Callable[[SavedSearch, AsyncSession], Awaitable[uuid.UUID | None]]


async def dispatch_due(
    session: AsyncSession,
    *,
    run_search: RunSearchFn,
    now: datetime | None = None,
) -> int:
    """Run every saved search whose ``next_run_at`` is in the past.

    Returns the number of rows dispatched. Each row's ``next_run_at``
    is advanced before any work happens, so a slow search can't be
    picked up twice by an overlapping tick.
    """
    moment = now or datetime.now(timezone.utc)
    rows = (
        (
            await session.execute(
                select(SavedSearch)
                .where(SavedSearch.active.is_(True))
                .where(SavedSearch.schedule.is_not(None))
                .where(SavedSearch.next_run_at.is_not(None))
                .where(SavedSearch.next_run_at <= moment)
            )
        )
        .scalars()
        .all()
    )

    dispatched = 0
    for row in rows:
        # Advance the cursor first so the next tick doesn't double-run
        # this saved search if the underlying job takes longer than
        # the tick interval.
        row.next_run_at = next_run_after(row.schedule, now=moment)
        row.last_run_at = moment
        row.updated_at = moment
        await session.commit()

        try:
            await run_search(row, session)
            dispatched += 1
        except Exception as exc:  # noqa: BLE001 - log + skip; loop continues
            logger.warning(
                "saved-search dispatch failed for %s: %s", row.id, exc
            )

    return dispatched


def build_search_query(saved: SavedSearch) -> SearchQuery:
    """Materialise a fresh ``SearchQuery`` from a saved row.

    Lives here so the worker and the inline fallback share one shape.
    Caller is responsible for committing.
    """
    return SearchQuery(
        id=uuid.uuid4(),
        user_id=saved.user_id,
        team_id=saved.team_id,
        niche=saved.niche,
        region=saved.region,
        target_languages=saved.target_languages,
        max_results=saved.max_results,
        scope=saved.scope,
        radius_m=saved.radius_m,
        status="pending",
        source="web",
    )
