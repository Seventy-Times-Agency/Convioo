"""Affiliate dashboard routes: codes CRUD and overview."""
from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.schemas import (
    AffiliateCodeCreateRequest,
    AffiliateCodeSchema,
    AffiliateCodeUpdate,
    AffiliateOverview,
)
from leadgen.db.models import (
    AffiliateCode,
    Referral,
    User,
)
from leadgen.db.session import session_factory

router = APIRouter()
logger = logging.getLogger(__name__)

# ── /api/v1/affiliate (per-user partner dashboard) ─────────────────────


@router.get("/api/v1/affiliate", response_model=AffiliateOverview)
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


@router.post(
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


@router.patch(
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


@router.delete("/api/v1/affiliate/codes/{code}")
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
