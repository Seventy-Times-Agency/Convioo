"""Fingerprints for cross-session lead deduplication.

Two leads coming back from different searches are considered "the
same business" when their phone digits match (last 10 only — country
codes are unreliable on Google Places) or their site's registrable
domain matches. Both heuristics are cheap and false-positive-resistant
for B2B targeting where the user owns the same address space.

The fingerprints are intentionally SQL-friendly: applied with
``func.regexp_replace`` and ``func.lower`` server-side so a single
indexed scan can match. Python equivalents below match the same
output for use on already-loaded rows.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# Two-or-three-letter country-coded TLDs that take a second-level
# segment ("co.uk", "com.ua"). Without this list, normalize_domain
# would strip "example" from "example.co.uk" and produce "co.uk".
# Not exhaustive — just the ones our targeting actually hits.
_DOUBLE_TLDS = frozenset(
    {
        "co.uk",
        "co.il",
        "co.nz",
        "co.za",
        "com.ua",
        "com.au",
        "com.br",
        "com.tr",
        "com.mx",
        "org.uk",
        "ac.uk",
        "gov.uk",
        "net.au",
        "org.au",
    }
)


def normalize_phone(value: str | None) -> str | None:
    """Reduce a free-form phone string to its last 10 digits.

    Google Places returns numbers in many shapes ("+1 (212) 555-0100",
    "212.555.0100", "1-212-555-0100"). For dedup we only care about
    the local 10-digit core; country codes are reliable for matching
    inside a country and noisy across borders. Returns None when the
    input contains fewer than 7 digits (almost certainly not a phone).
    """
    if not value:
        return None
    digits = re.sub(r"[^0-9]", "", value)
    if len(digits) < 7:
        return None
    return digits[-10:] if len(digits) >= 10 else digits


def normalize_domain(url: str | None) -> str | None:
    """Extract the registrable domain from any URL or bare hostname.

    Examples:
        ``https://www.example.com/about`` → ``example.com``
        ``http://example.co.uk``           → ``example.co.uk``
        ``EXAMPLE.com``                    → ``example.com``

    Returns None when the input has no recognisable host.
    """
    if not url:
        return None
    candidate = url.strip().lower()
    if "://" not in candidate:
        candidate = "http://" + candidate
    try:
        host = urlparse(candidate).netloc
    except ValueError:
        return None
    host = host.split("@")[-1].split(":")[0]  # strip user:pass@ and port
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host:
        return None
    parts = host.split(".")
    if len(parts) >= 3:
        last_two = ".".join(parts[-2:])
        if last_two in _DOUBLE_TLDS:
            return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host
