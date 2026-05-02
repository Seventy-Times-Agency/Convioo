"""Curated city catalogue + autocomplete matcher.

The JSON next to this module is the source of truth: ~120 hand-
picked entries covering EU capitals + major cities, US top metros,
Ukraine + CIS-non-RU, UK + Canada. Each entry has a stable ``id``
plus per-language display names so an autocomplete dropdown can
show "Berlin" / "Берлин" / "Берлін" depending on the user's UI
language. Anything outside this list is still typeable by hand —
the combobox is purely additive.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

_DATA_FILE = Path(__file__).with_name("cities.json")
DEFAULT_LANGUAGE = "en"


@dataclass(slots=True, frozen=True)
class CityEntry:
    id: str
    name_en: str
    names: dict[str, str]
    country: str
    lat: float
    lon: float
    population: int

    def label(self, language: str | None) -> str:
        if language and language in self.names:
            return self.names[language]
        return self.name_en

    def haystack(self) -> Iterable[str]:
        """All searchable strings for this city, lowercased."""
        yield self.name_en.lower()
        for value in self.names.values():
            yield value.lower()


@functools.lru_cache(maxsize=1)
def _load() -> tuple[CityEntry, ...]:
    raw = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    entries: list[CityEntry] = []
    for item in raw:
        try:
            cid = str(item["id"]).strip()
            name_en = str(item["name"]).strip()
            country = str(item["country"]).strip().upper()
            lat = float(item["lat"])
            lon = float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if not cid or not name_en:
            continue
        names_raw = item.get("names") or {}
        names = {
            str(code).strip().lower(): str(value).strip()
            for code, value in names_raw.items()
            if value
        }
        try:
            population = int(item.get("population") or 0)
        except (TypeError, ValueError):
            population = 0
        entries.append(
            CityEntry(
                id=cid,
                name_en=name_en,
                names=names,
                country=country,
                lat=lat,
                lon=lon,
                population=population,
            )
        )
    # Sort by population descending so the curated top-of-list shows
    # the biggest cities first when the user opens the dropdown empty.
    entries.sort(key=lambda c: -c.population)
    return tuple(entries)


def all_cities() -> tuple[CityEntry, ...]:
    return _load()


def find(city_id: str) -> CityEntry | None:
    cid = city_id.strip().lower()
    for entry in _load():
        if entry.id == cid:
            return entry
    return None


def suggest(
    query: str | None,
    *,
    country: str | None = None,
    language: str | None = None,
    limit: int = 12,
) -> list[CityEntry]:
    """Return up to ``limit`` city suggestions matching ``query``.

    Empty / very short query returns the population-sorted top.
    ``country`` filter (ISO2) lets the SPA narrow to one country once
    the user picks a scope=country search.
    """
    if limit <= 0:
        return []
    entries = _load()
    if country:
        cc = country.strip().upper()
        entries = tuple(c for c in entries if c.country == cc)

    q = (query or "").strip().lower()
    if not q:
        return list(entries[:limit])

    exact: list[CityEntry] = []
    prefix: list[CityEntry] = []
    contains: list[CityEntry] = []
    for entry in entries:
        bucket = None
        for needle in entry.haystack():
            if needle == q:
                bucket = exact
                break
            if needle.startswith(q):
                bucket = prefix
                continue
            if q in needle and bucket is None:
                bucket = contains
        if bucket is not None:
            bucket.append(entry)

    out: list[CityEntry] = []
    for tier in (exact, prefix, contains):
        for entry in tier:
            if entry not in out:
                out.append(entry)
            if len(out) >= limit:
                return out
    return out


def match_city(text: str | None) -> CityEntry | None:
    """Best-effort city lookup from free-form input.

    Used by the search pipeline to decide whether to use the curated
    coords (skip Nominatim entirely for cities we already know).
    Returns ``None`` if nothing matches.
    """
    if not text:
        return None
    matches = suggest(text, limit=1)
    return matches[0] if matches else None
