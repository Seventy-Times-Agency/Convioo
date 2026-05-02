"""Niche taxonomy loader + autocomplete matcher.

The YAML next to this module is the source of truth: each entry has
a stable ``id``, per-language labels (en/ru/uk/de), and free-form
aliases. ``suggest()`` searches across labels + aliases so a user
typing "дантисты" lands on the ``dentists`` niche even though the
canonical English label says "Dentists".

Match precedence is rough but pragmatic:
  1. exact match on any label/alias
  2. label/alias starts with the query (word-prefix)
  3. label/alias contains the query as a substring
Within a tier we keep insertion order from the YAML so a curated
top-of-mind ordering survives into the dropdown.

Loading is one-shot: the YAML is small (<100 entries), parsed once
on first call, cached in a module-level singleton.
"""

from __future__ import annotations

import functools
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml

_DATA_FILE = Path(__file__).with_name("niches.yaml")
SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"en", "ru", "uk", "de"})
DEFAULT_LANGUAGE = "en"


@dataclass(slots=True, frozen=True)
class NicheEntry:
    id: str
    category: str | None
    labels: dict[str, str]
    aliases: tuple[str, ...]

    def label(self, language: str | None) -> str:
        if language and language in self.labels:
            return self.labels[language]
        return self.labels.get(DEFAULT_LANGUAGE) or next(iter(self.labels.values()))

    def haystack(self) -> Iterable[str]:
        """All searchable strings for this niche, lowercased."""
        for value in self.labels.values():
            yield value.lower()
        for alias in self.aliases:
            yield alias.lower()


@functools.lru_cache(maxsize=1)
def _load() -> tuple[NicheEntry, ...]:
    raw = yaml.safe_load(_DATA_FILE.read_text(encoding="utf-8"))
    entries: list[NicheEntry] = []
    seen: set[str] = set()
    for item in raw.get("niches") or ():
        nid = str(item["id"]).strip()
        if not nid or nid in seen:
            continue
        seen.add(nid)
        labels = {
            code: str(label).strip()
            for code, label in (item.get("labels") or {}).items()
            if code in SUPPORTED_LANGUAGES and label
        }
        if not labels:
            continue
        aliases = tuple(
            str(a).strip() for a in (item.get("aliases") or []) if str(a).strip()
        )
        entries.append(
            NicheEntry(
                id=nid,
                category=(item.get("category") or None),
                labels=labels,
                aliases=aliases,
            )
        )
    return tuple(entries)


def all_niches() -> tuple[NicheEntry, ...]:
    """Read-only accessor to the cached taxonomy."""
    return _load()


def find(niche_id: str) -> NicheEntry | None:
    nid = niche_id.strip().lower()
    for entry in _load():
        if entry.id == nid:
            return entry
    return None


def suggest(
    query: str | None, *, language: str | None = None, limit: int = 12
) -> list[NicheEntry]:
    """Return up to ``limit`` taxonomy entries matching ``query``.

    Empty / very short query returns the curated top-of-list (so the
    combobox can prefill suggestions on focus).
    """
    entries = _load()
    if limit <= 0:
        return []
    q = (query or "").strip().lower()
    if not q:
        return list(entries[:limit])

    exact: list[NicheEntry] = []
    prefix: list[NicheEntry] = []
    contains: list[NicheEntry] = []
    for entry in entries:
        bucket = None
        for needle in entry.haystack():
            if needle == q:
                bucket = exact
                break
            if needle.startswith(q) or _word_prefix_match(needle, q):
                bucket = prefix
                continue
            if q in needle and bucket is None:
                bucket = contains
        if bucket is not None:
            bucket.append(entry)

    out: list[NicheEntry] = []
    for tier in (exact, prefix, contains):
        for entry in tier:
            if entry not in out:
                out.append(entry)
            if len(out) >= limit:
                return out
    return out


def _word_prefix_match(haystack: str, q: str) -> bool:
    """True if ``q`` matches the start of any whitespace-delimited word.

    "rooms cleaning" + q="clean" → True via the second word.
    """
    return any(word.startswith(q) for word in haystack.split())
