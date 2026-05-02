"""Lead-deduplication helpers — phone + domain normalization.

The pipeline matches incoming leads against ``UserSeenLead`` /
``TeamSeenLead`` along three axes: Google place-id, phone (E.164),
and registrable website domain. The functions here turn loose
real-world strings ("(415) 555-0100", "https://www.acme-roofing.com/")
into stable lookup keys.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# Strip everything that isn't a digit or a leading plus.
_PHONE_NON_DIGIT = re.compile(r"[^\d+]")


def normalize_phone(raw: str | None) -> str | None:
    """Best-effort E.164-ish normalization.

    We can't fully parse without a country hint and a phonenumbers
    library, but most leads come from Google Places with the
    ``internationalPhoneNumber`` field already in ``+CC ...`` form.
    We strip whitespace + punctuation and keep digits + the leading
    ``+``. Returns ``None`` for input that's too short to be useful
    (less than 7 digits) so we don't dedup on noise.
    """
    if not raw:
        return None
    cleaned = _PHONE_NON_DIGIT.sub("", raw)
    # Drop intermediate ``+`` signs but preserve the leading one.
    if cleaned.startswith("+"):
        cleaned = "+" + cleaned[1:].replace("+", "")
    else:
        cleaned = cleaned.replace("+", "")
    digit_count = sum(1 for c in cleaned if c.isdigit())
    if digit_count < 7:
        return None
    return cleaned[:32]


# A domain we want to ignore — these are platforms many small
# businesses point their "website" field at instead of owning a
# real one. Matching on them would treat unrelated leads as dupes.
_GENERIC_HOSTS: frozenset[str] = frozenset(
    {
        "facebook.com",
        "m.facebook.com",
        "instagram.com",
        "linkedin.com",
        "tiktok.com",
        "twitter.com",
        "x.com",
        "youtube.com",
        "vk.com",
        "ok.ru",
        "google.com",
        "goo.gl",
        "maps.google.com",
        "business.site",
        "wixsite.com",
        "weebly.com",
        "blogspot.com",
        "wordpress.com",
        "shopify.com",
        "yelp.com",
        "tripadvisor.com",
    }
)


def domain_root(raw: str | None) -> str | None:
    """Return a stable lowercase host derived from ``raw``.

    Strips scheme + ``www.`` + path + query. Returns ``None`` when
    the input parses to a generic platform host (Facebook, Instagram,
    etc.) — those make terrible dedup keys because dozens of unrelated
    companies share them.
    """
    if not raw:
        return None
    candidate = raw.strip()
    if not candidate:
        return None
    if "://" not in candidate:
        # urlparse needs a scheme to populate ``netloc``.
        candidate = "http://" + candidate
    parsed = urlparse(candidate)
    host = (parsed.netloc or parsed.path or "").lower().strip()
    # Drop any user:password@, port, trailing slash.
    if "@" in host:
        host = host.split("@", 1)[1]
    host = host.split("/")[0]
    if ":" in host:
        host = host.split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host:
        return None
    if host in _GENERIC_HOSTS:
        return None
    return host[:128]
