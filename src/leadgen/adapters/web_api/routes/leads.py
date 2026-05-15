"""``/api/v1/leads/{id}/(archive|unarchive)`` — CRM archive zone.

Carved out of ``app.py`` first; the rest of ``/api/v1/leads/*`` will
follow in subsequent passes. Archive sets ``archived_at`` and writes
through to ``user_seen_leads`` / ``team_seen_leads`` so future
searches don't resurface the same place; unarchive restores CRM
visibility but keeps the search-side block (intentional).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.routes._helpers import membership
from leadgen.core.services.lead_archive import archive_lead, unarchive_lead
from leadgen.db.models import Lead, LeadActivity, SearchQuery, User
from leadgen.db.session import session_factory

router = APIRouter(tags=["leads"])


async def _authorise_lead(
    session,
    lead_id: uuid.UUID,
    current_user: User,
) -> tuple[Lead, SearchQuery]:
    """Load + authorise a lead. Raises 404 / 403 directly on failure."""
    lead = await session.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="lead not found")
    search = await session.get(SearchQuery, lead.query_id)
    if search is None:
        raise HTTPException(status_code=404, detail="search not found")

    allowed = search.user_id == current_user.id
    if not allowed and search.team_id is not None:
        ms = await membership(session, search.team_id, current_user.id)
        allowed = ms is not None
    if not allowed:
        raise HTTPException(status_code=403, detail="forbidden")
    return lead, search


@router.post("/api/v1/leads/{lead_id}/archive")
async def archive_lead_endpoint(
    lead_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    """Move a lead to the Archive zone.

    Sets ``archived_at`` and writes through to ``user_seen_leads`` /
    ``team_seen_leads`` so the same place won't return from a future
    search. Un-archiving restores CRM visibility but the search-side
    block stays — by design (see :mod:`leadgen.core.services.lead_archive`).
    """
    async with session_factory() as session:
        lead, search = await _authorise_lead(session, lead_id, current_user)
        await archive_lead(session, lead, search)
        session.add(
            LeadActivity(
                lead_id=lead.id,
                user_id=current_user.id,
                team_id=search.team_id,
                kind="archived",
                payload={},
            )
        )
        await session.commit()
    return {"ok": True}


@router.post("/api/v1/leads/{lead_id}/unarchive")
async def unarchive_lead_endpoint(
    lead_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    """Restore a lead from the Archive zone back to the active CRM.

    Does NOT clear the seen-leads block — the search-side suppression
    is permanent by design.
    """
    async with session_factory() as session:
        lead, search = await _authorise_lead(session, lead_id, current_user)
        await unarchive_lead(lead)
        session.add(
            LeadActivity(
                lead_id=lead.id,
                user_id=current_user.id,
                team_id=search.team_id,
                kind="unarchived",
                payload={},
            )
        )
        await session.commit()
    return {"ok": True}
