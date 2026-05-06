"""Companies House (UK) collector — finds recently registered businesses.

Queries the free Companies House API for companies registered in the
last 6 months matching the search niche. No API key required.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://api.company-information.service.gov.uk"
_NEW_BIZ_MONTHS = 6


async def search_new_businesses(
    niche: str,
    region: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return recently registered UK companies matching *niche*.

    Only companies incorporated within the last 6 months are returned.
    Never raises — errors are logged and an empty list is returned.
    """
    cutoff = date.today() - timedelta(days=_NEW_BIZ_MONTHS * 30)
    results: list[dict[str, Any]] = []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{_BASE}/search/companies",
                params={"q": niche, "items_per_page": 50},
            )
            if resp.status_code != 200:
                logger.warning("companies_house: status=%d", resp.status_code)
                return []

            items = resp.json().get("items", [])

        for item in items:
            inc_date_str = item.get("date_of_creation", "")
            if not inc_date_str:
                continue
            try:
                inc_date = date.fromisoformat(inc_date_str)
            except ValueError:
                continue

            if inc_date < cutoff:
                continue  # too old

            status = (item.get("company_status") or "").lower()
            if status not in ("active", ""):
                continue

            name = item.get("title", "")
            address = item.get("address_snippet", region)
            company_number = item.get("company_number", "")
            months_old = (date.today() - inc_date).days // 30

            results.append({
                "name": name,
                "category": niche,
                "address": address,
                "phone": None,
                "website": None,
                "rating": None,
                "reviews_count": None,
                "latitude": None,
                "longitude": None,
                "source": "companies_house",
                "source_id": f"ch_{company_number}",
                "raw": {
                    "company_number": company_number,
                    "incorporation_date": inc_date_str,
                    "months_old": months_old,
                },
                "tags": [f"New business ({months_old} mo.)"],
            })

            if len(results) >= limit:
                break

    except Exception:
        logger.warning("companies_house: request failed niche=%r", niche, exc_info=True)

    logger.info("companies_house: found %d new businesses niche=%r", len(results), niche)
    return results
