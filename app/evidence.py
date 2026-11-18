"""Honesty rule: a suggested skill is kept only if its evidence appears in what the user wrote.

The model is asked for a short quote from the user's text. We check that quote against the
user's own text (resume or description, plus raw journal entries). Small wording changes are
allowed, but most of the quote's words must appear in a single source.
"""

import re

WORD = re.compile(r"[a-z0-9]+")
MIN_WORDS = 3  # shorter quotes prove too little to count as evidence
MATCH_RATIO = 0.9  # share of the quote's words that must appear in one source


def _words(s: str) -> list[str]:
    return WORD.findall((s or "").lower())


def supported(evidence: str, sources: list[str]) -> bool:
    """True if `evidence` is backed by one of the user's source texts."""
    quote = _words(evidence)
    if len(quote) < MIN_WORDS:
        return False
    quote_text = " " + " ".join(quote) + " "
    for src in sources:
        src_text = " " + " ".join(_words(src)) + " "
        if quote_text in src_text:
            return True
        hits = sum(1 for w in quote if f" {w} " in src_text)
        if hits / len(quote) >= MATCH_RATIO:
            return True
    return False


def keep_supported(skills: list[dict], sources: list[str]) -> tuple[list[dict], int]:
    """Return (kept skills, number removed)."""
    kept = [s for s in skills if supported(s.get("evidence", ""), sources)]
    return kept, len(skills) - len(kept)
