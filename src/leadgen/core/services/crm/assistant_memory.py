"""Assistant memory store — Henry's continuity between sessions.

Henry keeps two flavours of long-lived memory per user:

- **summary** — a 1-3 sentence recap of a recent dialogue session.
  Written every ``SUMMARY_EVERY_N_USER_MSGS`` user messages.
- **fact** — a single durable statement about the user's business or
  behaviour ("продаёт SEO для дантистов в Берлине", "целевой
  сегмент — премиум"). Several can be written per summarisation pass.

Memories scoped per user; team-mode memories additionally carry a
``team_id`` so coordinators / team owners share Henry's understanding
of the team while every member's personal observations stay private.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.db.models import AssistantMemory

logger = logging.getLogger(__name__)


# How many user messages should accumulate before we trigger a fresh
# summarisation pass. Low enough to keep memory current; high enough
# that we're not paying for an LLM call after every reply.
SUMMARY_EVERY_N_USER_MSGS = 6

# Cap on memories we ship into the system prompt — older ones get
# silently dropped. Recency wins: we order by created_at desc.
MAX_MEMORIES_IN_PROMPT = 20

# Hard cap on stored rows per (user, team) — older entries get pruned
# when we cross this. Prevents unbounded growth on heavy users.
MAX_STORED_PER_SCOPE = 80


async def load_memories(
    session: AsyncSession,
    user_id: int,
    team_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    """Return the most recent memories Henry should see in his prompt.

    In team mode we union the personal memories of the caller with
    every memory carrying the matching ``team_id`` — Henry sees both
    the team's shared notes and what *this specific* user has been
    asking about.
    """
    stmt = select(AssistantMemory).where(AssistantMemory.user_id == user_id)
    if team_id is not None:
        stmt = stmt.where(
            (AssistantMemory.team_id == team_id) | (AssistantMemory.team_id.is_(None))
        )
    else:
        stmt = stmt.where(AssistantMemory.team_id.is_(None))
    stmt = stmt.order_by(desc(AssistantMemory.created_at)).limit(
        MAX_MEMORIES_IN_PROMPT
    )

    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "kind": row.kind,
            "content": row.content,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


async def record_memory(
    session: AsyncSession,
    user_id: int,
    team_id: uuid.UUID | None,
    kind: str,
    content: str,
    meta: dict[str, Any] | None = None,
) -> AssistantMemory:
    """Persist a single memory entry. Caller commits the session."""
    if kind not in {"summary", "fact"}:
        raise ValueError(f"unknown memory kind: {kind!r}")
    cleaned = (content or "").strip()
    if not cleaned:
        raise ValueError("memory content cannot be empty")
    row = AssistantMemory(
        user_id=user_id,
        team_id=team_id,
        kind=kind,
        content=cleaned[:2000],
        meta=meta,
    )
    session.add(row)
    return row


async def prune_old(
    session: AsyncSession,
    user_id: int,
    team_id: uuid.UUID | None,
) -> int:
    """Delete the oldest entries beyond ``MAX_STORED_PER_SCOPE``.

    Returns the number of rows pruned. Keeps Henry's memory bounded
    so a 5-year-old user doesn't drag in 5000 entries on every prompt.
    """
    stmt = select(AssistantMemory).where(AssistantMemory.user_id == user_id)
    if team_id is None:
        stmt = stmt.where(AssistantMemory.team_id.is_(None))
    else:
        stmt = stmt.where(AssistantMemory.team_id == team_id)
    stmt = stmt.order_by(desc(AssistantMemory.created_at))

    rows = (await session.execute(stmt)).scalars().all()
    if len(rows) <= MAX_STORED_PER_SCOPE:
        return 0
    pruned = 0
    for row in rows[MAX_STORED_PER_SCOPE:]:
        await session.delete(row)
        pruned += 1
    return pruned


def should_summarise(history: list[dict[str, str]]) -> bool:
    """Cheap predicate to decide whether the current turn warrants a
    fresh summarisation pass. Triggered when the running count of
    user messages is a positive multiple of the threshold."""
    user_msgs = sum(1 for m in history if m.get("role") == "user")
    return user_msgs > 0 and user_msgs % SUMMARY_EVERY_N_USER_MSGS == 0
