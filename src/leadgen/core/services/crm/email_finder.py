"""Hunter.io fallback — a company email when the site gave none.

Hunter's ``email-finder`` wants a person's name and answers 400 to a
bare domain (that is what happened on every lead in production). For
"any address at this company" the right call is ``domain-search``; it
costs one credit per request, so it's gated by the free ``email-count``
probe and asked for a single result.
"""
from __future__ import annotations

import logging

import httpx

from leadgen.config import get_settings
from leadgen.core.services.search import usage_tracker

logger = logging.getLogger(__name__)

_COUNT_URL = "https://api.hunter.io/v2/email-count"
_SEARCH_URL = "https://api.hunter.io/v2/domain-search"


async def find_email(domain: str) -> str | None:
    """Return one email found for *domain* via Hunter.io, or None.

    Returns None immediately if the Hunter API key is not configured.
    Never raises — all errors are logged as warnings.
    """
    api_key = get_settings().hunter_api_key
    if not api_key or not domain:
        return None
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            count = await client.get(
                _COUNT_URL, params={"domain": domain, "api_key": api_key}
            )
            if count.status_code != 200:
                return None
            total = int(((count.json().get("data") or {}).get("total")) or 0)
            if total <= 0:
                return None
            resp = await client.get(
                _SEARCH_URL,
                params={"domain": domain, "limit": 1, "api_key": api_key},
            )
            await usage_tracker.record("hunter_credit", 1)
        if resp.status_code != 200:
            logger.warning(
                "email_finder: Hunter domain-search %s for %s",
                resp.status_code,
                domain,
            )
            return None
        emails = ((resp.json().get("data") or {}).get("emails")) or []
        for item in emails:
            value = (item.get("value") or "").strip()
            if value:
                return value
        return None
    except Exception:
        logger.warning(
            "email_finder: Hunter.io request failed domain=%s", domain, exc_info=True
        )
        return None
