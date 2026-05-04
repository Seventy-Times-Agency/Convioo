"""``/api/v1/admin/*`` — platform ops dashboard.

This is the founder's window into platform health: signup count,
running searches, Anthropic spend (sampled from Prometheus), failure
rate, queue depth, source health. Explicitly NOT a business view —
``/teams/{id}/analytics`` covers per-team CRM analytics, this one is
for "is the engine alive".

Gated by ``users.is_admin`` (a 404 — not 403 — for non-admins so the
route doesn't even hint at its existence).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.schemas import (
    AdminOverview,
    AdminQuality,
    AdminTopUser,
    SlowSearchEntry,
)
from leadgen.db.models import Lead, SearchQuery, Team, User
from leadgen.db.session import session_factory

router = APIRouter(tags=["admin"])


async def _require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Auth dep that 404s for non-admins (no info leak)."""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=404, detail="not found")
    return current_user


@router.get("/api/v1/admin/overview", response_model=AdminOverview)
async def admin_overview(
    _admin: User = Depends(_require_admin),
) -> AdminOverview:
    """High-level platform health for the in-app admin dashboard.

    All counts are computed server-side in a single round-trip per
    metric — cheap on Postgres because every column we touch is
    already indexed for the regular CRM queries. Trial / paid status
    reuses the same predicate the billing service uses so the cutover
    from "trial active" to "paid active" matches /app/billing exactly.
    """
    now = datetime.now(timezone.utc)
    cutoff_7d = now - timedelta(days=7)
    cutoff_24h = now - timedelta(hours=24)

    async with session_factory() as session:
        users_total = (
            await session.execute(select(func.count()).select_from(User))
        ).scalar_one()
        teams_total = (
            await session.execute(select(func.count()).select_from(Team))
        ).scalar_one()
        searches_last_7d = (
            await session.execute(
                select(func.count())
                .select_from(SearchQuery)
                .where(SearchQuery.created_at >= cutoff_7d)
            )
        ).scalar_one()
        searches_running = (
            await session.execute(
                select(func.count())
                .select_from(SearchQuery)
                .where(SearchQuery.status == "running")
            )
        ).scalar_one()
        leads_last_7d = (
            await session.execute(
                select(func.count())
                .select_from(Lead)
                .where(Lead.created_at >= cutoff_7d)
            )
        ).scalar_one()
        failed_searches_last_24h = (
            await session.execute(
                select(func.count())
                .select_from(SearchQuery)
                .where(SearchQuery.status == "failed")
                .where(SearchQuery.created_at >= cutoff_24h)
            )
        ).scalar_one()

        # Paid + trialing counts via the same predicate the billing
        # service uses. We compute in Python since the predicate spans
        # two columns and a clock check.
        users = (await session.execute(select(User))).scalars().all()
        users_paid = sum(
            1
            for u in users
            if u.plan != "free"
            and u.plan_until is not None
            and (
                u.plan_until.replace(tzinfo=timezone.utc)
                if u.plan_until.tzinfo is None
                else u.plan_until
            )
            > now
        )
        users_trialing = sum(
            1
            for u in users
            if (
                u.trial_ends_at is not None
                and (
                    u.trial_ends_at.replace(tzinfo=timezone.utc)
                    if u.trial_ends_at.tzinfo is None
                    else u.trial_ends_at
                )
                > now
                and (u.plan or "free") == "free"
            )
        )

        top_rows = (
            await session.execute(
                select(
                    User.id,
                    User.display_name,
                    User.first_name,
                    User.email,
                    User.plan,
                    User.queries_used,
                    User.is_admin,
                )
                .order_by(User.queries_used.desc())
                .limit(10)
            )
        ).all()

    return AdminOverview(
        users_total=int(users_total or 0),
        users_paid=users_paid,
        users_trialing=users_trialing,
        teams_total=int(teams_total or 0),
        searches_last_7d=int(searches_last_7d or 0),
        searches_running=int(searches_running or 0),
        leads_last_7d=int(leads_last_7d or 0),
        failed_searches_last_24h=int(failed_searches_last_24h or 0),
        top_users_by_searches=[
            AdminTopUser(
                user_id=int(row[0]),
                name=(row[1] or row[2] or f"user-{row[0]}")[:60],
                email=row[3],
                plan=row[4] or "free",
                queries_used=int(row[5] or 0),
                is_admin=bool(row[6]),
            )
            for row in top_rows
        ],
    )


@router.get("/api/v1/admin/sources/health")
async def admin_sources_health(
    _admin: User = Depends(_require_admin),
) -> dict[str, Any]:
    """Live ping of every external collector.

    Used by the admin dashboard to spot when Yelp's daily budget is
    gone or Overpass is throttling, without trawling Railway logs.
    Each probe runs in parallel, ~6 s timeout, never raises. Results
    are cached in-process for ~60 s so refreshing the dashboard
    doesn't hammer the upstreams.
    """
    from leadgen.core.services.source_health import check_all

    results = await check_all()
    return {"sources": [r.to_dict() for r in results]}


@router.get("/api/v1/admin/quality", response_model=AdminQuality)
async def admin_quality(
    _admin: User = Depends(_require_admin),
) -> AdminQuality:
    """Ops/quality dashboard payload — explicitly NOT a business view.

    Surfaces signals that tell the founder when the platform is
    misbehaving: external-API call counts, error rates, queue depth,
    and the slowest searches over the last 24 h. Anthropic spend
    comes from the in-process Prometheus counter (sampled at
    scrape-time, no DB hit) — accuracy is "are we on the same order
    of magnitude as yesterday", not invoice-grade.
    """
    from prometheus_client import REGISTRY

    # ── Anthropic call counters from Prometheus ────────────────────
    anthropic_total = 0
    anthropic_failed = 0
    for metric in REGISTRY.collect():
        if metric.name != "leadgen_external_api_calls":
            continue
        for sample in metric.samples:
            if not sample.name.endswith("_total"):
                continue
            if sample.labels.get("api") != "anthropic":
                continue
            value = int(sample.value)
            anthropic_total += value
            if sample.labels.get("status") not in {"ok", "success", "200"}:
                anthropic_failed += value
    # ~$0.005 per Haiku call at ~1.5k input + 700 output tokens.
    # Tracking exact tokens would require a side-channel from the SDK;
    # this estimate is good enough to spot a 10x spike.
    anthropic_estimated_spend_usd = round(anthropic_total * 0.005, 2)

    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)

    async with session_factory() as session:
        searches_24h = (
            await session.execute(
                select(func.count())
                .select_from(SearchQuery)
                .where(SearchQuery.created_at >= cutoff_24h)
            )
        ).scalar_one()
        failed_24h = (
            await session.execute(
                select(func.count())
                .select_from(SearchQuery)
                .where(SearchQuery.created_at >= cutoff_24h)
                .where(SearchQuery.status == "failed")
            )
        ).scalar_one()

        queue_pending = (
            await session.execute(
                select(func.count())
                .select_from(SearchQuery)
                .where(SearchQuery.status == "pending")
            )
        ).scalar_one()
        queue_running = (
            await session.execute(
                select(func.count())
                .select_from(SearchQuery)
                .where(SearchQuery.status == "running")
            )
        ).scalar_one()

        # Slowest 10 finished searches in the last 24 h. We compute
        # duration in Python because subtracting two timestamps is
        # awkward across SQLite (tests) and Postgres (prod) without a
        # dialect-specific expression.
        slow_rows = (
            await session.execute(
                select(SearchQuery)
                .where(SearchQuery.created_at >= cutoff_24h)
                .where(SearchQuery.finished_at.is_not(None))
                .order_by(SearchQuery.created_at.desc())
                .limit(200)
            )
        ).scalars().all()
        slow_entries: list[SlowSearchEntry] = []
        for q in slow_rows:
            if not q.finished_at:
                continue
            started = q.created_at
            ended = q.finished_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            if ended.tzinfo is None:
                ended = ended.replace(tzinfo=timezone.utc)
            duration = (ended - started).total_seconds()
            slow_entries.append(
                SlowSearchEntry(
                    search_id=str(q.id),
                    niche=q.niche,
                    region=q.region,
                    duration_seconds=round(duration, 1),
                    leads_count=int(q.leads_count or 0),
                    status=q.status,
                    user_id=q.user_id,
                    finished_at=q.finished_at,
                )
            )
        slow_entries.sort(key=lambda e: e.duration_seconds, reverse=True)
        slow_entries = slow_entries[:10]

    total_24h = int(searches_24h or 0)
    failed_24h_int = int(failed_24h or 0)
    failure_rate = (failed_24h_int / total_24h) if total_24h else 0.0

    return AdminQuality(
        anthropic_calls_total=anthropic_total,
        anthropic_calls_failed=anthropic_failed,
        anthropic_estimated_spend_usd=anthropic_estimated_spend_usd,
        searches_total_24h=total_24h,
        searches_failed_24h=failed_24h_int,
        searches_failure_rate_24h=round(failure_rate, 4),
        queue_pending=int(queue_pending or 0),
        queue_running=int(queue_running or 0),
        slowest_searches=slow_entries,
    )
