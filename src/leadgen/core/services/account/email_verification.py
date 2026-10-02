"""Email verification — syntax + MX-based deliverability heuristic.

A cheap, never-raises check we run during enrichment (and on demand
from the API) so the outreach send path can refuse hard-invalid
addresses and warn on risky ones. The verdict is one of:

* ``"valid"``   — syntax ok, domain has MX, personal (non-role) local part.
* ``"risky"``   — deliverable-ish but suspect: role address (info@, sales@…)
  or a domain with no MX but an A/AAAA record (mail might still land).
* ``"invalid"`` — bad syntax, NXDOMAIN, or a domain with no usable records.
* ``"unknown"`` — DNS disabled, a timeout, or any unexpected error. Never
  a hard failure — the caller decides whether to send.

DNS is done through a module-level :func:`_resolve_mx` /
:func:`_resolve_a` indirection so tests can monkeypatch them and never
touch the network. Per-domain results are cached in-process with a TTL
so a 50-lead enrichment doesn't hammer the resolver for one domain.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from email.utils import parseaddr

from leadgen.config import get_settings

logger = logging.getLogger(__name__)

# DNS lookups are wrapped in ``asyncio.to_thread`` with this ceiling so a
# slow / non-responsive resolver can't stall an enrichment batch.
_DNS_TIMEOUT = 5.0

# How long a domain's MX / A lookup result stays cached in-process.
_CACHE_TTL = 6 * 60 * 60  # 6 hours

# Role / shared mailboxes — deliverable but not a person. We still send
# (status "risky") but flag them so the UI / operator knows.
_ROLE_LOCALS = frozenset(
    {
        "info",
        "sales",
        "support",
        "admin",
        "contact",
        "office",
        "hello",
        "team",
        "mail",
        "noreply",
        "no-reply",
    }
)

# Pragmatic RFC-ish address shape: local @ domain.tld. Deliberately not a
# full RFC 5322 grammar — that admits absurd addresses no real lead uses.
_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,}$"
)


@dataclass(slots=True)
class EmailVerification:
    """Outcome of :func:`verify_email`."""

    status: str  # "valid" | "risky" | "invalid" | "unknown"
    reason: str
    mx_host: str | None = None


# ── in-process domain cache ─────────────────────────────────────────────

# domain -> (expires_at_epoch, result_tuple). The result tuple is
# (kind, host) where kind is "mx" | "a" | "none" | "error".
_domain_cache: dict[str, tuple[float, tuple[str, str | None]]] = {}


def _cache_get(domain: str) -> tuple[str, str | None] | None:
    hit = _domain_cache.get(domain)
    if hit is None:
        return None
    expires_at, value = hit
    if expires_at < time.monotonic():
        _domain_cache.pop(domain, None)
        return None
    return value


def _cache_put(domain: str, value: tuple[str, str | None]) -> None:
    _domain_cache[domain] = (time.monotonic() + _CACHE_TTL, value)


def clear_cache() -> None:
    """Drop every cached domain result (used by tests)."""
    _domain_cache.clear()


# ── injectable resolvers (patched in tests) ─────────────────────────────


def _resolve_mx(domain: str) -> list[str]:
    """Blocking MX lookup. Returns the exchange hostnames, lowest pref first.

    Raises on NXDOMAIN / no-answer / timeout — the async wrapper turns
    those into the appropriate verdict. Patched in tests so no real DNS
    happens.
    """
    import dns.resolver

    resolver = dns.resolver.Resolver()
    resolver.lifetime = _DNS_TIMEOUT
    resolver.timeout = _DNS_TIMEOUT
    answers = resolver.resolve(domain, "MX")
    records = sorted(answers, key=lambda r: r.preference)
    return [str(r.exchange).rstrip(".") for r in records]


def _resolve_a(domain: str) -> bool:
    """Blocking A/AAAA presence check. True when the domain resolves.

    Used to downgrade "no MX" to "risky" instead of "invalid": a domain
    with an A record but no MX may still accept mail at its A host.
    """
    import dns.resolver

    resolver = dns.resolver.Resolver()
    resolver.lifetime = _DNS_TIMEOUT
    resolver.timeout = _DNS_TIMEOUT
    for rdtype in ("A", "AAAA"):
        try:
            answers = resolver.resolve(domain, rdtype)
            if len(answers) > 0:
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


async def _lookup_domain(domain: str) -> tuple[str, str | None]:
    """Resolve a domain's mail capability, caching the verdict.

    Returns ``(kind, host)`` where ``kind`` is one of:
      * ``"mx"``    — MX present, ``host`` is the primary exchange.
      * ``"a"``     — no MX but an A/AAAA record exists.
      * ``"none"``  — no records at all (NXDOMAIN / empty).
      * ``"error"`` — timeout or unexpected resolver error.
    """
    cached = _cache_get(domain)
    if cached is not None:
        return cached

    import dns.resolver

    try:
        mx_hosts = await asyncio.to_thread(_resolve_mx, domain)
        if mx_hosts:
            result = ("mx", mx_hosts[0])
            _cache_put(domain, result)
            return result
        # Empty answer with no exception — treat as "no MX".
        has_a = await asyncio.to_thread(_resolve_a, domain)
        result = ("a", None) if has_a else ("none", None)
        _cache_put(domain, result)
        return result
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
        # Domain exists but no MX, or doesn't exist. Fall back to A check —
        # NoAnswer (no MX records) is the deliverable-ish case.
        try:
            has_a = await asyncio.to_thread(_resolve_a, domain)
        except Exception:  # noqa: BLE001
            has_a = False
        result = ("a", None) if has_a else ("none", None)
        _cache_put(domain, result)
        return result
    except (dns.resolver.LifetimeTimeout, dns.exception.Timeout):
        # Don't cache transient timeouts — a retry later may succeed.
        return ("error", None)
    except Exception:  # noqa: BLE001
        logger.warning(
            "email_verification: MX lookup crashed for %s", domain, exc_info=True
        )
        return ("error", None)


def _normalize(email: str) -> str | None:
    """Extract a bare address from a possibly-decorated string, or None."""
    _name, addr = parseaddr(email or "")
    addr = addr.strip()
    if not addr or not _EMAIL_RE.match(addr):
        return None
    return addr


async def verify_email(email: str) -> EmailVerification:
    """Verify *email* and return its deliverability verdict. Never raises."""
    try:
        addr = _normalize(email)
        if addr is None:
            return EmailVerification(
                status="invalid", reason="bad syntax", mx_host=None
            )

        local, _, domain = addr.partition("@")
        domain = domain.lower()
        local_lc = local.lower()

        # DNS disabled (or test mode) → syntax-only, can't confirm domain.
        if not get_settings().email_verification_enabled:
            return EmailVerification(
                status="unknown", reason="dns disabled", mx_host=None
            )

        kind, host = await _lookup_domain(domain)
        if kind == "error":
            return EmailVerification(
                status="unknown", reason="dns timeout", mx_host=None
            )
        if kind == "none":
            return EmailVerification(
                status="invalid", reason="no mail records", mx_host=None
            )
        if kind == "a":
            return EmailVerification(
                status="risky", reason="no mx, a record present", mx_host=None
            )

        # kind == "mx": deliverable. Distinguish role from personal.
        if local_lc in _ROLE_LOCALS:
            return EmailVerification(
                status="risky", reason="role address", mx_host=host
            )
        return EmailVerification(status="valid", reason="mx ok", mx_host=host)
    except Exception:  # noqa: BLE001
        logger.warning(
            "email_verification: unexpected error for %r", email, exc_info=True
        )
        return EmailVerification(
            status="unknown", reason="unexpected error", mx_host=None
        )


def is_role_local(local_part: str) -> bool:
    """True when *local_part* is a shared / role mailbox name."""
    return local_part.lower() in _ROLE_LOCALS
