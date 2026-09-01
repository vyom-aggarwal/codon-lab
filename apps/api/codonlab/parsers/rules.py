"""Deterministic goal parser.

Keyword and pattern matching, no network, fully reproducible. It is the offline
path and the test path, and it runs whenever no API key is configured.

Its output is always badged as rule-based. That badge is not modesty — this
parser matches phrases, it does not read sentences, and a scientist looking at
chips deserves to know which of those produced them.

Where it is unsure it says nothing. An unmatched clause goes to `unparsed` and
is shown back to the user rather than dropped.
"""

from __future__ import annotations

import re

from codonlab.domain.goal import (
    Budget,
    GoalSpec,
    Objective,
    ParsedGoal,
    ParseMethod,
    TargetValue,
)

#: Objective keywords, most specific first — "melting temperature" must win over
#: a bare "temperature", and solvent tolerance over generic stability.
_OBJECTIVE_PATTERNS: tuple[tuple[Objective, re.Pattern[str]], ...] = (
    (
        Objective.SOLVENT_TOLERANCE,
        # Either word order: "solvent tolerance" and "stability in organic
        # cosolvent" are the same goal. `co-?solvent` is spelled out because a
        # \b before "solvent" does not match inside "cosolvent".
        re.compile(
            r"\b(?:co-?solvent|solvent|dmso|methanol|ethanol|organic)\b.{0,40}"
            r"\b(?:toleran\w*|stabilit\w*|stable|resist\w*)\b"
            r"|\b(?:toleran\w*|stabilit\w*|stable|resist\w*)\b.{0,40}"
            r"\b(?:co-?solvent|solvent|dmso|methanol|ethanol|organic)\b",
            re.I,
        ),
    ),
    (
        Objective.THERMOSTABILITY,
        re.compile(
            r"\bthermostab\w*|\bthermal\s+stab\w*|\bmelting\s+temperat\w*|\bt\s?m\b"
            r"|\bheat[- ]stab\w*|\bsurvive\b.{0,20}\b\d+\s*°?\s*c\b"
            r"|\bstab\w*\b.{0,20}\b(temperat\w*|heat)\b",
            re.I,
        ),
    ),
    (
        Objective.BINDING_AFFINITY,
        re.compile(r"\baffinit\w*|\bbinding\b|\bk\s?d\b|\bdissociation\b", re.I),
    ),
    (
        Objective.SOLUBILITY,
        re.compile(r"\bsolubilit\w*|\bsoluble\b|\baggregat\w*", re.I),
    ),
    (
        Objective.EXPRESSION,
        re.compile(r"\bexpress\w*|\byield\b|\btitre\b|\btiter\b", re.I),
    ),
    (
        Objective.SPECIFICITY,
        re.compile(r"\bspecificit\w*|\bselectiv\w*|\bpromiscuit\w*|\bspecific\b", re.I),
    ),
    (
        Objective.ACTIVITY,
        re.compile(r"\bactivit\w*|\bkcat\b|\bturnover\b|\bcatalytic\s+rate\b", re.I),
    ),
)

#: A temperature the user wrote. Only °C and °F — a bare number is not a
#: temperature, and guessing its unit is exactly the kind of invention this
#: module refuses.
_TEMPERATURE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?:°|degrees?\s*)?\s*(?P<unit>c|f|celsius|fahrenheit)\b",
    re.I,
)

_VARIANT_COUNT = re.compile(
    r"\b(?P<value>\d+)\s*(?:different\s+)?(?:variants?|mutants?|designs?|constructs?)\b",
    re.I,
)
#: 96- and 384-well plates are the units labs actually budget in.
_PLATE = re.compile(r"\b(?:one|a|1)\s+(?P<size>96|384)[- ]well\s+plate\b", re.I)
_MONEY = re.compile(r"(?P<symbol>[$£€])\s?(?P<value>[\d,]+(?:\.\d+)?)\s*(?P<k>k\b)?", re.I)

_CURRENCY_BY_SYMBOL = {"$": "USD", "£": "GBP", "€": "EUR"}

#: Expression hosts, mapped to the name a codon-usage table would be keyed by.
_HOSTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Escherichia coli", re.compile(r"\be\.?\s?coli\b|\bescherichia\b", re.I)),
    ("Saccharomyces cerevisiae", re.compile(r"\bs\.?\s?cerevisiae\b|\bbaker'?s yeast\b", re.I)),
    ("Pichia pastoris", re.compile(r"\bpichia\b|\bkomagataella\b", re.I)),
    ("Bacillus subtilis", re.compile(r"\bb\.?\s?subtilis\b|\bbacillus\b", re.I)),
    ("HEK293", re.compile(r"\bhek\s?293\b", re.I)),
    ("CHO", re.compile(r"\bcho\b(?!\w)", re.I)),
    ("Insect (Sf9)", re.compile(r"\bsf9\b|\bbaculovirus\b", re.I)),
    # Bare "yeast" last, so a named yeast wins.
    ("Yeast", re.compile(r"\byeast\b", re.I)),
)

_ASSAYS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Differential scanning fluorimetry", re.compile(r"\bdsf\b|\bthermal\s+shift\b", re.I)),
    ("Differential scanning calorimetry", re.compile(r"\bdsc\b|\bcalorimetr\w*", re.I)),
    ("Circular dichroism", re.compile(r"\bcircular\s+dichroism\b|\bcd\s+melt\w*", re.I)),
    ("Enzyme kinetics", re.compile(r"\bkinetics?\b|\bmichaelis\b|\bkcat/\s?km\b", re.I)),
    ("Plate reader", re.compile(r"\bplate\s+reader\b|\babsorbance\b|\bfluorescence\b", re.I)),
    ("SDS-PAGE", re.compile(r"\bsds[- ]page\b|\bgel\b", re.I)),
)

#: Clauses stating something must be held constant. The captured group is the
#: property, kept in the user's own words.
_PRESERVE = (
    re.compile(
        r"\bwithout\s+(?:killing|losing|sacrificing|compromising|harming|hurting)\s+"
        r"(?:the\s+|its\s+)?(?P<what>[\w\s/-]{2,40}?)(?=[.,;]|$|\s+(?:and|but|while))",
        re.I,
    ),
    re.compile(
        r"\b(?:while\s+)?(?:preserv\w*|maintain\w*|retain\w*|keep\w*)\s+"
        r"(?:the\s+|its\s+)?(?P<what>[\w\s/-]{2,40}?)(?=[.,;]|$|\s+(?:and|but|while))",
        re.I,
    ),
    re.compile(
        r"\b(?:don'?t|do\s+not|must\s+not)\s+(?:lose|kill|reduce|sacrifice)\s+"
        r"(?:the\s+|its\s+)?(?P<what>[\w\s/-]{2,40}?)(?=[.,;]|$|\s+(?:and|but|while))",
        re.I,
    ),
)


def _find_objective(text: str) -> tuple[Objective | None, str | None, list[str]]:
    for objective, pattern in _OBJECTIVE_PATTERNS:
        match = pattern.search(text)
        if match:
            return objective, match.group(0).strip(), [match.group(0).strip()]
    return None, None, []


def _find_temperature(text: str) -> tuple[TargetValue | None, list[str]]:
    match = _TEMPERATURE.search(text)
    if match is None:
        return None, []
    unit = match.group("unit").upper()[0]
    return TargetValue(value=float(match.group("value")), unit=f"°{unit}"), [match.group(0)]


def _find_budget(text: str) -> tuple[Budget, list[str]]:
    matched: list[str] = []
    variants: int | None = None
    amount: float | None = None
    currency: str | None = None

    plate = _PLATE.search(text)
    if plate:
        variants = int(plate.group("size"))
        matched.append(plate.group(0))
    else:
        count = _VARIANT_COUNT.search(text)
        if count:
            variants = int(count.group("value"))
            matched.append(count.group(0))

    money = _MONEY.search(text)
    if money:
        raw = float(money.group("value").replace(",", ""))
        amount = raw * 1000 if money.group("k") else raw
        currency = _CURRENCY_BY_SYMBOL.get(money.group("symbol"))
        matched.append(money.group(0))

    return Budget(variants=variants, amount=amount, currency=currency), matched


def _find_first(
    text: str, table: tuple[tuple[str, re.Pattern[str]], ...]
) -> tuple[str | None, list[str]]:
    for label, pattern in table:
        match = pattern.search(text)
        if match:
            return label, [match.group(0).strip()]
    return None, []


def _find_preserve(text: str) -> tuple[tuple[str, ...], list[str]]:
    found: list[str] = []
    matched: list[str] = []
    for pattern in _PRESERVE:
        for match in pattern.finditer(text):
            phrase = " ".join(match.group("what").split()).strip(" .,;")
            if phrase and phrase.lower() not in {item.lower() for item in found}:
                found.append(phrase)
                matched.append(match.group(0).strip())
    return tuple(found), matched


def _leftover_clauses(text: str, matched: list[str]) -> tuple[str, ...]:
    """Clauses no pattern claimed, so the user can see what was not understood."""
    remaining = text
    for phrase in matched:
        remaining = remaining.replace(phrase, " ")

    clauses = [" ".join(clause.split()) for clause in re.split(r"[.;,]|\band\b|\bbut\b", remaining)]
    # Two words is the floor: single stray words are connective debris, not
    # clauses the user would recognise as having been missed.
    return tuple(clause for clause in clauses if len(clause.split()) >= 2)


def parse(text: str) -> ParsedGoal:
    """Parse a goal deterministically. Never raises; an unreadable goal parses
    to an empty spec, which the UI reports as needing an objective."""
    cleaned = " ".join(text.split())
    matched: list[str] = []

    objective, detail, hits = _find_objective(cleaned)
    matched += hits

    target, hits = _find_temperature(cleaned)
    matched += hits

    preserve, hits = _find_preserve(cleaned)
    matched += hits

    budget, hits = _find_budget(cleaned)
    matched += hits

    host, hits = _find_first(cleaned, _HOSTS)
    matched += hits

    assay, hits = _find_first(cleaned, _ASSAYS)
    matched += hits

    # A temperature only belongs on the objective if the objective is about
    # temperature. "65 °C" in a solvent-tolerance goal is an assay condition,
    # not a target, and attaching it would invent a goal the user never set.
    if objective is not Objective.THERMOSTABILITY:
        target = None

    spec = GoalSpec(
        objective=objective,
        objective_detail=detail,
        target_value=target,
        preserve=preserve,
        budget=budget,
        expression_host=host,
        assay=assay,
        unparsed=_leftover_clauses(cleaned, matched),
    )

    return ParsedGoal(
        raw_text=text,
        spec=spec,
        method=ParseMethod.RULES,
        matched_phrases=tuple(matched),
        note=(
            "Parsed by keyword matching, not by reading the sentence. Check every "
            "chip before confirming."
        ),
    )
