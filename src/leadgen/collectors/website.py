"""Website collector: fetch a business homepage and extract structured info.

Pulls title, meta description, contacts (emails/phones), social-network links,
plus a short text snippet for downstream AI analysis.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from leadgen.config import get_settings
from leadgen.utils import retry_async

logger = logging.getLogger(__name__)


SOCIAL_PATTERNS: dict[str, re.Pattern[str]] = {
    "vk": re.compile(r"https?://(?:www\.|m\.)?vk\.(?:com|ru)/[A-Za-z0-9_.\-]+", re.I),
    "instagram": re.compile(r"https?://(?:www\.)?instagram\.com/[A-Za-z0-9_.\-]+", re.I),
    "facebook": re.compile(r"https?://(?:www\.|m\.)?facebook\.com/[A-Za-z0-9_.\-]+", re.I),
    "telegram": re.compile(r"https?://(?:www\.)?t\.me/[A-Za-z0-9_]+", re.I),
    "youtube": re.compile(
        r"https?://(?:www\.)?youtube\.com/(?:channel|user|c|@)[A-Za-z0-9_./\-]+",
        re.I,
    ),
    "whatsapp": re.compile(r"https?://(?:wa\.me|api\.whatsapp\.com/send\?phone=)[0-9]+", re.I),
    "linkedin": re.compile(
        r"https?://(?:www\.)?linkedin\.com/(?:in|company)/[A-Za-z0-9_\-]+", re.I
    ),
    "tiktok": re.compile(r"https?://(?:www\.)?tiktok\.com/@[A-Za-z0-9_.]+", re.I),
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(
    r"(?:\+7|8|\+\d{1,3})[\s\-()]*\d{2,4}[\s\-()]*\d{2,4}[\s\-()]*\d{2,4}[\s\-()]*\d{0,4}"
)

# Generic inbox names (local-part) that rarely reach a decision-maker.
# Filtered out so the lead card shows something actually useful to write to.
_GENERIC_EMAIL_LOCALS = frozenset(
    {
        "info",
        "hello",
        "hi",
        "contact",
        "contacts",
        "support",
        "help",
        "admin",
        "office",
        "mail",
        "email",
        "team",
        "noreply",
        "no-reply",
        "donotreply",
        "do-not-reply",
        "reply",
        "sales",  # kept loose; a user selling to sales leads might disagree
        "enquiry",
        "enquiries",
        "inquiry",
        "inquiries",
        "feedback",
        "marketing",
        "pr",
        "webmaster",
        "postmaster",
        "abuse",
        "privacy",
        "legal",
    }
)


def _is_generic_email(email: str) -> bool:
    local = email.split("@", 1)[0].lower()
    # Match on exact local-part or local that starts with a generic name
    # followed by a common separator ("info-uk", "support.en", "sales+usa").
    if local in _GENERIC_EMAIL_LOCALS:
        return True
    for prefix in _GENERIC_EMAIL_LOCALS:
        if local.startswith(prefix) and len(local) > len(prefix):
            sep = local[len(prefix)]
            if sep in "-_.+":
                return True
    return False

PRICING_HINTS = ("цен", "тариф", "прайс", "стоимост", "price", "pricing")
PORTFOLIO_HINTS = ("портфолио", "наши работ", "кейс", "portfolio", "case")
BLOG_HINTS = ("блог", "новост", "стать", "blog", "news", "article")

# Heuristic signals we extract on top of the basics. None of these
# cost a Claude call — pure regex on combined site text. Their job is
# to give the downstream AI prompts (analyze_lead, draft_lead_email)
# richer per-lead context so emails sound like the sender actually
# read the prospect's site.
HIRING_HINTS = (
    "we are hiring",
    "we're hiring",
    "join our team",
    "open positions",
    "join us",
    "ищем",
    "вакансии",
    "присоединяйся",
)
# "Founded in 2014", "Since 1998", "Established 2003", "Est. 2017",
# "© 2010-2024 ...". One of these usually appears in the footer.
FOUNDED_RE = re.compile(
    r"(?:founded\s+(?:in\s+)?|since\s+|established\s+(?:in\s+)?|est\.?\s+|основан[аы]?\s+в\s+|"
    r"©\s*\d{4}\s*[\-–]\s*)(\d{4})",
    re.I,
)
# "We are 25 people", "Team of 50+", "Команда из 12 человек".
TEAM_SIZE_RE = re.compile(
    r"(?:team of|we are|our team has|команда из|нас в команде)[\s\D]*?(\d{1,4})\+?\s*(?:people|employees|members|человек|сотрудник)",
    re.I,
)

EXTRA_PATHS = [
    "/contacts",
    "/contact",
    "/about",
    "/about-us",
    "/team",
    "/our-team",
    "/services",
    "/careers",
    "/jobs",
    "/clients",
    "/customers",
    "/case-studies",
    "/portfolio",
    "/work",
]


@dataclass(slots=True)
class WebsiteInfo:
    url: str
    status_code: int = 0
    ok: bool = False
    is_https: bool = False
    title: str | None = None
    description: str | None = None
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    social_links: dict[str, str] = field(default_factory=dict)
    main_text: str | None = None
    has_pricing: bool = False
    has_portfolio: bool = False
    has_blog: bool = False
    # Heuristic signals lifted from the combined site text. Used by
    # downstream Claude prompts to ground cold-email personalisation.
    founded_year: int | None = None
    team_size_hint: int | None = None
    is_hiring: bool = False
    headings: list[str] = field(default_factory=list)
    error: str | None = None


class WebsiteCollector:
    """Async fetcher with sensible defaults for arbitrary business sites."""

    USER_AGENT = "Mozilla/5.0 (compatible; LeadgenBot/1.0; +https://github.com/leadgen)"

    def __init__(self, timeout: float = 10.0, max_bytes: int = 500_000) -> None:
        self.timeout = timeout
        self.max_bytes = max_bytes

    async def fetch(self, url: str | None) -> WebsiteInfo:
        if not url:
            return WebsiteInfo(url="", error="no url")

        normalised = self._normalise_url(url)
        info = WebsiteInfo(url=normalised, is_https=normalised.startswith("https"))

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": self.USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "ru,en;q=0.9",
                },
            ) as client:
                async def do_root_request() -> httpx.Response:
                    return await client.get(normalised)

                root_resp = await retry_async(
                    do_root_request,
                    retries=get_settings().http_retries,
                    base_delay=get_settings().http_retry_base_delay,
                    retry_on=(httpx.HTTPError,),
                )
                info.status_code = root_resp.status_code
                if root_resp.status_code != 200:
                    info.error = f"http {root_resp.status_code}"
                    return info

                content_type = root_resp.headers.get("content-type", "")
                if "html" not in content_type.lower():
                    info.error = f"non-html content-type: {content_type}"
                    return info

                html_blobs: list[str] = [root_resp.text[: self.max_bytes]]
                extra_urls = [urljoin(normalised, path) for path in EXTRA_PATHS]
                extra_responses = await self._fetch_extra_pages(client, extra_urls)
                html_blobs.extend(extra_responses)

                self._parse_html(html_blobs, info)
                info.ok = True
                return info

        except httpx.TimeoutException:
            info.error = "timeout"
        except httpx.HTTPError as exc:
            info.error = f"http error: {exc.__class__.__name__}"
        except Exception as exc:  # noqa: BLE001
            logger.exception("website.fetch unexpected for %s", normalised)
            info.error = f"unexpected: {exc.__class__.__name__}"
        return info

    async def _fetch_extra_pages(self, client: httpx.AsyncClient, urls: list[str]) -> list[str]:
        sem = asyncio.Semaphore(4)

        async def fetch_one(url: str) -> str | None:
            async with sem:
                try:
                    async def do_extra_request() -> httpx.Response:
                        return await client.get(url)

                    resp = await retry_async(
                        do_extra_request,
                        retries=get_settings().http_retries,
                        base_delay=get_settings().http_retry_base_delay,
                        retry_on=(httpx.HTTPError,),
                    )
                    if resp.status_code != 200:
                        return None
                    content_type = resp.headers.get("content-type", "")
                    if "html" not in content_type.lower():
                        return None
                    return resp.text[: self.max_bytes]
                except Exception:  # noqa: BLE001
                    return None

        results = await asyncio.gather(*[fetch_one(url) for url in urls])
        return [page for page in results if page]

    def _parse_html(self, html_blobs: list[str], info: WebsiteInfo) -> None:
        if not html_blobs:
            return

        primary_soup = BeautifulSoup(html_blobs[0], "html.parser")
        info.title = self._extract_title(primary_soup)
        info.description = self._extract_description(primary_soup)

        combined_html = "\n".join(html_blobs)
        combined_soup = BeautifulSoup(combined_html, "html.parser")
        info.main_text = self._extract_main_text(combined_soup)[:2000]

        info.social_links = self._extract_socials(combined_html)
        raw_emails = EMAIL_RE.findall(combined_html)
        # Drop info@/noreply@-style addresses: they rarely reach the
        # decision-maker we're actually trying to contact.
        real_emails = [e for e in raw_emails if not _is_generic_email(e)]
        # Keep a small generic fallback only if we found nothing personal.
        if not real_emails and raw_emails:
            real_emails = raw_emails[:1]
        info.emails = self._dedupe_limit(real_emails, 7)

        phones = [
            re.sub(r"\s+", " ", p).strip()
            for p in PHONE_RE.findall(combined_html)
            if sum(c.isdigit() for c in p) >= 10
        ]
        info.phones = self._dedupe_limit(phones, 7)

        nav_text = self._extract_nav(combined_soup).lower()
        info.has_pricing = any(h in nav_text for h in PRICING_HINTS)
        info.has_portfolio = any(h in nav_text for h in PORTFOLIO_HINTS)
        info.has_blog = any(h in nav_text for h in BLOG_HINTS)

        # Heuristic facts. Cheap signals — no Claude call. These flow
        # into the cold-email prompt so messages can mention "I see
        # you've been at it since 2008" or "noticed you're hiring".
        info.headings = self._extract_headings(primary_soup)
        info.founded_year = self._extract_founded_year(combined_html)
        info.team_size_hint = self._extract_team_size(combined_html)
        info.is_hiring = self._detect_hiring(combined_html, nav_text)

    @staticmethod
    def _normalise_url(url: str) -> str:
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        parsed = urlparse(url)
        if not parsed.netloc:
            return url
        return url

    @staticmethod
    def _dedupe_limit(items: list[str], limit: int) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> str | None:
        if soup.title and soup.title.string:
            return soup.title.string.strip()[:200]
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            return str(og["content"]).strip()[:200]
        return None

    @staticmethod
    def _extract_description(soup: BeautifulSoup) -> str | None:
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            return str(meta["content"]).strip()[:500]
        og = soup.find("meta", property="og:description")
        if og and og.get("content"):
            return str(og["content"]).strip()[:500]
        return None

    @staticmethod
    def _extract_main_text(soup: BeautifulSoup) -> str:
        for tag in soup(["script", "style", "noscript", "iframe", "svg"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        return re.sub(r"\s+", " ", text)

    @staticmethod
    def _extract_nav(soup: BeautifulSoup) -> str:
        parts: list[str] = []
        for tag in soup.find_all(["nav", "header", "footer"]):
            parts.append(tag.get_text(separator=" ", strip=True))
        for link in soup.find_all("a", href=True):
            text = link.get_text(strip=True)
            if text:
                parts.append(text)
            href = link.get("href", "")
            if href:
                parts.append(str(href))
        return " ".join(parts)

    @staticmethod
    def _extract_socials(html: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for key, pattern in SOCIAL_PATTERNS.items():
            match = pattern.search(html)
            if match:
                result[key] = match.group(0)
        return result

    @staticmethod
    def _extract_headings(soup: BeautifulSoup) -> list[str]:
        """Top H1/H2 strings from the homepage — usually the company's
        own one-liner ("We design beautiful kitchens for NYC homes").
        """
        out: list[str] = []
        seen: set[str] = set()
        for tag in soup.find_all(["h1", "h2"], limit=12):
            text = tag.get_text(separator=" ", strip=True)
            text = re.sub(r"\s+", " ", text)
            if not (4 <= len(text) <= 200):
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(text)
            if len(out) >= 6:
                break
        return out

    @staticmethod
    def _extract_founded_year(html: str) -> int | None:
        """Pulls the earliest year that fits an "established / since /
        copyright" pattern. Falls back to None if nothing convincing.
        """
        years: list[int] = []
        for match in FOUNDED_RE.finditer(html):
            try:
                year = int(match.group(1))
            except ValueError:
                continue
            # A small business was almost certainly not founded before
            # 1900 or after the current year.
            if 1900 <= year <= 2030:
                years.append(year)
        return min(years) if years else None

    @staticmethod
    def _extract_team_size(html: str) -> int | None:
        match = TEAM_SIZE_RE.search(html)
        if not match:
            return None
        try:
            value = int(match.group(1))
        except ValueError:
            return None
        # Sanity: the regex sometimes catches phone fragments or
        # "100% satisfied"-style copy. Cap at a believable range.
        if 1 <= value <= 5000:
            return value
        return None

    @staticmethod
    def _detect_hiring(html: str, nav_text: str) -> bool:
        haystack = (html.lower() + " " + nav_text)
        return any(hint in haystack for hint in HIRING_HINTS)


def website_info_to_dict(info: WebsiteInfo, *, include_main_text: bool = False) -> dict[str, Any]:
    """Serialise WebsiteInfo for storage; omits long fields by default."""
    data: dict[str, Any] = {
        "url": info.url,
        "status_code": info.status_code,
        "ok": info.ok,
        "is_https": info.is_https,
        "title": info.title,
        "description": info.description,
        "emails": info.emails,
        "phones": info.phones,
        "social_links": info.social_links,
        "has_pricing": info.has_pricing,
        "has_portfolio": info.has_portfolio,
        "has_blog": info.has_blog,
        "founded_year": info.founded_year,
        "team_size_hint": info.team_size_hint,
        "is_hiring": info.is_hiring,
        "headings": info.headings,
        "error": info.error,
    }
    if include_main_text:
        data["main_text"] = info.main_text
    return data
