"""Business-language classifier (Wave 1, задача 6).

A generic "what language does this business live in" engine. It
combines cheap deterministic signals — website text script, review
text script, Ukrainian/Russian-specific characters, transliterated
Slavic personal names, social/domain hints and explicit keywords —
into a single verdict:

    (language, confidence, signals)

* ``language`` — BCP-47-ish lowercase code ("ru", "uk", …) or None.
* ``confidence`` — "exact" (точно) | "likely" (вероятно) | None (нет).
* ``signals`` — which evidence fired, for the UI tooltip / debugging.

The engine is language-agnostic by design; the RU/UA preset our own
department uses is just the pair of labels this module distinguishes
best. Extending to another community = adding its character set /
name list / keyword pack here — no pipeline changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Characters that exist in Ukrainian but not Russian orthography.
_UK_CHARS = set("іїєґІЇЄҐ")
# Characters that exist in Russian but not Ukrainian orthography.
_RU_CHARS = set("ыэъёЫЭЪЁ")

# Explicit self-identification keywords → (language, exact).
_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("говорим по-русски", "ru"),
    ("русскоговорящ", "ru"),
    ("русскоязычн", "ru"),
    ("russian speaking", "ru"),
    ("russian-speaking", "ru"),
    ("по-русски", "ru"),
    ("розмовляємо українською", "uk"),
    ("україномовн", "uk"),
    ("украиноязычн", "uk"),
    ("ukrainian speaking", "uk"),
    ("ukrainian-speaking", "uk"),
    ("говоримо українською", "uk"),
)

# Social / domain hints.
_SOCIAL_HINTS: tuple[tuple[str, str], ...] = (
    ("vk.com", "ru"),
    ("ok.ru", "ru"),
    (".ua/", "uk"),
    (".com.ua", "uk"),
    ("olx.ua", "uk"),
)

# Transliterated surname suffixes typical for the two communities.
# Shared Slavic suffixes count as a weak "slavic" signal that leans
# to whichever language other evidence points at.
_UA_NAME_SUFFIXES = ("enko", "eiko", "chuk", "czuk", "shchuk", "iuk", "yuk")
_SLAVIC_NAME_SUFFIXES = (
    "ov",
    "ova",
    "ev",
    "eva",
    "in",
    "ina",
    "sky",
    "skiy",
    "skaya",
    "ski",
    "vich",
    "ich",
)

_WORD_RE = re.compile(r"[A-Za-z]+")


@dataclass
class LanguageVerdict:
    language: str | None
    confidence: str | None  # "exact" | "likely" | None
    signals: list[str] = field(default_factory=list)


def _script_counts(text: str) -> tuple[int, int, int, int]:
    """(cyrillic, latin, uk_specific, ru_specific) character counts."""
    cyr = lat = uk = ru = 0
    for ch in text:
        if ch in _UK_CHARS:
            uk += 1
            cyr += 1
        elif ch in _RU_CHARS:
            ru += 1
            cyr += 1
        elif "Ѐ" <= ch <= "ӿ":
            cyr += 1
        elif ch.isascii() and ch.isalpha():
            lat += 1
    return cyr, lat, uk, ru


def classify_business_language(
    *,
    website_text: str | None = None,
    reviews_texts: list[str] | None = None,
    owner_names: list[str] | None = None,
    social_links: dict[str, str] | None = None,
    extra_text: str | None = None,
) -> LanguageVerdict:
    """Combine the available evidence into one verdict.

    Rules (strongest first):
    1. Explicit keyword self-identification → exact.
    2. Language-specific characters in site/review text → exact when
       one side clearly dominates, likely otherwise.
    3. Plain Cyrillic text with no side-specific characters → "ru"
       likely (statistically dominant in the US diaspora corpus) —
       unless UA hints (domains) flip it.
    4. Transliterated Slavic names / social hints alone → likely.
    5. Nothing → (None, None).
    """
    signals: list[str] = []
    corpus_parts: list[str] = []
    if website_text:
        corpus_parts.append(website_text)
    for rt in reviews_texts or []:
        if rt:
            corpus_parts.append(rt)
    if extra_text:
        corpus_parts.append(extra_text)
    corpus = "\n".join(corpus_parts)
    corpus_lower = corpus.lower()

    links_blob = " ".join(
        (social_links or {}).values()
    ).lower() + " " + " ".join((social_links or {}).keys()).lower()

    # 1 — keywords.
    for needle, lang in _KEYWORDS:
        if needle in corpus_lower:
            signals.append(f"keyword:{needle}")
            return LanguageVerdict(lang, "exact", signals)

    cyr, lat, uk_sp, ru_sp = _script_counts(corpus)

    # 2 — script-specific characters.
    if uk_sp or ru_sp:
        if uk_sp and ru_sp:
            lang = "uk" if uk_sp >= ru_sp else "ru"
            signals.append(f"chars:uk={uk_sp},ru={ru_sp}")
            return LanguageVerdict(lang, "likely", signals)
        lang = "uk" if uk_sp else "ru"
        strong = (uk_sp if uk_sp else ru_sp) >= 3
        signals.append(f"chars:{lang}={uk_sp or ru_sp}")
        return LanguageVerdict(lang, "exact" if strong else "likely", signals)

    # Social/domain hints — evaluated before the generic-Cyrillic
    # fallback so a .ua site with ambiguous text reads as uk.
    hint_lang: str | None = None
    for needle, lang in _SOCIAL_HINTS:
        if needle in links_blob or (
            website_text is None and needle in corpus_lower
        ):
            hint_lang = lang
            signals.append(f"social:{needle}")
            break

    # 3 — generic Cyrillic body.
    if cyr >= 20 and cyr >= lat * 0.15:
        signals.append(f"cyrillic:{cyr}")
        return LanguageVerdict(hint_lang or "ru", "likely", signals)

    # 4 — transliterated names.
    for name in owner_names or []:
        for word in _WORD_RE.findall(name.lower()):
            if any(word.endswith(s) for s in _UA_NAME_SUFFIXES):
                signals.append(f"name:{word}")
                return LanguageVerdict("uk", "likely", signals)
            if any(word.endswith(s) for s in _SLAVIC_NAME_SUFFIXES) and len(
                word
            ) > 4:
                signals.append(f"name:{word}")
                return LanguageVerdict(hint_lang or "ru", "likely", signals)

    if hint_lang:
        return LanguageVerdict(hint_lang, "likely", signals)

    return LanguageVerdict(None, None, signals)
