"""Cross-route helpers shared by extracted ``APIRouter`` modules.

These were ``app.py`` module-level functions; lifting them here keeps
the per-domain route files free of upward imports into ``app.py``,
which would create a cycle (``app.py`` imports the routers).

Add helpers here only when at least two route modules need them. One-
off helpers belong inside their owning route module.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.db.models import LeadTag, TeamMembership


async def membership(
    session: AsyncSession, team_id: uuid.UUID, user_id: int
) -> TeamMembership | None:
    """Return the user's membership row in a team, or ``None``."""
    result = await session.execute(
        select(TeamMembership)
        .where(TeamMembership.team_id == team_id)
        .where(TeamMembership.user_id == user_id)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def can_manage_tag(
    session: AsyncSession, tag: LeadTag, user_id: int
) -> bool:
    """Personal tags belong to one user; team tags need membership."""
    if tag.team_id is None:
        return tag.user_id == user_id
    return (await membership(session, tag.team_id, user_id)) is not None
