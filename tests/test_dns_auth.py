"""SPF / DMARC checker — present + absent, patched resolver (no real DNS)."""

from __future__ import annotations

import dns.resolver
import pytest

from leadgen.core.services import dns_auth


@pytest.fixture(autouse=True)
def _clear_cache():
    dns_auth.clear_cache()
    yield
    dns_auth.clear_cache()


@pytest.fixture(autouse=True)
def _enable(monkeypatch):
    from leadgen.config import get_settings

    monkeypatch.setattr(
        get_settings(), "email_verification_enabled", True
    )
    yield


@pytest.mark.asyncio
async def test_spf_and_dmarc_present(monkeypatch):
    def _txt(name: str):
        if name == "example.com":
            return ["v=spf1 include:_spf.google.com ~all"]
        if name == "_dmarc.example.com":
            return ["v=DMARC1; p=reject; rua=mailto:a@example.com"]
        return []

    monkeypatch.setattr(dns_auth, "_resolve_txt", _txt)
    result = await dns_auth.check_domain_auth("example.com")
    assert result["spf"]["present"] is True
    assert result["spf"]["record"].startswith("v=spf1")
    assert result["dmarc"]["present"] is True
    assert result["dmarc"]["policy"] == "reject"


@pytest.mark.asyncio
async def test_spf_and_dmarc_absent(monkeypatch):
    def _none(_name: str):
        raise dns.resolver.NXDOMAIN()

    monkeypatch.setattr(dns_auth, "_resolve_txt", _none)
    result = await dns_auth.check_domain_auth("nope.example")
    assert result["spf"] == {"present": False, "record": None}
    assert result["dmarc"] == {"present": False, "policy": None}


@pytest.mark.asyncio
async def test_disabled_returns_empty(monkeypatch):
    from leadgen.config import get_settings

    monkeypatch.setattr(
        get_settings(), "email_verification_enabled", False
    )

    def _boom(_name: str):
        raise AssertionError("DNS must not run when disabled")

    monkeypatch.setattr(dns_auth, "_resolve_txt", _boom)
    result = await dns_auth.check_domain_auth("example.com")
    assert result["spf"]["present"] is False
    assert result["dmarc"]["present"] is False
