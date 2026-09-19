"""ЛПР: страна по номеру, выбор лучшего человека, сведение контактов."""

from __future__ import annotations

import pytest

from leadgen.core.services import decision_maker as dm
from leadgen.core.services.decision_maker import (
    LookupInput,
    Person,
    detect_country,
)


def test_detect_country():
    assert detect_country("+380 67 123 45 67", None) == "UA"
    # Без кода страны номер не угадываем.
    assert detect_country("(305) 555-1234", None) is None
    assert detect_country("+1 305 555 1234", None) == "US"
    assert detect_country("+44 20 7123 4567", None) == "GB"
    assert detect_country(None, "Hauptstr. 1, Berlin, Germany") == "DE"


def test_people_links_any_language():
    html = """
      <a href="/pro-nas">Про нас</a>
      <a href="/impressum">Impressum</a>
      <a href="https://other.com/team">Team</a>
      <a href="/blog">Blog</a>
    """
    links = dm._people_links("https://firma.ua/", html)
    assert "https://firma.ua/pro-nas" in links
    assert "https://firma.ua/impressum" in links
    assert all("other.com" not in u for u in links)
    assert not any(u.endswith("/blog") for u in links)


@pytest.mark.asyncio
async def test_registry_role_merged_with_site_contacts(monkeypatch):
    """Реестр подтверждает роль, сайт даёт почту — в итоге один ЛПР
    с ролью из реестра и почтой с сайта."""

    async def site(inp):
        return [
            Person(name="John Smith", title="Manager", email="john@acme.co.uk",
                   source="website"),
            Person(name="Anna Lee", title="Sales", source="website"),
        ]

    async def ch(company):
        return [Person(name="John Smith", title="director",
                       is_decision_maker=True, source="companies_house")]

    async def nothing(*a, **k):
        return []

    async def no_email(*a, **k):
        return None

    monkeypatch.setattr(dm, "_site_people", site)
    monkeypatch.setattr(dm, "_companies_house", ch)
    monkeypatch.setattr(dm, "_apollo", nothing)
    monkeypatch.setattr(dm, "_hunter_email", no_email)

    res = await dm.find_decision_maker(
        LookupInput(company_name="Acme Ltd", website="https://acme.co.uk",
                    phone="+44 20 7123 4567")
    )
    assert res["name"] == "John Smith"
    assert res["title"] == "director"
    assert res["email"] == "john@acme.co.uk"
    assert res["source"] == "companies_house"
    assert res["country"] == "GB"
    assert len(res["people"]) == 3


@pytest.mark.asyncio
async def test_hunter_fills_missing_email(monkeypatch):
    async def site(inp):
        return [Person(name="Олена Коваль", title="Директор",
                       is_decision_maker=True, source="website")]

    async def nothing(*a, **k):
        return []

    async def hunter(person, domain):
        return "o.koval@firma.ua"

    monkeypatch.setattr(dm, "_site_people", site)
    monkeypatch.setattr(dm, "_opencorporates", nothing)
    monkeypatch.setattr(dm, "_apollo", nothing)
    monkeypatch.setattr(dm, "_hunter_email", hunter)

    res = await dm.find_decision_maker(
        LookupInput(company_name="Фірма", website="firma.ua",
                    phone="+380671234567")
    )
    assert res["name"] == "Олена Коваль"
    assert res["email"] == "o.koval@firma.ua"
    assert res["country"] == "UA"


@pytest.mark.asyncio
async def test_nobody_found(monkeypatch):
    async def nothing(*a, **k):
        return []

    for fn in ("_site_people", "_opencorporates", "_apollo"):
        monkeypatch.setattr(dm, fn, nothing)
    assert await dm.find_decision_maker(LookupInput(company_name="X")) is None
