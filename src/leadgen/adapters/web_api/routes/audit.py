"""Digital audit PDF — GET /api/v1/leads/{lead_id}/audit-pdf."""
from __future__ import annotations

import io
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.db.models import Lead, SearchQuery, User
from leadgen.db.session import session_factory

router = APIRouter(prefix="/api/v1", tags=["audit"])
logger = logging.getLogger(__name__)


def _build_pdf(lead: Lead) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=20, spaceAfter=6)
    h2 = ParagraphStyle(
        "h2", parent=styles["Heading2"], fontSize=13, spaceAfter=4, spaceBefore=12
    )
    body = styles["Normal"]
    muted = ParagraphStyle("muted", parent=body, fontSize=9, textColor=colors.grey)

    meta: dict[str, Any] = lead.website_meta or {}
    snapshots: list[dict] = lead.rating_snapshots or []
    components: dict[str, int] = lead.score_components or {}

    story: list[Any] = []

    story.append(Paragraph(f"Digital Audit — {lead.name}", h1))
    if lead.address:
        story.append(Paragraph(lead.address, muted))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey, spaceAfter=8))

    story.append(Paragraph("Summary", h2))
    if lead.score_ai is not None:
        story.append(Paragraph(f"Pain Score: {int(lead.score_ai)}/100", body))
    if lead.summary:
        story.append(Paragraph(lead.summary, body))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("Website Health", h2))
    health_rows: list[list[str]] = [["Metric", "Value"]]
    for label, key in [
        ("PageSpeed Mobile", "pagespeed_mobile"),
        ("PageSpeed Desktop", "pagespeed_desktop"),
    ]:
        val = meta.get(key)
        if val is not None:
            health_rows.append([label, f"{val}/100"])
    ssl = meta.get("has_ssl")
    if ssl is not None:
        health_rows.append(["SSL Certificate", "Yes" if ssl else "No"])
    last_year = meta.get("last_modified_year")
    if last_year:
        health_rows.append(["Last Updated", str(last_year)])
    if len(health_rows) > 1:
        t = Table(health_rows, colWidths=[90 * mm, 70 * mm])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f5f5f5")),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#fafafa")],
                    ),
                ]
            )
        )
        story.append(t)
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("Reviews", h2))
    if lead.rating:
        story.append(
            Paragraph(
                f"Rating: {lead.rating}/5 ({lead.reviews_count or 0} reviews)", body
            )
        )
    if len(snapshots) >= 2:
        delta = snapshots[-1]["rating"] - snapshots[0]["rating"]
        trend = f"+{delta:.1f}" if delta > 0 else f"{delta:.1f}"
        story.append(Paragraph(f"Trend: {trend} over {len(snapshots)} checks", body))
    if lead.reviews_summary:
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(f"Recent: {lead.reviews_summary}", muted))
    story.append(Spacer(1, 4 * mm))

    if components:
        story.append(Paragraph("Score Breakdown", h2))
        comp_rows: list[list[str]] = [["Component", "Points"]]
        for key, val in components.items():
            comp_rows.append([key.replace("_", " ").title(), str(val)])
        t = Table(comp_rows, colWidths=[110 * mm, 50 * mm])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f5f5f5")),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ]
            )
        )
        story.append(t)
        story.append(Spacer(1, 4 * mm))

    if lead.advice:
        story.append(Paragraph("Recommendations", h2))
        story.append(Paragraph(lead.advice, body))
        story.append(Spacer(1, 4 * mm))

    weaknesses = lead.weaknesses
    if weaknesses:
        story.append(Paragraph("Areas to Improve", h2))
        items = weaknesses if isinstance(weaknesses, list) else [weaknesses]
        for w in items:
            story.append(Paragraph(f"• {w}", body))
        story.append(Spacer(1, 4 * mm))

    story.append(Spacer(1, 8 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    story.append(Paragraph("Generated by Convioo · convioo.com", muted))

    doc.build(story)
    buf.seek(0)
    return buf.read()


@router.get("/leads/{lead_id}/audit-pdf")
async def download_audit_pdf(
    lead_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    async with session_factory() as session:
        lead = await session.get(Lead, lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="Lead not found")
        search = await session.get(SearchQuery, lead.query_id)
        if search is None or search.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Forbidden")

    try:
        pdf_bytes = _build_pdf(lead)
    except Exception as exc:
        logger.error("audit_pdf: generation failed lead_id=%s", lead_id, exc_info=True)
        raise HTTPException(status_code=500, detail="PDF generation failed") from exc

    safe_name = "".join(
        c if c.isalnum() or c in "._- " else "_" for c in lead.name
    )[:50]
    filename = f"{safe_name}_audit.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
