"""SPF / DMARC presence checker for a sending domain.

Powers the deliverability dashboard: a domain without SPF / DMARC
records is far more likely to land in spam, so we surface their
presence (and the DMARC policy) to the user. Same never-raise,
injectable-resolver, in-process-cache contract as
:mod:`leadgen.core.services.email_verification` so unit tests can run
without touching the network.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from leadgen.config import get_settings

logger = logging.getLogger(__name__)

_DNS_TIMEOUT = 5.0
_CACHE_TTL = 6 * 60 * 60  # 6 hours

# domain -> (expires_at_epoch, result_dict)
_auth_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def clear_cache() -> None:
    """Drop every cached domain-auth result (used by tests)."""
    _auth_cache.clear()


def _resolve_txt(name: str) -> list[str]:
    """Blocking TXT lookup returning the joined record strings.

    Patched in tests so no real DNS happens. Raises on resolver errors;
    the async wrapper turns those into "not present".
    """
    import dns.resolver

    resolver = dns.resolver.Resolver()
    resolver.lifetime = _DNS_TIMEOUT
    resolver.timeout = _DNS_TIMEOUT
    answers = resolver.resolve(name, "TXT")
    records: list[str] = []
    for rdata in answers:
        # dnspython exposes the chunks as ``strings`` (list[bytes]); join
        # them so a split long TXT record reads as one string.
        parts = getattr(rdata, "strings", None)
        if parts:
            records.append(
                "".join(
                    p.decode("utf-8", "ignore") if isinstance(p, bytes) else str(p)
                    for p in parts
                )
            )
        else:
            records.append(str(rdata).strip('"'))
    return records


async def _txt_records(name: str) -> list[str] | None:
    """Async TXT lookup. Returns the records, or None on any DNS error."""
    import dns.resolver

    try:
        return await asyncio.to_thread(_resolve_txt, name)
    except (
        dns.resolver.NoAnswer,
        dns.resolver.NXDOMAIN,
        dns.resolver.NoNameservers,
    ):
        return []
    except (dns.resolver.LifetimeTimeout, dns.exception.Timeout):
        return None
    except Exception:  # noqa: BLE001
        logger.warning("dns_auth: TXT lookup crashed for %s", name, exc_info=True)
        return None


def _empty_result() -> dict[str, Any]:
    return {
        "spf": {"present": False, "record": None},
        "dmarc": {"present": False, "policy": None},
    }


async def check_domain_auth(domain: str) -> dict[str, Any]:
    """Return SPF + DMARC presence for *domain*. Never raises.

    Shape::

        {
          "spf":   {"present": bool, "record": str | None},
          "dmarc": {"present": bool, "policy": str | None},
        }
    """
    try:
        domain = (domain or "").strip().lower()
        if not domain:
            return _empty_result()

        if not get_settings().email_verification_enabled:
            return _empty_result()

        cached = _auth_cache.get(domain)
        if cached is not None and cached[0] >= time.monotonic():
            return cached[1]

        result = _empty_result()

        spf_records = await _txt_records(domain)
        if spf_records:
            for rec in spf_records:
                if rec.lower().startswith("v=spf1"):
                    result["spf"] = {"present": True, "record": rec}
                    break

        dmarc_records = await _txt_records(f"_dmarc.{domain}")
        if dmarc_records:
            for rec in dmarc_records:
                if rec.lower().startswith("v=dmarc1"):
                    result["dmarc"] = {
                        "present": True,
                        "policy": _extract_dmarc_policy(rec),
                    }
                    break

        _auth_cache[domain] = (time.monotonic() + _CACHE_TTL, result)
        return result
    except Exception:  # noqa: BLE001
        logger.warning("dns_auth: check crashed for %s", domain, exc_info=True)
        return _empty_result()


def _extract_dmarc_policy(record: str) -> str | None:
    """Pull the ``p=`` policy token out of a DMARC TXT record."""
    for token in record.split(";"):
        token = token.strip()
        if token.lower().startswith("p="):
            return token.split("=", 1)[1].strip() or None
    return None
