"""ICP refinement: surface user's fit / not-fit votes to the AI prompts.

Convioo's pitch over generic scoring tools (Apollo, Clay) is that the
scorer adapts to *your* taste, not a one-size-fits-all formula. This
service is the storage + retrieval layer; the AIAnalyzer does the
adaptation by injecting recent verdicts into its system prompts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.db.models import Lead, LeadFeedback

VERDICT_FIT = "fit"
VERDICT_NOT_FIT = "not_fit"
VALID_VERDICTS = frozenset({VERDICT_FIT, VERDICT_NOT_FIT})


@dataclass(slots=True, frozen=True)
class FeedbackExample:
    """One past verdict, with enough lead context for prompt injection."""

    verdict: str
    lead_name: str
    lead_summary: str | None
    lead_category: str | None
    lead_address: str | None
    reason: str | None


@dataclass(slots=True, frozen=True)
class ICPSnapshot:
    """Aggregate the user can render in the UI."""

    fit_count: int
    not_fit_count: int
    recent_examples: list[FeedbackExample]


async def upsert_verdict(
    session: AsyncSession,
    *,
    user_id: int,
    lead_id,
    verdict: str,
    reason: str | None,
) -> LeadFeedback:
    """Insert or update the verdict for this (user_id, lead_id)."""
    if verdict not in VALID_VERDICTS:
        raise ValueError(f"verdict must be one of {sorted(VALID_VERDICTS)}")
    existing = (
        await session.execute(
            select(LeadFeedback)
            .where(LeadFeedback.user_id == user_id)
            .where(LeadFeedback.lead_id == lead_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if existing is None:
        row = LeadFeedback(
            user_id=user_id,
            lead_id=lead_id,
            verdict=verdict,
            reason=reason,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        await session.flush()
        return row
    existing.verdict = verdict
    existing.reason = reason
    existing.updated_at = now
    await session.flush()
    return existing


async def clear_verdict(
    session: AsyncSession, *, user_id: int, lead_id
) -> bool:
    row = (
        await session.execute(
            select(LeadFeedback)
            .where(LeadFeedback.user_id == user_id)
            .where(LeadFeedback.lead_id == lead_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.flush()
    return True


async def get_user_verdict(
    session: AsyncSession, *, user_id: int, lead_id
) -> str | None:
    row = (
        await session.execute(
            select(LeadFeedback.verdict)
            .where(LeadFeedback.user_id == user_id)
            .where(LeadFeedback.lead_id == lead_id)
            .limit(1)
        )
    ).first()
    return row[0] if row else None


async def snapshot_for_user(
    session: AsyncSession,
    *,
    user_id: int,
    examples_per_side: int = 5,
) -> ICPSnapshot:
    """Counts + a few recent representative leads on each side.

    Used both for the SPA's "Henry знает: N fit / M not-fit" chip and
    for the AI prompt injection. Examples are joined to ``leads`` so
    the prompt can name them ("you liked Acme Plumbing in Brooklyn").
    """
    rows = (
        (
            await session.execute(
                select(
                    LeadFeedback.verdict,
                    LeadFeedback.reason,
                    Lead.name,
                    Lead.summary,
                    Lead.category,
                    Lead.address,
                )
                .join(Lead, Lead.id == LeadFeedback.lead_id)
                .where(LeadFeedback.user_id == user_id)
                .order_by(LeadFeedback.updated_at.desc())
            )
        )
        .all()
    )

    fit: list[FeedbackExample] = []
    not_fit: list[FeedbackExample] = []
    for verdict, reason, name, summary, category, address in rows:
        bucket = fit if verdict == VERDICT_FIT else not_fit
        if len(bucket) >= examples_per_side:
            continue
        bucket.append(
            FeedbackExample(
                verdict=verdict,
                lead_name=name,
                lead_summary=summary,
                lead_category=category,
                lead_address=address,
                reason=reason,
            )
        )

    fit_count = sum(1 for r in rows if r[0] == VERDICT_FIT)
    not_fit_count = sum(1 for r in rows if r[0] == VERDICT_NOT_FIT)
    return ICPSnapshot(
        fit_count=fit_count,
        not_fit_count=not_fit_count,
        recent_examples=fit + not_fit,
    )


def render_icp_block(snapshot: ICPSnapshot) -> str:
    """Compact text block dropped into AI system prompts.

    Returns an empty string when the user hasn't given any feedback —
    we don't want to nudge Claude into making things up.
    """
    if not snapshot.recent_examples:
        return ""
    lines = [
        "ОБРАТНАЯ СВЯЗЬ ЭТОГО ЮЗЕРА (на основе оценок прошлых лидов):",
        f"  всего fit: {snapshot.fit_count}, not-fit: {snapshot.not_fit_count}",
    ]
    fits = [e for e in snapshot.recent_examples if e.verdict == VERDICT_FIT]
    nots = [e for e in snapshot.recent_examples if e.verdict == VERDICT_NOT_FIT]
    if fits:
        lines.append("  Понравились:")
        for ex in fits:
            tail = []
            if ex.lead_category:
                tail.append(ex.lead_category)
            if ex.lead_address:
                tail.append(ex.lead_address)
            if ex.reason:
                tail.append(f"причина: {ex.reason}")
            tail_text = f" ({', '.join(tail)})" if tail else ""
            lines.append(f"    - {ex.lead_name}{tail_text}")
    if nots:
        lines.append("  Не понравились:")
        for ex in nots:
            tail = []
            if ex.lead_category:
                tail.append(ex.lead_category)
            if ex.lead_address:
                tail.append(ex.lead_address)
            if ex.reason:
                tail.append(f"причина: {ex.reason}")
            tail_text = f" ({', '.join(tail)})" if tail else ""
            lines.append(f"    - {ex.lead_name}{tail_text}")
    lines.append(
        "  ВАЖНО: используй эти примеры как ориентир что для этого "
        "юзера работает / не работает. Это его реальная ICP."
    )
    return "\n".join(lines)
