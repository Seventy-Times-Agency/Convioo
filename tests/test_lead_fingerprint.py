"""Cross-session dedup helpers — phone + domain normalization."""

from leadgen.core.services.lead_fingerprint import (
    normalize_domain,
    normalize_phone,
)


class TestNormalizePhone:
    def test_strips_punctuation_to_last_10_digits(self) -> None:
        assert normalize_phone("+1 (212) 555-0100") == "2125550100"
        assert normalize_phone("212.555.0100") == "2125550100"
        assert normalize_phone("1-212-555-0100") == "2125550100"

    def test_handles_short_numbers(self) -> None:
        assert normalize_phone("555-0100") == "5550100"

    def test_returns_none_for_too_few_digits(self) -> None:
        assert normalize_phone("12345") is None
        assert normalize_phone("") is None
        assert normalize_phone(None) is None

    def test_caps_to_last_ten_digits_for_long_numbers(self) -> None:
        # International with country code + area code → keep last 10
        assert normalize_phone("+44 (0) 20 7946 0958") == "2079460958"

    def test_two_phones_with_different_country_codes_match(self) -> None:
        # The "212-555-0100" number with or without the +1 prefix should
        # produce the same fingerprint so dedup catches both shapes.
        assert normalize_phone("+1-212-555-0100") == normalize_phone("(212) 555-0100")


class TestNormalizeDomain:
    def test_strips_protocol_path_query(self) -> None:
        assert normalize_domain("https://www.example.com/about?utm=x") == "example.com"

    def test_strips_www_prefix(self) -> None:
        assert normalize_domain("https://www.example.com") == "example.com"
        assert normalize_domain("example.com") == "example.com"

    def test_handles_double_tlds(self) -> None:
        assert normalize_domain("https://www.example.co.uk/x") == "example.co.uk"
        assert normalize_domain("http://shop.example.com.ua") == "example.com.ua"

    def test_lowercases(self) -> None:
        assert normalize_domain("HTTPS://EXAMPLE.COM") == "example.com"

    def test_strips_port_and_userinfo(self) -> None:
        assert normalize_domain("http://user:pw@example.com:8080") == "example.com"

    def test_returns_none_for_garbage(self) -> None:
        assert normalize_domain("") is None
        assert normalize_domain(None) is None
        assert normalize_domain("not a url") is None

    def test_subdomains_collapse_to_registrable(self) -> None:
        # blog.example.com and shop.example.com should both fingerprint
        # to the same business — they share the same registrable domain.
        assert normalize_domain("https://blog.example.com") == "example.com"
        assert normalize_domain("https://shop.example.com") == "example.com"
