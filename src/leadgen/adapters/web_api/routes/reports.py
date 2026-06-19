"""``/api/v1/...`` — white-label client reports (Wave 4).

Three surfaces:

* **authenticated owner/member** mints + lists + revokes reports over a
  search's results (``POST /searches/{id}/report``, ``GET /reports``,
  ``DELETE /reports/{id}``).
* **public, no-auth** consumers read the branded JSON or download the
  PDF behind an unguessable token (``GET /reports/public/{token}`` and
  ``…/download.pdf``).

The public endpoints take **no** auth dependency and are CSRF-exempt
(see ``csrf._EXEMPT_PREFIXES``). They expose only the report's aggregate
stats + a short top-leads table + the team's branding — never internal
ids, user emails or another team's data. A revoked / expired / unknown
token always answers a uniform 404 so links can't be probed.
"""

from __future__ import annotations

import asyncio
import io
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.routes._helpers import membership
from leadgen.core.services.report_builder import (
    build_branded_report_pdf,
    build_report_stats,
)
from leadgen.db.models import (
    ClientReport,
    SearchQuery,
    Team,
    TeamMembership,
    User,
)
from leadgen.db.session import session_factory

router = APIRouter(tags=["reports"])
logger = logging.getLogger(__name__)


# ── Schemas ─────────────────────────────────────────────────────────────


class ReportCreateRequest(BaseModel):
    title: str | None = None
    expires_in_days: int | None = None


class ReportCreateResponse(BaseModel):
    report_id: str
    token: str
    share_path: str
    expires_at: str | None = None


class ReportListItem(BaseModel):
    report_id: str
    token: str
    title: str | None = None
    search_id: str
    revoked: bool
    expires_at: str | None = None
    created_at: str
    share_path: str


class ReportListResponse(BaseModel):
    reports: list[ReportListItem]


# ── Helpers ─────────────────────────────────────────────────────────────


def _share_path(token: str) -> str:
    return f"/report/{token}"


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _is_live(report: ClientReport) -> bool:
    """A report is viewable while it isn't revoked and hasn't expired."""
    if report.revoked:
        return False
    expires = report.expires_at
    if expires is not None:
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= expires:
            return False
    return True


async def _load_public_report(
    session, token: str
) -> tuple[ClientReport, SearchQuery, Team]:
    """Resolve a public token to (report, search, team) or raise 404.

    Uniform 404 on unknown / revoked / expired / dangling so a caller
    can't distinguish the reasons. Team branding is resolved via the
    report's own ``team_id`` — never trusting anything client-supplied.
    """
    report = (
        await session.execute(
            select(ClientReport).where(ClientReport.token == token).limit(1)
        )
    ).scalar_one_or_none()
    if report is None or not _is_live(report):
        raise HTTPException(status_code=404, detail="report not found")
    search = await session.get(SearchQuery, report.search_id)
    team = await session.get(Team, report.team_id)
    if search is None or team is None:
        raise HTTPException(status_code=404, detail="report not found")
    return report, search, team


# ── Authenticated endpoints ─────────────────────────────────────────────


@router.post(
    "/api/v1/searches/{search_id}/report",
    response_model=ReportCreateResponse,
)
async def create_report(
    search_id: uuid.UUID,
    body: ReportCreateRequest,
    current_user: User = Depends(get_current_user),
) -> ReportCreateResponse:
    """Mint a shareable client report over a search the caller may read.

    Readable when the caller owns the search or is a member of its team.
    The report is anchored to a team: the search's ``team_id`` if set,
    otherwise the caller's own personal team is resolved so branding has
    a home. Cross-user access answers 404 (search ids stay unprobeable).
    """
    async with session_factory() as session:
        search = await session.get(SearchQuery, search_id)
        if search is None:
            raise HTTPException(status_code=404, detail="search not found")

        allowed = search.user_id == current_user.id
        team_id = search.team_id
        if not allowed and team_id is not None:
            allowed = (
                await membership(session, team_id, current_user.id)
            ) is not None
        if not allowed:
            raise HTTPException(status_code=404, detail="search not found")

        # Personal-mode search (no team) → anchor the report to the
        # caller's own team so the branding lookup has somewhere to land.
        if team_id is None:
            owned = (
                await session.execute(
                    select(TeamMembership.team_id)
                    .where(TeamMembership.user_id == current_user.id)
                    .order_by(TeamMembership.created_at)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if owned is None:
                raise HTTPException(
                    status_code=400,
                    detail="no team available to anchor the report",
                )
            team_id = owned

        title = (body.title or "").strip() or None
        expires_at: datetime | None = None
        if body.expires_in_days and body.expires_in_days > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(
                days=body.expires_in_days
            )

        token = secrets.token_urlsafe(32)
        report = ClientReport(
            team_id=team_id,
            search_id=search.id,
            created_by_user_id=current_user.id,
            title=title,
            token=token,
            expires_at=expires_at,
        )
        session.add(report)
        await session.commit()
        await session.refresh(report)

        return ReportCreateResponse(
            report_id=str(report.id),
            token=report.token,
            share_path=_share_path(report.token),
            expires_at=_iso(report.expires_at),
        )


@router.get("/api/v1/reports", response_model=ReportListResponse)
async def list_reports(
    current_user: User = Depends(get_current_user),
) -> ReportListResponse:
    """List reports across every team the caller belongs to, newest
    first."""
    async with session_factory() as session:
        team_ids = (
            await session.execute(
                select(TeamMembership.team_id).where(
                    TeamMembership.user_id == current_user.id
                )
            )
        ).scalars().all()
        if not team_ids:
            return ReportListResponse(reports=[])

        rows = (
            await session.execute(
                select(ClientReport)
                .where(ClientReport.team_id.in_(team_ids))
                .order_by(ClientReport.created_at.desc())
            )
        ).scalars().all()

        return ReportListResponse(
            reports=[
                ReportListItem(
                    report_id=str(r.id),
                    token=r.token,
                    title=r.title,
                    search_id=str(r.search_id),
                    revoked=r.revoked,
                    expires_at=_iso(r.expires_at),
                    created_at=_iso(r.created_at) or "",
                    share_path=_share_path(r.token),
                )
                for r in rows
            ]
        )


@router.delete("/api/v1/reports/{report_id}")
async def revoke_report(
    report_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Revoke (soft-kill) a report. The creator, or a team owner, may
    revoke; the row is kept for the audit trail."""
    async with session_factory() as session:
        report = await session.get(ClientReport, report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="report not found")

        allowed = report.created_by_user_id == current_user.id
        if not allowed:
            from leadgen.core.services.team_permissions import (
                ROLE_OWNER,
                normalize_role,
            )

            m = await membership(session, report.team_id, current_user.id)
            allowed = m is not None and normalize_role(m.role) == ROLE_OWNER
        if not allowed:
            raise HTTPException(status_code=403, detail="forbidden")

        report.revoked = True
        await session.commit()
        return {"ok": True}


# ── Public endpoints (no auth, CSRF-exempt) ─────────────────────────────


@router.get("/api/v1/reports/public/{token}")
async def public_report_json(token: str) -> dict:
    """The branded JSON for the public web view. No auth."""
    async with session_factory() as session:
        report, search, team = await _load_public_report(session, token)
        stats = await build_report_stats(session, search)
        return {
            "brand_name": team.brand_name,
            "brand_logo": team.brand_logo,
            "brand_color": team.brand_color,
            "title": report.title,
            "generated_at": stats["generated_at"],
            "stats": stats,
        }


@router.get("/api/v1/reports/public/{token}/download.pdf")
async def public_report_pdf(token: str) -> StreamingResponse:
    """The branded PDF download. No auth."""
    async with session_factory() as session:
        report, search, team = await _load_public_report(session, token)
        stats = await build_report_stats(session, search)
        brand_name = team.brand_name or "Convioo"
        title = report.title or f"{search.niche} — {search.region}"

    try:
        pdf_bytes = await asyncio.to_thread(
            build_branded_report_pdf,
            stats=stats,
            brand_name=brand_name,
            brand_logo_data_url=team.brand_logo,
            brand_color=team.brand_color,
            search_title=title,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("report_pdf: generation failed token=%s", token, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PDF generation failed",
        ) from exc

    safe = "".join(
        c if c.isalnum() or c in "._- " else "_" for c in brand_name
    )[:40].strip() or "report"
    filename = f"{safe}_report.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
