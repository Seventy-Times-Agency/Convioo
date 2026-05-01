"""Heuristic-only CSV column mapper (no AI call).

The Claude pass is harder to unit-test (network call); the cheap first
pass that runs before it is fully deterministic and covers the common
cases. These tests pin down the keyword list against typical CSV
exports from HubSpot, Pipedrive and a few Russian / Ukrainian sheets.
"""

from leadgen.analysis.ai_analyzer import _heuristic_csv_mapping


def field_for(headers: list[str], header: str) -> str:
    out = _heuristic_csv_mapping(headers)
    for entry in out:
        if entry["header"] == header:
            return str(entry["field"])
    raise AssertionError(f"missing header {header}")


class TestEnglish:
    def test_company_variants(self) -> None:
        for h in ("Company", "Company Name", "Business Name", "Organisation"):
            assert field_for([h], h) == "name"

    def test_website_variants(self) -> None:
        for h in ("Website", "URL", "Domain", "Homepage"):
            assert field_for([h], h) == "website"

    def test_region_variants(self) -> None:
        for h in ("Region", "City", "Country", "Location", "Address"):
            assert field_for([h], h) == "region"

    def test_phone_variants(self) -> None:
        for h in ("Phone", "Tel", "Mobile"):
            assert field_for([h], h) == "phone"

    def test_category_variants(self) -> None:
        for h in ("Category", "Industry", "Sector", "Niche"):
            assert field_for([h], h) == "category"


class TestRussianUkrainian:
    def test_russian_headers(self) -> None:
        assert field_for(["Название"], "Название") == "name"
        assert field_for(["Сайт"], "Сайт") == "website"
        assert field_for(["Город"], "Город") == "region"
        assert field_for(["Телефон"], "Телефон") == "phone"
        assert field_for(["Ниша"], "Ниша") == "category"

    def test_ukrainian_company_header(self) -> None:
        assert field_for(["Назва компанії"], "Назва компанії") == "name"


class TestFallback:
    def test_unknown_header_falls_to_extras(self) -> None:
        assert field_for(["Notes about lead"], "Notes about lead") == "extras"

    def test_id_columns_marked_skip(self) -> None:
        assert field_for(["row_id"], "row_id") == "skip"
        # "ID" alone is too short to confidently match — falls to extras.
        # That's acceptable — the AI pass would handle this.
