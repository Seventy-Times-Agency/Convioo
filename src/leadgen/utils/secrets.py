"""Log sanitizer: scrub API keys and auth headers from strings before logging.

External APIs occasionally echo the bad key back in their error response
(seen with Google and some websites behind Cloudflare). Without scrubbing
these strings would get persisted to Railway logs / Prometheus alerts /
error-tracking tools, which is exactly how secrets leak.
"""

from __future__ import annotations

import re

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Generic "api_key=..." or "apikey: ..." in query string / header / body
    (re.compile(r"(?i)(api[-_]?key|x-goog-api-key|authorization)\s*[=:]\s*([\"']?)([A-Za-z0-9_\-./+]{12,})\2"),
     r"\1=[REDACTED]"),
    # Google API keys always start with "AIza"
    (re.compile(r"AIza[0-9A-Za-z_\-]{30,}"), "AIza[REDACTED]"),
    # Anthropic keys start with sk-ant- (or sk-)
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), "sk-ant-[REDACTED]"),
    (re.compile(r"sk-[A-Za-z0-9_\-]{20,}"), "sk-[REDACTED]"),
    # Telegram bot tokens are "<digits>:<alphanumerics>"
    (re.compile(r"\b\d{6,}:[A-Za-z0-9_\-]{30,}\b"), "[REDACTED_BOT_TOKEN]"),
    # Bearer tokens in headers
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-.=/+]{16,}"), "Bearer [REDACTED]"),
    # Database URLs with passwords
    (re.compile(r"(postgres(?:ql)?(?:\+[a-z]+)?://[^:]+:)([^@]+)(@)"), r"\1[REDACTED]\3"),
]


def sanitize(text: str | None) -> str:
    """Return ``text`` with any detected credential replaced by a placeholder."""
    if not text:
        return text or ""
    out = text
    for pattern, replacement in _PATTERNS:
        out = pattern.sub(replacement, out)
    return out
