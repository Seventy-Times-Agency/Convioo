"""Decision-maker lookup — 3-level waterfall: website HTML → OpenCorporates → ProxyCurl."""
from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Any

import httpx
from bs4 import BeautifulSoup

from leadgen.config import get_settings

logger = logging.getLogger(__name__)

_TITLE_RE = re.compile(
    r"\b(Owner|Founder|CEO|Director|Managing\s+Partner|Proprietor|President)\b",
    re.IGNORECASE,
)
_NAME_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b")


async def find_decision_maker(
    lead_name: str,
    website_html: str | None,
    social_links: dict[str, Any],
) -> dict[str, Any] | None:
    """Return {name, title, source, source_label} or None."""

    # Step 1 — website HTML parsing
    if website_html:
        result = _parse_html(website_html)
        if result:
            return result

    # Step 2 — OpenCorporates (free)
    result = await _opencorporates(lead_name)
    if result:
        return result

    # Step 3 — ProxyCurl (paid, optional)
    linkedin_url = social_links.get("linkedin")
    if linkedin_url and get_settings().proxycurl_api_key:
        result = await _proxycurl(linkedin_url)
        if result:
            return result

    return None


def _parse_html(html: str) -> dict[str, Any] | None:
    try:
        soup = BeautifulSoup(html[:200_000], "html.parser")
        for tag in soup.find_all(["h2", "h3", "h4", "strong", "b", "p"]):
            text = tag.get_text(" ", strip=True)
            if not _TITLE_RE.search(text):
                continue
            title_match = _TITLE_RE.search(text)
            name_match = _NAME_RE.search(text)
            if name_match and title_match:
                return {
                    "name": name_match.group(0),
                    "title": title_match.group(0).title(),
                    "source": "website",
                    "source_label": "Website",
                }
    except Exception:
        logger.warning("decision_maker: HTML parse error", exc_info=True)
    return None


async def _opencorporates(company_name: str) -> dict[str, Any] | None:
    if not company_name:
        return None
    url = (
        "https://api.opencorporates.com/v0.4/companies/search"
        f"?q={urllib.parse.quote(company_name)}&format=json"
    )
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return None
        companies = resp.json().get("results", {}).get("companies", [])
        if not companies:
            return None
        officers = companies[0].get("company", {}).get("officers", [])
        for officer in officers:
            pos = (officer.get("position") or "").lower()
            if any(kw in pos for kw in ("director", "owner", "secretary", "president")):
                return {
                    "name": officer.get("name", ""),
                    "title": officer.get("position", ""),
                    "source": "opencorporates",
                    "source_label": "OpenCorporates",
                }
    except Exception:
        logger.warning("decision_maker: OpenCorporates request failed", exc_info=True)
    return None


async def _proxycurl(linkedin_url: str) -> dict[str, Any] | None:
    api_key = get_settings().proxycurl_api_key
    if not api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://nubela.co/proxycurl/api/linkedin/company/employees/",
                params={
                    "linkedin_company_profile_url": linkedin_url,
                    "role_search": "owner",
                    "page_size": 1,
                },
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if resp.status_code != 200:
            return None
        employees = resp.json().get("employees", [])
        if employees:
            emp = employees[0].get("profile", {})
            name = f"{emp.get('first_name', '')} {emp.get('last_name', '')}".strip()
            if name:
                return {
                    "name": name,
                    "title": emp.get("headline", "LinkedIn"),
                    "source": "proxycurl",
                    "source_label": "LinkedIn (ProxyCurl)",
                }
    except Exception:
        logger.warning("decision_maker: ProxyCurl request failed", exc_info=True)
    return None
