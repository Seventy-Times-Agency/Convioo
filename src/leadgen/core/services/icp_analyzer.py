"""ICP (Ideal Customer Profile) analyzer — extracts patterns from client CSV."""
from __future__ import annotations

import csv
import io
import json
import logging
from typing import Any

import anthropic

from leadgen.config import get_settings

logger = logging.getLogger(__name__)

_SYSTEM = """You are a business analyst. The user will give you a list of their best clients.
Extract the Ideal Customer Profile (ICP) as a JSON object with these fields:
- industries: list of top 3-5 industry types (e.g. ["roofing", "plumbing", "HVAC"])
- typical_size: one of "micro" (1-5 staff), "small" (5-20), "medium" (20-100)
- pain_points: list of top 3 pain points these businesses have (marketing-related)
- avg_rating_range: [min, max] typical Google rating range (e.g. [3.5, 4.2])
- locations: list of city/region patterns if obvious (e.g. ["London", "Manchester"])
- keywords: list of 5-10 search keywords that would find similar businesses
- notes: 1-2 sentences about what makes these clients ideal

Respond ONLY with valid JSON. No explanation, no markdown."""


async def analyze_client_csv(csv_content: str) -> dict[str, Any]:
    """Parse CSV and extract ICP via Claude. Returns ICP dict.

    CSV can have any columns — just dumps the content as text for Claude.
    Raises ValueError if CSV is empty or Claude returns invalid JSON.
    """
    reader = csv.reader(io.StringIO(csv_content))
    rows = list(reader)
    if len(rows) < 2:
        raise ValueError("CSV must have at least one data row")

    headers = rows[0]
    data_rows = rows[1:51]
    lines = [", ".join(f"{h}: {v}" for h, v in zip(headers, row)) for row in data_rows]
    clients_text = "\n".join(lines)

    client = anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key)
    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": f"Here are my best clients:\n\n{clients_text}\n\nExtract the ICP.",
            }
        ],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("icp_analyzer: Claude returned invalid JSON: %s", raw[:200])
        raise ValueError("Claude returned invalid JSON") from exc
