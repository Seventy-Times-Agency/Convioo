"""Content spam pre-flight (Wave 1, задача 8).

Deterministic heuristic scorer for outbound email copy, run BEFORE a
send so a rep never ships a message that lands in Promotions/Spam.
No external API: the signals are the classic filter tells —
trigger phrases, shouting, exclamation storms, link stuffing, money
symbols, missing unsubscribe context, subject smells.

Score is 0–10 (higher = spammier):
* 0–2  ok        — send it.
* 3–5  risky     — show the issues, let the human decide.
* 6+   spammy    — strongly advise a rewrite.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# EN + RU trigger phrases (lowercase). Each hit adds its weight.
_TRIGGERS: tuple[tuple[str, float], ...] = (
    ("free", 0.75),
    ("100% free", 1.5),
    ("guarantee", 0.75),
    ("guaranteed", 0.75),
    ("act now", 1.25),
    ("limited time", 1.0),
    ("click here", 1.25),
    ("buy now", 1.0),
    ("no obligation", 1.0),
    ("risk free", 1.0),
    ("winner", 1.0),
    ("congratulations", 0.75),
    ("earn money", 1.25),
    ("make money", 1.25),
    ("cash bonus", 1.5),
    ("бесплатно", 0.75),
    ("гарантия", 0.5),
    ("гарантируем", 0.75),
    ("только сегодня", 1.25),
    ("успей", 1.0),
    ("жми", 1.25),
    ("кликни", 1.25),
    ("заработок", 1.25),
    ("быстрые деньги", 1.5),
    ("скидка 90", 1.25),
    ("поздравляем", 0.75),
)

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_MONEY_RE = re.compile(r"[$€£₴₽]|(?:\b\d+\s?%\s)")


@dataclass(slots=True)
class SpamVerdict:
    score: float  # 0..10
    verdict: str  # "ok" | "risky" | "spammy"
    issues: list[str] = field(default_factory=list)


def check_spam(subject: str | None, body: str) -> SpamVerdict:
    """Score one email's copy. Pure and fast — safe on every keypress."""
    issues: list[str] = []
    score = 0.0
    subject = (subject or "").strip()
    text = f"{subject}\n{body}"
    lower = text.lower()

    # Trigger phrases.
    hits = [t for t, _w in _TRIGGERS if t in lower]
    if hits:
        score += sum(w for t, w in _TRIGGERS if t in lower)
        issues.append("trigger_words:" + ",".join(hits[:6]))

    # SHOUTING (letters only; short texts get a pass).
    letters = [c for c in text if c.isalpha()]
    if len(letters) >= 30:
        upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if upper_ratio > 0.3:
            score += 2.0
            issues.append("all_caps")
        elif upper_ratio > 0.18:
            score += 1.0
            issues.append("caps_heavy")

    # Exclamation storms.
    bangs = text.count("!")
    if bangs >= 3:
        score += min(2.0, 0.5 * bangs)
        issues.append(f"exclamations:{bangs}")
    if "!!" in text or "?!" in text:
        score += 0.5

    # Link stuffing.
    links = _URL_RE.findall(text)
    if len(links) >= 3:
        score += 1.5
        issues.append(f"links:{len(links)}")
    # Раскрытые шорт-линки — фильтры их не любят.
    if any(
        d in lower for d in ("bit.ly", "tinyurl.", "goo.gl", "t.co/")
    ):
        score += 1.5
        issues.append("shortener")

    # Money symbols / percentages density.
    money_hits = len(_MONEY_RE.findall(text))
    if money_hits >= 3:
        score += 1.0
        issues.append(f"money_symbols:{money_hits}")

    # Subject smells.
    if subject:
        if len(subject) > 78:
            score += 0.5
            issues.append("subject_long")
        if subject.isupper() and len(subject) > 8:
            score += 1.5
            issues.append("subject_caps")
        if subject.count("!") >= 1 and subject.count("!") + subject.count(
            "?"
        ) >= 2:
            score += 0.75
            issues.append("subject_punctuation")
    else:
        score += 0.5
        issues.append("subject_missing")

    # Very short body with a link reads like phishing bait.
    if len(body.strip()) < 120 and links:
        score += 1.0
        issues.append("short_body_with_link")

    score = round(min(10.0, score), 2)
    verdict = "ok" if score < 3 else "risky" if score < 6 else "spammy"
    return SpamVerdict(score=score, verdict=verdict, issues=issues)
