"""Goal parsing.

One interface, two implementations, chosen by configuration. Claude reads the
sentence; the rule parser matches keywords and always runs when Claude is
unavailable — no key, network failure, malformed output, or a safety refusal.

A parser is not a `Predictor`: it produces no scientific number and has no
weights hash to cite, which is why this sits beside `providers/` rather than
inside it. What it produces is a proposal the user must confirm.
"""

from __future__ import annotations

from codonlab.domain.goal import ParsedGoal
from codonlab.parsers import claude, rules


def parse(text: str) -> ParsedGoal:
    """Parse a goal, falling back to rules whenever Claude cannot.

    The fallback is silent to the caller but never to the user: a rule-based
    parse carries a badge and a note saying so, and the note explains why it
    fell back rather than leaving the user to wonder.
    """
    if not text.strip():
        return rules.parse(text)

    if not claude.is_configured():
        return rules.parse(text)

    try:
        return claude.parse(text)
    except claude.ParserUnavailableError as error:
        fallback = rules.parse(text)
        return ParsedGoal(
            raw_text=fallback.raw_text,
            spec=fallback.spec,
            method=fallback.method,
            matched_phrases=fallback.matched_phrases,
            note=f"{error} Fell back to keyword matching — check every chip.",
        )


__all__ = ["claude", "parse", "rules"]
