"""White-label client-report stats + branded PDF rendering.

A ``ClientReport`` is a shareable, public view over one search's
results. Two consumers read the same aggregate:

* the web view (JSON) — :func:`build_report_stats`
* the downloadable PDF — :func:`build_branded_report_pdf`

Both are deliberately limited to the report's *aggregate* numbers plus
a short top-leads table (name / score / status / contact). No internal
ids, owner emails or cross-team data ever cross into here — the public
endpoints hand us a single ``SearchQuery`` and the team's branding, and
nothing else leaks.

The PDF builder never raises on a bad logo: a corrupt / oversized /
non-image base64 blob is caught and the header simply omits the image
rather than failing the whole download. Run :func:`build_branded_report_pdf`
inside ``asyncio.to_thread`` at the call site (reportlab is sync), the
same way the xlsx export does.
"""

from __future__ import annotations

import base64
import io
import logging
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.db.models import Lead, LeadActivity, SearchQuery

logger = logging.getLogger(__name__)

# Fallback accent when a team hasn't set a brand colour.
_DEFAULT_ACCENT = "#3D5AFE"

# How many leads land in the report's top-leads table.
_TOP_LEADS_LIMIT = 15


def _lead_has_email(lead: Lead) -> bool:
    """True if we have *any* address to show — contact_email or a
    scraped website-meta email."""
    if lead.contact_email:
        return True
    meta = lead.website_meta or {}
    emails = meta.get("emails")
    if isinstance(emails, list) and any(
        isinstance(e, str) and "@" in e for e in emails
    ):
        return True
    primary = meta.get("primary_email")
    return isinstance(primary, str) and "@" in primary


def _lead_email(lead: Lead) -> str | None:
    if lead.contact_email:
        return lead.contact_email
    meta = lead.website_meta or {}
    emails = meta.get("emails")
    if isinstance(emails, list):
        for e in emails:
            if isinstance(e, str) and "@" in e:
                return e
    primary = meta.get("primary_email")
    if isinstance(primary, str) and "@" in primary:
        return primary
    return None


async def build_report_stats(
    session: AsyncSession, search: SearchQuery
) -> dict:
    """Aggregate one search into the numbers a client report shows.

    Null-safe across the board: an empty search returns zeroed counts
    and an empty ``top_leads`` list rather than raising.
    """
    leads = (
        await session.execute(
            select(Lead)
            .where(Lead.query_id == search.id)
            .where(Lead.deleted_at.is_(None))
        )
    ).scalars().all()

    total_leads = len(leads)
    hot_leads = sum(1 for ld in leads if (ld.score_ai or 0) >= 75)
    leads_with_email = sum(1 for ld in leads if _lead_has_email(ld))
    leads_with_valid_email = sum(
        1 for ld in leads if ld.email_status == "valid"
    )
    leads_with_phone = sum(1 for ld in leads if ld.phone)

    scored = [ld.score_ai for ld in leads if ld.score_ai is not None]
    avg_score = round(sum(scored) / len(scored), 1) if scored else None

    replied = 0
    if leads:
        lead_ids = [ld.id for ld in leads]
        # Count distinct leads that ever received a reply. Plain scan +
        # set keeps it portable across Postgres and the sqlite test DB.
        rows = (
            await session.execute(
                select(LeadActivity.lead_id)
                .where(LeadActivity.lead_id.in_(lead_ids))
                .where(LeadActivity.kind == "email_replied")
            )
        ).scalars().all()
        replied = len(set(rows))

    top_sorted = sorted(
        leads, key=lambda ld: (ld.score_ai or 0), reverse=True
    )[:_TOP_LEADS_LIMIT]
    top_leads = [
        {
            "name": ld.name,
            "score": int(ld.score_ai) if ld.score_ai is not None else None,
            "lead_status": ld.lead_status,
            "contact_email": _lead_email(ld),
            "phone": ld.phone,
            "website": ld.website,
        }
        for ld in top_sorted
    ]

    insights: str | None = None
    summary = search.analysis_summary
    if isinstance(summary, dict):
        raw = summary.get("insights")
        if isinstance(raw, str) and raw.strip():
            insights = raw.strip()

    return {
        "total_leads": total_leads,
        "hot_leads": hot_leads,
        "leads_with_email": leads_with_email,
        "leads_with_valid_email": leads_with_valid_email,
        "leads_with_phone": leads_with_phone,
        "avg_score": avg_score,
        "replied": replied,
        "top_leads": top_leads,
        "insights": insights,
        "niche": search.niche,
        "region": search.region,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _decode_logo(data_url: str | None) -> ImageReader | None:
    """Decode a ``data:image/...;base64,...`` URL into an ImageReader.

    Returns ``None`` (never raises) on anything malformed so a bad logo
    can't take down the whole PDF.
    """
    if not data_url or not isinstance(data_url, str):
        return None
    try:
        if not data_url.startswith("data:image/"):
            return None
        _, b64 = data_url.split(",", 1)
        raw = base64.b64decode(b64, validate=True)
        if not raw:
            return None
        return ImageReader(io.BytesIO(raw))
    except Exception:  # noqa: BLE001
        logger.warning("report: logo decode failed, omitting image")
        return None


def _accent_color(brand_color: str | None) -> colors.Color:
    candidate = (brand_color or "").strip()
    try:
        return colors.HexColor(candidate or _DEFAULT_ACCENT)
    except Exception:  # noqa: BLE001
        return colors.HexColor(_DEFAULT_ACCENT)


def build_branded_report_pdf(
    *,
    stats: dict,
    brand_name: str,
    brand_logo_data_url: str | None,
    brand_color: str | None,
    search_title: str,
) -> bytes:
    """Render the multi-page white-label PDF for a client report.

    Robust by design: a bad logo is omitted, a bad colour falls back to
    the default accent, and missing numbers render as ``0``.
    """
    accent = _accent_color(brand_color)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )

    styles = getSampleStyleSheet()
    brand_style = ParagraphStyle(
        "brand",
        parent=styles["Heading1"],
        fontSize=20,
        textColor=colors.white,
        spaceAfter=0,
    )
    h2 = ParagraphStyle(
        "h2", parent=styles["Heading2"], fontSize=13, spaceAfter=4, spaceBefore=12
    )
    body = styles["Normal"]
    muted = ParagraphStyle(
        "muted", parent=body, fontSize=9, textColor=colors.grey
    )

    story: list = []

    # ── Header band (brand colour) with logo + agency name ──────────
    logo_img = _decode_logo(brand_logo_data_url)
    title_cell = Paragraph(brand_name or "Report", brand_style)
    if logo_img is not None:
        try:
            iw, ih = logo_img.getSize()
            target_h = 16 * mm
            target_w = target_h * (iw / ih) if ih else target_h
            target_w = min(target_w, 45 * mm)
            header_inner = [[Image(logo_img, width=target_w, height=target_h), title_cell]]
            header = Table(header_inner, colWidths=[target_w + 6 * mm, None])
        except Exception:  # noqa: BLE001
            header = Table([[title_cell]], colWidths=[None])
    else:
        header = Table([[title_cell]], colWidths=[None])
    header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), accent),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.append(header)
    story.append(Spacer(1, 6 * mm))

    # ── Report title + scope ────────────────────────────────────────
    story.append(Paragraph(search_title or "Lead Report", h2))
    niche = stats.get("niche") or ""
    region = stats.get("region") or ""
    scope_bits = " · ".join(b for b in (niche, region) if b)
    if scope_bits:
        story.append(Paragraph(scope_bits, muted))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey, spaceAfter=8))

    # ── Headline summary ────────────────────────────────────────────
    total = int(stats.get("total_leads") or 0)
    hot = int(stats.get("hot_leads") or 0)
    with_email = int(stats.get("leads_with_email") or 0)
    replied = int(stats.get("replied") or 0)
    headline = (
        f"{total} leads found, {hot} hot, {with_email} with email, "
        f"{replied} replied"
    )
    story.append(Paragraph("Summary", h2))
    story.append(Paragraph(headline, body))

    summary_rows = [
        ["Metric", "Value"],
        ["Total leads", str(total)],
        ["Hot leads (score ≥ 75)", str(hot)],
        ["With email", str(with_email)],
        ["With valid email", str(int(stats.get("leads_with_valid_email") or 0))],
        ["With phone", str(int(stats.get("leads_with_phone") or 0))],
        ["Replied", str(replied)],
    ]
    avg = stats.get("avg_score")
    if avg is not None:
        summary_rows.append(["Average score", f"{avg}/100"])
    t = Table(summary_rows, colWidths=[90 * mm, 70 * mm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), accent),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
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

    insights = stats.get("insights")
    if isinstance(insights, str) and insights.strip():
        story.append(Paragraph("Insights", h2))
        story.append(Paragraph(insights.strip(), body))
        story.append(Spacer(1, 4 * mm))

    # ── Top leads table ─────────────────────────────────────────────
    top_leads = stats.get("top_leads") or []
    if top_leads:
        story.append(Paragraph("Top leads", h2))
        rows: list[list] = [["Company", "Score", "Status", "Contact"]]
        for ld in top_leads:
            score = ld.get("score")
            contact = ld.get("contact_email") or ld.get("phone") or "—"
            rows.append(
                [
                    str(ld.get("name") or "—")[:48],
                    "—" if score is None else str(score),
                    str(ld.get("lead_status") or "—"),
                    str(contact)[:42],
                ]
            )
        lead_table = Table(
            rows, colWidths=[60 * mm, 18 * mm, 32 * mm, 54 * mm], repeatRows=1
        )
        lead_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), accent),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#fafafa")],
                    ),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story.append(lead_table)

    # ── Footer ──────────────────────────────────────────────────────
    story.append(Spacer(1, 10 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    story.append(
        Paragraph(f"Generated by {brand_name or 'Convioo'} · {date_str}", muted)
    )
    story.append(Paragraph("Powered by Convioo", muted))

    doc.build(story)
    buf.seek(0)
    return buf.read()
