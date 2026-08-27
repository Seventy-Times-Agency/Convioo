"""``/api/v1/deliverability/*`` + lead email re-verification.

Wave 2 deliverability surface for the dashboard:

* ``GET /api/v1/deliverability/status`` merges the warmup / daily-cap
  snapshot with an SPF / DMARC check for the caller's sending domain.
* ``POST /api/v1/leads/{lead_id}/verify-email`` re-runs verification on
  a single lead's contact address and persists the verdict.

The "sending domain" is the connected mailbox's address domain when one
is connected; otherwise the platform's ``EMAIL_FROM`` domain.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.routes._helpers import membership
from leadgen.config import get_settings
from leadgen.core.services.dns_auth import check_domain_auth
from leadgen.core.services.email_verification import verify_email
from leadgen.core.services.oauth_store import get_credential
from leadgen.core.services.send_quota import get_send_status
from leadgen.db.models import Lead, SearchQuery, User
from leadgen.db.session import session_factory

router = APIRouter(prefix="/api/v1", tags=["deliverability"])

_SENDING_PROVIDERS = ("gmail", "outlook")
_EMAIL_FROM_RE = re.compile(r"<([^>]+)>")


def _domain_of(address: str | None) -> str | None:
    if not address:
        return None
    addr = address.strip()
    if "@" not in addr:
        return None
    return addr.rsplit("@", 1)[1].strip().lower() or None


def _platform_from_domain() -> str | None:
    """Domain of the platform ``EMAIL_FROM`` (handles ``Name <a@b>`` form)."""
    raw = get_settings().email_from or ""
    match = _EMAIL_FROM_RE.search(raw)
    address = match.group(1) if match else raw
    return _domain_of(address)


async def _sending_domain(session, user_id: int) -> str | None:
    """The caller's sending domain — connected mailbox, else platform."""
    for provider in _SENDING_PROVIDERS:
        cred = await get_credential(
            session, user_id=user_id, provider=provider
        )
        if cred is not None and cred.account_email:
            domain = _domain_of(cred.account_email)
            if domain:
                return domain
    return _platform_from_domain()


@router.get("/deliverability/status")
async def deliverability_status(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Warmup / daily-cap snapshot merged with SPF / DMARC for the domain."""
    async with session_factory() as session:
        status = await get_send_status(session, current_user.id)
        domain = await _sending_domain(session, current_user.id)

    auth = await check_domain_auth(domain) if domain else {
        "spf": {"present": False, "record": None},
        "dmarc": {"present": False, "policy": None},
    }

    return {
        "connected": status["connected"],
        "provider": status["provider"],
        "domain": domain,
        "warmup_day": status["warmup_day"],
        "daily_cap": status["daily_cap"],
        "sent_today": status["sent_today"],
        "remaining": status["remaining"],
        "spf": auth["spf"],
        "dmarc": auth["dmarc"],
    }


async def _authorise_lead(
    session, lead_id: uuid.UUID, current_user: User
) -> Lead:
    """Load + authorise a lead; 404 on missing / cross-user."""
    lead = await session.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="lead not found")
    search = await session.get(SearchQuery, lead.query_id)
    allowed = search is not None and search.user_id == current_user.id
    if not allowed and search is not None and search.team_id is not None:
        ms = await membership(session, search.team_id, current_user.id)
        allowed = ms is not None
    if not allowed:
        raise HTTPException(status_code=404, detail="lead not found")
    return lead


@router.post("/leads/{lead_id}/verify-email")
async def verify_lead_email(
    lead_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Re-run email verification for one lead and persist the verdict.

    Uses ``contact_email`` when set; otherwise re-picks the best address
    out of ``website_meta.emails`` (legacy rows enriched before the
    field existed).
    """
    from leadgen.pipeline.enrichment import pick_primary_email

    async with session_factory() as session:
        lead = await _authorise_lead(session, lead_id, current_user)

        target = lead.contact_email
        if not target:
            meta = lead.website_meta if isinstance(lead.website_meta, dict) else {}
            target = pick_primary_email(meta.get("emails"))

        if not target:
            lead.email_status = "unknown"
            lead.email_checked_at = datetime.now(timezone.utc)
            await session.commit()
            return {
                "contact_email": None,
                "email_status": "unknown",
                "email_checked_at": _iso(lead.email_checked_at),
            }

        verdict = await verify_email(target)
        lead.contact_email = target
        lead.email_status = verdict.status
        lead.email_checked_at = datetime.now(timezone.utc)
        await session.commit()
        return {
            "contact_email": lead.contact_email,
            "email_status": lead.email_status,
            "email_checked_at": _iso(lead.email_checked_at),
        }


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment is not None else None
