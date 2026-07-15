"""AI classification of inbound email replies.

The reply tracker (:mod:`leadgen.core.services.email_reply_tracker`) detects
that a lead answered one of our outreach emails, but on its own it can't tell
an enthusiastic "yes, let's talk" from an out-of-office bounce or an angry
"remove me". This module runs the reply body through Claude Haiku and returns a
small structured verdict the tracker can act on:

- ``category`` — one of :data:`REPLY_CATEGORIES`
- ``sentiment`` — ``positive`` / ``neutral`` / ``negative``
- ``confidence`` — 0.0-1.0
- ``summary`` — one short sentence for the activity feed
- ``suggested_reply`` — a drafted response the user can send back (may be empty)

Everything degrades gracefully: with no API key, or on any API/parse error, we
return a neutral ``other`` verdict so the caller behaves exactly as it did
before classification existed. Better to skip a classification than to crash the
worker tick or mislabel a lead.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from leadgen.config import get_settings

logger = logging.getLogger(__name__)

# The categories Claude is allowed to return. Keep this list and the routing
# table (:data:`CATEGORY_ROUTING`) in sync.
REPLY_CATEGORIES = (
    "interested",  # wants to move forward / positive intent
    "meeting_request",  # explicitly asks for a call/demo/meeting
    "question",  # asks a question, needs info before deciding
    "objection",  # pushback on price/timing/fit but not a hard no
    "not_interested",  # polite or blunt decline
    "unsubscribe",  # asks to be removed / stop emailing
    "auto_reply",  # out-of-office, autoresponder, "I'm on leave"
    "referral",  # "talk to my colleague instead" / forwards to someone
    "other",  # anything that doesn't fit / could not classify
)

# What the tracker should do with each category. Kept here so the policy lives
# next to the taxonomy, not scattered through the worker.
#   suppress      -> add the sender to the do-not-contact list
#   lead_status   -> desired lead status, or None to leave it untouched
#   not_a_reply   -> True when this shouldn't count as a genuine human reply
#                    (auto-responders), so we don't nudge the lead to "replied"
CATEGORY_ROUTING: dict[str, dict[str, Any]] = {
    "interested": {"suppress": False, "lead_status": "replied", "not_a_reply": False},
    "meeting_request": {"suppress": False, "lead_status": "replied", "not_a_reply": False},
    "question": {"suppress": False, "lead_status": "replied", "not_a_reply": False},
    "objection": {"suppress": False, "lead_status": "replied", "not_a_reply": False},
    "not_interested": {"suppress": False, "lead_status": "lost", "not_a_reply": False},
    "unsubscribe": {"suppress": True, "lead_status": "lost", "not_a_reply": False},
    "auto_reply": {"suppress": False, "lead_status": None, "not_a_reply": True},
    "referral": {"suppress": False, "lead_status": "replied", "not_a_reply": False},
    "other": {"suppress": False, "lead_status": "replied", "not_a_reply": False},
}

_SYSTEM = """You classify replies that leads send to B2B sales outreach emails.

Return ONLY a JSON object (no markdown, no prose) with exactly these fields:
- "category": one of ["interested","meeting_request","question","objection","not_interested","unsubscribe","auto_reply","referral","other"]
- "sentiment": one of ["positive","neutral","negative"]
- "confidence": a number between 0 and 1
- "summary": one short sentence (max 120 chars) describing the reply
- "suggested_reply": a short, professional draft the sender could send back. Empty string for auto_reply, unsubscribe, or not_interested.

Category guidance:
- interested: shows positive buying intent, wants to learn more.
- meeting_request: explicitly asks for a call, demo, or meeting.
- question: asks something and needs an answer before deciding.
- objection: pushes back on price, timing, or fit, but not a hard no.
- not_interested: declines, politely or bluntly.
- unsubscribe: asks to be removed, to stop emailing, or says "do not contact".
- auto_reply: out-of-office, autoresponder, vacation notice, no human intent.
- referral: redirects you to a colleague or another contact.
- other: none of the above, or too little signal to tell.

Be conservative: if unsure between not_interested and unsubscribe, and the reply
demands removal or threatens spam reports, choose unsubscribe."""

_NEUTRAL: dict[str, Any] = {
    "category": "other",
    "sentiment": "neutral",
    "confidence": 0.0,
    "summary": "",
    "suggested_reply": "",
}


def _coerce(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate/normalize Claude's JSON into the shape callers rely on."""
    category = str(raw.get("category") or "other").strip().lower()
    if category not in REPLY_CATEGORIES:
        category = "other"
    sentiment = str(raw.get("sentiment") or "neutral").strip().lower()
    if sentiment not in ("positive", "neutral", "negative"):
        sentiment = "neutral"
    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    summary = str(raw.get("summary") or "").strip()[:200]
    suggested = str(raw.get("suggested_reply") or "").strip()
    return {
        "category": category,
        "sentiment": sentiment,
        "confidence": confidence,
        "summary": summary,
        "suggested_reply": suggested,
    }


async def classify_reply(
    body_text: str,
    *,
    subject: str | None = None,
    lead_name: str | None = None,
) -> dict[str, Any]:
    """Classify a single inbound reply. Never raises.

    Returns a dict with ``category``, ``sentiment``, ``confidence``,
    ``summary`` and ``suggested_reply``. Falls back to a neutral ``other``
    verdict when the API key is missing, the body is empty, or the call fails.
    """
    text = (body_text or "").strip()
    if not text:
        return dict(_NEUTRAL)

    settings = get_settings()
    api_key = getattr(settings, "anthropic_api_key", None)
    if not api_key:
        return dict(_NEUTRAL)

    # Keep the prompt bounded — the first ~2k chars carry the intent; long
    # quoted threads below just cost tokens.
    snippet = text[:2000]
    context = []
    if subject:
        context.append(f"Original subject: {subject}")
    if lead_name:
        context.append(f"Lead / company: {lead_name}")
    header = ("\n".join(context) + "\n\n") if context else ""

    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        message = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": f"{header}Reply body:\n\n{snippet}",
                }
            ],
        )
    except Exception as exc:  # noqa: BLE001 - never let classification crash the tick
        logger.warning("reply_classifier: Claude call failed: %s", exc)
        return dict(_NEUTRAL)

    block = next(
        (b for b in (message.content or []) if getattr(b, "text", None)), None
    )
    if block is None:
        return dict(_NEUTRAL)
    raw = block.text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("reply_classifier: invalid JSON: %s", raw[:200])
        return dict(_NEUTRAL)
    if not isinstance(parsed, dict):
        return dict(_NEUTRAL)
    return _coerce(parsed)


def routing_for(category: str) -> dict[str, Any]:
    """Return the routing policy for a category (safe default for unknowns)."""
    return CATEGORY_ROUTING.get(category, CATEGORY_ROUTING["other"])
