"""Pure-function tests for the dedup normalisers."""

from __future__ import annotations

from leadgen.utils.dedup import domain_root, normalize_phone

# ── normalize_phone ──────────────────────────────────────────────────────


def test_normalize_phone_strips_punctuation() -> None:
    assert normalize_phone("+1 (415) 555-0100") == "+14155550100"
    assert normalize_phone("(415) 555.0100") == "4155550100"


def test_normalize_phone_keeps_leading_plus() -> None:
    assert normalize_phone("+44 20 7946 0958") == "+442079460958"


def test_normalize_phone_drops_intermediate_pluses() -> None:
    # Junk like "+1+2-3" → keep the first plus only.
    assert normalize_phone("+1+2 3 4 5 6 7") == "+1234567"


def test_normalize_phone_rejects_too_short() -> None:
    assert normalize_phone("123") is None
    assert normalize_phone("+1 22") is None
    assert normalize_phone("") is None
    assert normalize_phone(None) is None


def test_normalize_phone_caps_length() -> None:
    huge = "+" + "1" * 100
    assert normalize_phone(huge) is not None
    assert len(normalize_phone(huge)) <= 32


# ── domain_root ──────────────────────────────────────────────────────────


def test_domain_root_basic() -> None:
    assert domain_root("https://www.acme-roofing.com/") == "acme-roofing.com"
    assert domain_root("http://acme.com") == "acme.com"
    assert domain_root("acme.com") == "acme.com"


def test_domain_root_strips_path_and_query() -> None:
    assert (
        domain_root("https://shop.acme.com/path?utm=foo")
        == "shop.acme.com"
    )


def test_domain_root_strips_port_and_userinfo() -> None:
    url = "https://" + "user" + "@" + "acme.com:8080/"
    assert domain_root(url) == "acme.com"


def test_domain_root_lowercases() -> None:
    assert domain_root("HTTPS://Acme.COM") == "acme.com"


def test_domain_root_rejects_generic_platforms() -> None:
    # Two unrelated leads pointing their "website" at Facebook would
    # otherwise dedup against each other — wrong.
    assert domain_root("https://facebook.com/MyShop") is None
    assert domain_root("https://www.linkedin.com/company/x") is None
    assert domain_root("https://x.com/handle") is None
    assert domain_root("https://maps.google.com/?cid=123") is None


def test_domain_root_handles_garbage() -> None:
    assert domain_root(None) is None
    assert domain_root("") is None
    assert domain_root("   ") is None
    # No dot → not a domain.
    assert domain_root("localhost") is None
