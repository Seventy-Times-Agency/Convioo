"""Email verification — syntax, MX, role, timeout, and caching.

The injectable ``_resolve_mx`` / ``_resolve_a`` resolvers are patched in
every test so NO real DNS lookup ever happens.
"""

from __future__ import annotations

import dns.resolver
import pytest

from leadgen.core.services import email_verification as ev


@pytest.fixture(autouse=True)
def _clear_cache():
    ev.clear_cache()
    yield
    ev.clear_cache()


@pytest.fixture(autouse=True)
def _enable_verification(monkeypatch):
    # The verifier short-circuits to "unknown" when DNS is disabled. These
    # tests want the full path, so force the flag on regardless of env.
    from leadgen.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "email_verification_enabled", True)
    yield


@pytest.mark.asyncio
async def test_valid_personal_address(monkeypatch):
    monkeypatch.setattr(
        ev, "_resolve_mx", lambda d: ["mx1.example.com"]
    )
    result = await ev.verify_email("jane.doe@example.com")
    assert result.status == "valid"
    assert result.mx_host == "mx1.example.com"


@pytest.mark.asyncio
async def test_invalid_syntax_short_circuits(monkeypatch):
    # Should never reach DNS for a malformed address.
    def _boom(_d):
        raise AssertionError("DNS must not be called for bad syntax")

    monkeypatch.setattr(ev, "_resolve_mx", _boom)
    result = await ev.verify_email("not-an-email")
    assert result.status == "invalid"
    assert result.reason == "bad syntax"


@pytest.mark.asyncio
async def test_no_mx_with_a_record_is_risky(monkeypatch):
    def _no_mx(_d):
        raise dns.resolver.NoAnswer()

    monkeypatch.setattr(ev, "_resolve_mx", _no_mx)
    monkeypatch.setattr(ev, "_resolve_a", lambda d: True)
    result = await ev.verify_email("jane@example.com")
    assert result.status == "risky"


@pytest.mark.asyncio
async def test_nxdomain_no_records_is_invalid(monkeypatch):
    def _nx(_d):
        raise dns.resolver.NXDOMAIN()

    monkeypatch.setattr(ev, "_resolve_mx", _nx)
    monkeypatch.setattr(ev, "_resolve_a", lambda d: False)
    result = await ev.verify_email("jane@nope.example")
    assert result.status == "invalid"


@pytest.mark.asyncio
async def test_role_address_is_risky(monkeypatch):
    monkeypatch.setattr(ev, "_resolve_mx", lambda d: ["mx1.example.com"])
    result = await ev.verify_email("info@example.com")
    assert result.status == "risky"
    assert result.reason == "role address"


@pytest.mark.asyncio
async def test_timeout_yields_unknown(monkeypatch):
    def _timeout(_d):
        raise dns.exception.Timeout()

    monkeypatch.setattr(ev, "_resolve_mx", _timeout)
    result = await ev.verify_email("jane@example.com")
    assert result.status == "unknown"


@pytest.mark.asyncio
async def test_disabled_flag_returns_unknown(monkeypatch):
    from leadgen.config import get_settings

    monkeypatch.setattr(
        get_settings(), "email_verification_enabled", False
    )

    def _boom(_d):
        raise AssertionError("DNS must not run when disabled")

    monkeypatch.setattr(ev, "_resolve_mx", _boom)
    result = await ev.verify_email("jane@example.com")
    assert result.status == "unknown"


@pytest.mark.asyncio
async def test_domain_result_is_cached(monkeypatch):
    calls = {"n": 0}

    def _counting(_d):
        calls["n"] += 1
        return ["mx1.example.com"]

    monkeypatch.setattr(ev, "_resolve_mx", _counting)
    r1 = await ev.verify_email("a@cached.example")
    r2 = await ev.verify_email("b@cached.example")
    assert r1.status == "valid"
    assert r2.status == "valid"
    # Second lookup for the same domain hit the cache, not the resolver.
    assert calls["n"] == 1


def test_pick_primary_prefers_personal():
    from leadgen.pipeline.enrichment import pick_primary_email

    assert (
        pick_primary_email(["info@x.com", "jane@x.com"]) == "jane@x.com"
    )
    assert pick_primary_email(["info@x.com"]) == "info@x.com"
    assert pick_primary_email([]) is None
    assert pick_primary_email(None) is None
