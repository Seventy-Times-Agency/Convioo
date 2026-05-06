"""Adzuna Jobs collector — surfaces companies hiring marketing roles.

Searches Adzuna for active job postings matching marketing/SMM keywords
in a given region. Companies posting these roles are likely spending on
marketing and are good prospects for agency outreach.
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import Any

import httpx

from leadgen.config import get_settings

logger = logging.getLogger(__name__)

# Job titles that signal a company needs marketing agency help
_MARKETING_KEYWORDS = [
    "social media manager",
    "marketing manager",
    "digital marketing",
    "content manager",
    "smm manager",
    "marketing coordinator",
]

_COUNTRY_MAP = {
    "united kingdom": "gb", "uk": "gb", "england": "gb",
    "united states": "us", "usa": "us",
    "canada": "ca", "australia": "au",
    "ukraine": "ua", "germany": "de",
    "france": "fr", "netherlands": "nl",
}


def _detect_country(region: str) -> str:
    region_lower = region.lower()
    for key, code in _COUNTRY_MAP.items():
        if key in region_lower:
            return code
    return "gb"


async def search_hiring_companies(
    niche: str,
    region: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return list of raw lead dicts for companies hiring marketing roles.

    Each dict has: name, website, category, address, source, source_id, tags.
    Never raises — errors are logged and an empty list is returned.
    """
    settings = get_settings()
    if not settings.adzuna_app_id or not settings.adzuna_api_key:
        return []

    country = _detect_country(region)
    results: list[dict[str, Any]] = []
    seen_companies: set[str] = set()

    async with httpx.AsyncClient(timeout=10.0) as client:
        for keyword in _MARKETING_KEYWORDS[:3]:  # cap at 3 keywords to limit API calls
            try:
                resp = await client.get(
                    f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
                    params={
                        "app_id": settings.adzuna_app_id,
                        "app_key": settings.adzuna_api_key,
                        "what": keyword,
                        "where": region,
                        "results_per_page": 10,
                        "content-type": "application/json",
                    },
                )
                if resp.status_code != 200:
                    continue

                jobs = resp.json().get("results", [])
                for job in jobs:
                    company = job.get("company", {}).get("display_name", "")
                    if not company or company.lower() in seen_companies:
                        continue
                    seen_companies.add(company.lower())

                    location = job.get("location", {}).get("display_name", region)
                    redirect_url = job.get("redirect_url", "")
                    posted_days = job.get("created", "")

                    results.append({
                        "name": company,
                        "category": niche,
                        "address": location,
                        "phone": None,
                        "website": None,
                        "rating": None,
                        "reviews_count": None,
                        "latitude": None,
                        "longitude": None,
                        "source": "adzuna",
                        "source_id": f"adzuna_{urllib.parse.quote(company)}_{country}",
                        "raw": {
                            "job_title": job.get("title", ""),
                            "redirect_url": redirect_url,
                            "keyword": keyword,
                            "posted": posted_days,
                        },
                        "tags": ["Нанимают маркетолога"],
                    })

                    if len(results) >= limit:
                        return results

            except Exception:
                logger.warning(
                    "adzuna: request failed keyword=%r region=%r",
                    keyword,
                    region,
                    exc_info=True,
                )
                continue

    logger.info("adzuna: found %d companies region=%r", len(results), region)
    return results
