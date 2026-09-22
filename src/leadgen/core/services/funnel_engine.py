"""Funnel execution engine — pure scheduling/outcome logic + the
worker entrypoint for due email touches.

The funnel's touch path lives in ``FunnelStep`` rows; every attached
lead carries (``funnel_step``, ``next_touch_at``, ``no_answer_count``).
This module is the single place that mutates that state:

* :func:`attach_lead` — bind a lead to a funnel and schedule step 0.
* :func:`advance_lead` — after a touch is done, schedule the next.
* :func:`apply_call_outcome` — the one-button outcome from call mode,
  including the funnel's no-answer rule (N tries → pause → free pool).
* :func:`process_due_email_touches` — worker cron: due email steps
  are auto-sent (template + placeholders, suppression honoured) or
  left as a draft activity for the rep's approval.

Framework-agnostic: no FastAPI imports, sessions come in from the
caller (worker or route).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.db.models import (
    Funnel,
    FunnelStep,
    Lead,
    LeadActivity,
    OutreachTemplate,
)

logger = logging.getLogger(__name__)

# Call-mode one-button outcomes (mockup: Недозвон / Неверный номер /
# Отказ / Думает / Перезвонить… / <goal reached>).
CALL_OUTCOMES: tuple[str, ...] = (
    "no_answer",
    "wrong_number",
    "refused",
    "thinking",
    "callback",
    "goal",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _steps_of(funnel: Funnel) -> list[FunnelStep]:
    return sorted(funnel.steps, key=lambda s: s.order_index)


def schedule_step(
    lead: Lead, funnel: Funnel, step_index: int, *, base: datetime | None = None
) -> None:
    """Point the lead at ``step_index`` and stamp when it is due.

    ``day_offset`` is relative to the previous touch (the mockup's
    "+1 день"), so the due time is ``base + offset`` where base is
    "now" right after the previous touch completed.
    """
    steps = _steps_of(funnel)
    if step_index >= len(steps):
        lead.funnel_step = step_index
        lead.next_touch_at = None  # path exhausted
        return
    start = base or _now()
    lead.funnel_step = step_index
    lead.next_touch_at = start + timedelta(days=steps[step_index].day_offset)


def attach_lead(lead: Lead, funnel: Funnel, *, now: datetime | None = None) -> None:
    """Bind a lead to a funnel and schedule its first touch."""
    lead.funnel_id = funnel.id
    lead.no_answer_count = 0
    lead.goal_reached_at = None
    schedule_step(lead, funnel, 0, base=now or _now())


def advance_lead(lead: Lead, funnel: Funnel, *, now: datetime | None = None) -> None:
    """The current step is done — schedule the next one."""
    schedule_step(lead, funnel, lead.funnel_step + 1, base=now or _now())


def apply_call_outcome(
    lead: Lead,
    funnel: Funnel | None,
    outcome: str,
    *,
    callback_at: datetime | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Apply a one-button call outcome to the lead's funnel state.

    Returns a small dict describing what happened (used for the
    activity payload and the API response). Works without a funnel
    too (personal-mode leads) — then only the timestamps move.
    """
    current = now or _now()
    lead.last_touched_at = current
    result: dict[str, Any] = {"outcome": outcome}

    if outcome == "callback":
        when = callback_at or (current + timedelta(days=1))
        lead.next_touch_at = when
        result["next_touch_at"] = when.isoformat()
        return result

    if outcome == "no_answer":
        lead.no_answer_count = (lead.no_answer_count or 0) + 1
        # Column defaults apply at flush time — a transient Funnel may
        # still carry None here, so fall back to the model defaults.
        attempts = (
            funnel.no_answer_attempts
            if funnel is not None and funnel.no_answer_attempts is not None
            else 3
        )
        pause_days = (
            funnel.no_answer_pause_days
            if funnel is not None and funnel.no_answer_pause_days is not None
            else 14
        )
        if lead.no_answer_count >= attempts:
            # Rule: N tries on different days → pause → back to the
            # free pool for re-distribution.
            lead.no_answer_count = 0
            lead.owner_user_id = None
            lead.next_touch_at = current + timedelta(days=pause_days)
            result["paused_days"] = pause_days
            result["released"] = True
        else:
            # Retry on another day.
            lead.next_touch_at = current + timedelta(days=1)
            result["attempt"] = lead.no_answer_count
        return result

    if outcome in ("wrong_number", "refused"):
        lead.next_touch_at = None
        result["terminal"] = True
        return result

    if outcome == "thinking":
        # Warm it up: move to the funnel's next touch (usually the
        # follow-up email drafted right after the call).
        if funnel is not None:
            advance_lead(lead, funnel, now=current)
            result["next_step"] = lead.funnel_step
            if lead.next_touch_at is not None:
                result["next_touch_at"] = lead.next_touch_at.isoformat()
        else:
            lead.next_touch_at = None
        return result

    if outcome == "goal":
        lead.goal_reached_at = current
        lead.next_touch_at = None
        result["goal_reached"] = True
        if funnel is not None:
            result["goal_name"] = funnel.goal_name
            result["goal_action"] = funnel.goal_action
            if funnel.goal_price is not None:
                result["goal_price"] = float(funnel.goal_price)
        return result

    raise ValueError(f"unknown call outcome: {outcome}")


def render_template(
    template: OutreachTemplate, lead: Lead, extra: dict[str, str] | None = None
) -> tuple[str, str]:
    """Substitute the documented ``{name}`` / ``{niche}`` / ``{region}``
    placeholders. Returns (subject, body)."""
    mapping = {
        "name": lead.name or "",
        "niche": (extra or {}).get("niche", ""),
        "region": (extra or {}).get("region", ""),
    }
    subject = template.subject or ""
    body = template.body
    for key, value in mapping.items():
        subject = subject.replace("{" + key + "}", value)
        body = body.replace("{" + key + "}", value)
    return subject, body


async def process_due_email_touches(
    session: AsyncSession, *, now: datetime | None = None, limit: int = 200
) -> dict[str, int]:
    """Worker cron body: execute due EMAIL steps of active funnels.

    * ``auto`` steps with a template and a known recipient → send via
      the transactional sender (suppression honoured) and advance.
    * non-auto steps → write a ``funnel_email_due`` activity (the
      rep's "письма ждут одобрения" surface) and advance the due
      pointer is NOT moved — the touch stays pending until the rep
      sends or skips it from the UI.
    Call steps are ignored here — the call queue surfaces them.
    """
    current = now or _now()
    sent = 0
    drafted = 0
    skipped = 0

    from sqlalchemy.orm import selectinload

    rows = (
        (
            await session.execute(
                select(Lead, Funnel)
                .join(Funnel, Funnel.id == Lead.funnel_id)
                .where(Lead.next_touch_at.is_not(None))
                .where(Lead.next_touch_at <= current)
                .where(Lead.deleted_at.is_(None))
                .where(Funnel.status == "active")
                .options(selectinload(Funnel.steps))
                .limit(limit)
            )
        )
        .all()
    )

    for lead, funnel in rows:
        steps = _steps_of(funnel)
        if lead.funnel_step >= len(steps):
            lead.next_touch_at = None
            continue
        step = steps[lead.funnel_step]
        if step.kind != "email":
            continue  # calls are the queue's job

        recipient = (lead.contact_email or "").strip() or None
        template = (
            await session.get(OutreachTemplate, step.template_id)
            if step.template_id
            else None
        )

        if not step.auto or template is None or recipient is None:
            # Leave for the rep: one pending-approval activity per
            # step (dedup on re-runs — payload check in Python keeps
            # it portable across PG/SQLite).
            actor_id = lead.owner_user_id or funnel.created_by_user_id
            if actor_id is None:
                skipped += 1
                continue
            prior = (
                (
                    await session.execute(
                        select(LeadActivity.payload)
                        .where(LeadActivity.lead_id == lead.id)
                        .where(LeadActivity.kind == "funnel_email_due")
                    )
                )
                .scalars()
                .all()
            )
            already = any(
                isinstance(p, dict) and p.get("step") == str(lead.funnel_step)
                for p in prior
            )
            if not already:
                session.add(
                    LeadActivity(
                        lead_id=lead.id,
                        user_id=actor_id,
                        team_id=funnel.team_id,
                        kind="funnel_email_due",
                        payload={
                            "step": str(lead.funnel_step),
                            "auto": step.auto,
                            "template_id": (
                                str(step.template_id)
                                if step.template_id
                                else None
                            ),
                            "reason": (
                                "approval"
                                if template is not None and recipient
                                else "missing_template_or_email"
                            ),
                        },
                    )
                )
                drafted += 1
            else:
                skipped += 1
            continue

        # Auto send path.
        from leadgen.core.services.email_sender import send_email
        from leadgen.core.services.suppression import is_suppressed

        sender_user_id = lead.owner_user_id or funnel.created_by_user_id
        if sender_user_id is not None and await is_suppressed(
            session, user_id=sender_user_id, email=recipient
        ):
            lead.next_touch_at = None
            skipped += 1
            continue

        subject, body = render_template(template, lead)
        ok = await send_email(
            to=recipient,
            subject=subject or funnel.name,
            html=body.replace("\n", "<br>"),
            text=body,
        )
        if ok:
            if sender_user_id is None:
                # No attributable actor — advance without an activity
                # row rather than violating the FK.
                advance_lead(lead, funnel, now=current)
                sent += 1
                continue
            session.add(
                LeadActivity(
                    lead_id=lead.id,
                    user_id=sender_user_id,
                    team_id=funnel.team_id,
                    kind="funnel_email_sent",
                    payload={
                        "step": str(lead.funnel_step),
                        "template_id": str(template.id),
                        "to": recipient,
                    },
                )
            )
            advance_lead(lead, funnel, now=current)
            sent += 1
        else:
            skipped += 1

    await session.commit()
    return {"sent": sent, "drafted": drafted, "skipped": skipped}
