"""Lead archive: hide-but-keep-restorable, with permanent search block.

The product distinguishes three lead-removal states:

* ``deleted_at`` — soft-delete. Hidden from the CRM, kept on disk.
  Can be cleared to undelete. No effect on future searches.
* ``blacklisted`` — permanent forever-block. Always hidden, can't be
  undone, written through to ``user_seen_leads`` / ``team_seen_leads``
  so the same place can never come back from a search.
* ``archived_at`` (this module) — user-facing "not interested, hide
  it for good but let me look later". Visible in a dedicated Archive
  tab, **also** written through to seen-leads so the lead won't pop
  up in a future search. Restoring (un-archive) brings the lead back
  to the CRM list but **does not** clear the seen-leads block — the
  search-side suppression is intentionally permanent.

This module owns the seen-leads write-through so the route handler
stays thin. ``archive_lead`` is idempotent: re-archiving an already
archived lead just updates the timestamp.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.db.models import Lead, SearchQuery, TeamSeenLead, UserSeenLead
from leadgen.utils.dedup import domain_root as _domain_root
from leadgen.utils.dedup import normalize_phone as _normalize_phone


async def archive_lead(
    session: AsyncSession,
    lead: Lead,
    search: SearchQuery,
) -> None:
    """Archive ``lead`` and seal it from future searches.

    Also writes (or refreshes) the ``user_seen_leads`` / ``team_seen_leads``
    rows that the search pipeline uses to skip already-known places. The
    write-through stays in place after un-archive so a restored lead
    doesn't reappear from a fresh Google Maps query.

    The caller is responsible for permission checks and for committing
    the session.
    """
    lead.archived_at = datetime.now(timezone.utc)

    phone_key = _normalize_phone(lead.phone)
    domain_key = _domain_root(lead.website)

    if search.user_id and search.user_id != 0:
        existing_user = (
            await session.execute(
                select(UserSeenLead)
                .where(UserSeenLead.user_id == search.user_id)
                .where(UserSeenLead.source == lead.source)
                .where(UserSeenLead.source_id == lead.source_id)
            )
        ).scalar_one_or_none()
        if existing_user is None:
            session.add(
                UserSeenLead(
                    user_id=search.user_id,
                    source=lead.source,
                    source_id=lead.source_id,
                    phone_e164=phone_key,
                    domain_root=domain_key,
                )
            )
        else:
            existing_user.phone_e164 = phone_key
            existing_user.domain_root = domain_key

    if search.team_id is not None:
        existing_team = (
            await session.execute(
                select(TeamSeenLead)
                .where(TeamSeenLead.team_id == search.team_id)
                .where(TeamSeenLead.source == lead.source)
                .where(TeamSeenLead.source_id == lead.source_id)
            )
        ).scalar_one_or_none()
        if existing_team is None:
            session.add(
                TeamSeenLead(
                    team_id=search.team_id,
                    source=lead.source,
                    source_id=lead.source_id,
                    phone_e164=phone_key,
                    domain_root=domain_key,
                    first_user_id=search.user_id,
                )
            )
        else:
            existing_team.phone_e164 = phone_key
            existing_team.domain_root = domain_key


async def unarchive_lead(lead: Lead) -> None:
    """Restore a previously archived lead to the active CRM list.

    Intentionally does NOT clear the ``user_seen_leads`` /
    ``team_seen_leads`` rows that ``archive_lead`` wrote — the
    search-side suppression is permanent by design.
    """
    lead.archived_at = None
