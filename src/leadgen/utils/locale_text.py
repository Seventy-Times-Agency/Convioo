"""Tiny backend-side localisation helper for system-generated text.

The frontend owns full i18n (frontend/lib/i18n); the backend only
needs to localise the handful of strings it generates itself —
transactional emails, heuristic AI fallbacks, seeded CRM labels,
user-facing error details. One ``pick`` call per string keeps those
sites flat instead of growing per-language if/else ladders.

Language resolution mirrors the frontend default: anything that is
not ``uk`` or ``en`` (including ``None``) is treated as ``ru``.
"""

from __future__ import annotations

SUPPORTED_LANGS: frozenset[str] = frozenset({"ru", "uk", "en"})

DEFAULT_LANG = "ru"


def normalize_lang(code: str | None) -> str:
    """Map a raw ``users.language_code`` value onto ru / uk / en."""
    cleaned = (code or "").strip().lower()
    return cleaned if cleaned in SUPPORTED_LANGS else DEFAULT_LANG


def pick(lang: str | None, *, ru: str, uk: str, en: str) -> str:
    """Return the variant matching ``lang`` (ru fallback)."""
    code = normalize_lang(lang)
    if code == "uk":
        return uk
    if code == "en":
        return en
    return ru
