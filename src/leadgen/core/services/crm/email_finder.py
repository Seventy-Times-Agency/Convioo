"""Hunter.io email finder — waterfall fallback when website scraping yields no email."""
from __future__ import annotations

import logging
import urllib.parse

import httpx

from leadgen.config import get_settings

logger = logging.getLogger(__name__)


async def find_email(domain: str) -> str | None:
    """Return the first email found for *domain* via Hunter.io, or None.

    Returns None immediately if the Hunter API key is not configured.
    Never raises — all errors are logged as warnings.
    """
    api_key = get_settings().hunter_api_key
    if not api_key or not domain:
        return None

    url = (
        "https://api.hunter.io/v2/email-finder"
        f"?domain={urllib.parse.quote(domain)}&api_key={api_key}"
    )
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return None
        email = resp.json().get("data", {}).get("email")
        return email if email else None
    except Exception:
        logger.warning("email_finder: Hunter.io request failed domain=%s", domain, exc_info=True)
        return None
