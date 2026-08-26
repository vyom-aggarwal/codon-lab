"""Stacking single mutations into one construct, and what that assumes.

Specification §5.7 asks for a combinatorial builder, "an unmissable warning that
stacked effects are assumed additive and frequently are not (epistasis), and a
flag on any pair within 8A of each other". Three things in this module are
load-bearing, and all three are about refusing to overstate.

**An additive total is not a prediction.** No model scored the double mutant. The
sum of two single-mutant values is arithmetic over numbers that already exist,
which is exactly what `domain/aggregate` is for consensus: derived on read, never
stored, and impossible to write as a `Score` because there is no `ModelVersion`
that produced it (ARCHITECTURE.md §4). `AdditiveEstimate.assumption` is not
optional text — it is a required field, so a total cannot travel anywhere without
the sentence saying what it assumes.

**A missing component makes the total missing.** If one mutation in a stack has
no value for a metric, the sum is `None`, not the sum of the rest. Adding three
of four contributions and presenting it as the total would understate the design
by exactly the amount nobody measured, and it would look like a number.

**Proximity has three states, not two.** `Proximity.UNKNOWN` exists so that "we
could not measure this pair" cannot be rendered by the same branch as "this pair
is far apart". A nullable boolean would let one `if` treat an unmeasured pair as
safe; the enum forces the third case to be handled. No structure means unknown,
and unknown means the interface says so.

Pure: no I/O, no database, no coordinates. The separations come from
`features/structure.pairwise_min_distances`, which is where a dependency on a
structure library belongs.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import combinations
from typing import Any

from catalyst.domain.mutation import MutationParseError, parse_mutation_set

#: Specification §5.7 states it: "a flag on any pair within 8A of each other."
#: Fixed by the brief. Not a default this module chose, and not a project
#: setting — a threshold the owner wrote down is not one the product may drift.
PAIR_PROXIMITY_ANGSTROM = 8.0

#: How that separation is measured. The same convention `features/structure` uses
#: for distance to the active site, and for the same reason: an arginine side
#: chain reaches roughly 7A past its own CA, so a CA-CA measurement would report
#: two residues as independent while their side chains are in contact.
#: See ARCHITECTURE.md §11.
PAIR_DISTANCE_CONVENTION = (
    "minimum non-hydrogen atom separation between the two residues, "
    "not CA-CA — see ARCHITECTURE.md §11"
)

#: The sentence that travels with every additive total. Specification §5.7 calls
#: for it to be unmissable; making it a required field of the estimate is how
#: this layer enforces that, rather than trusting a component to remember it.
ADDITIVITY_ASSUMPTION = (
    "Stacked effects are assumed additive. They frequently are not: mutations "
    "interact (epistasis), and the interaction is not predicted here. This total "
    "is the sum of single-mutant values, not a prediction for the combined "
    "construct, and no model scored this construct."
)


class Proximity(StrEnum):
    """Whether two mutated positions are close enough to interact structurally.

    `UNKNOWN` is a first-class outcome, not an error. It is what a pair reports
    when there is no structure, when the structure does not resolve one of the
    residues, or when the numbering was never reconciled — and it must never be
    rendered as though it were `BEYOND`.
    """

    WITHIN = "within"
    BEYOND = "beyond"
    UNKNOWN = "unknown"


class StackError(ValueError):
    """A combination that could not be built, with the way forward."""

    def __init__(self, message: str, remedy: str) -> None:
        super().__init__(message)
        self.remedy = remedy


@dataclass(frozen=True, slots=True)
class PairFlag:
    """One pair of mutated positions within a stacked design."""

    a_code: str
    b_code: str
    #: 1-based sequence indices. The codes carry the canonical scheme's labels;
    #: these are what geometry joins on. ARCHITECTURE.md §9 — never converted
    #: between by arithmetic.
    a_position: int
    b_position: int
    proximity: Proximity
    separation_angstrom: float | None = None
    #: Why the separation is unknown, when it is. Always set for UNKNOWN, and
    #: always None otherwise, so a caller cannot show a stale reason.
    reason: str | None = None

    @property
    def is_flagged(self) -> bool:
        """True only for a measured pair inside the cutoff.

        Deliberately not `proximity is not Proximity.BEYOND` — an unmeasured
        pair is not a flagged one, and a caller that wants to know about
        unmeasured pairs asks for `UNKNOWN` by name.
        """
        return self.proximity is Proximity.WITHIN

    def to_json(self) -> dict[str, Any]:
        return {
            "a_code": self.a_code,
            "b_code": self.b_code,
            "a_position": self.a_position,
            "b_position": self.b_position,
            "proximity": self.proximity.value,
            "separation_angstrom": self.separation_angstrom,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class AdditiveEstimate:
    """A per-metric sum over the singles in a stack, with its assumption attached.

    `total` is None whenever any component lacks a value: a partial sum presented
    as a total understates the design by exactly the contribution nobody has.
    """

    metric: str
    label: str
    unit: str | None
    sign_convention: str
    total: float | None
    #: (mutation code, value) for every component that had one.
    contributions: tuple[tuple[str, float], ...]
    #: Component codes with no value for this metric. Non-empty means total is None.
    missing: tuple[str, ...]
    #: Never empty. See the module docstring.
    assumption: str = ADDITIVITY_ASSUMPTION
    #: Per specification §7 a stability prediction is reported with an interval.
    #: A stacked design has none, and this says why rather than leaving a blank
    #: that could be read as zero uncertainty.
    interval_note: str = (
        "No interval. The single-mutant values carry none, and the additivity "
        "assumption itself has no uncertainty attached to it."
    )

    def to_json(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "label": self.label,
            "unit": self.unit,
            "sign_convention": self.sign_convention,
            "total": self.total,
            "contributions": [
                {"code": code, "value": value} for code, value in self.contributions
            ],
            "missing": list(self.missing),
            "assumption": self.assumption,
            "interval_note": self.interval_note,
        }


@dataclass(frozen=True, slots=True)
class StackedDesign:
    """A combination of single-point mutations proposed as one construct."""

    #: Component mutation codes, in the canonical scheme, ordered by position.
    codes: tuple[str, ...]
    #: The joined form, `A123V/L45M`. Ordered the same way, so the same set of
    #: mutations always produces the same code and therefore the same variant row.
    code: str
    positions: tuple[int, ...]

    @property
    def size(self) -> int:
        return len(self.codes)


def stack(
    codes: Sequence[str],
    positions: Mapping[str, int],
) -> StackedDesign:
    """Build one stacked design from a set of single-mutation codes.

    Rejects two mutations at the same position through `parse_mutation_set`,
    which is where that rule already lives — a construct cannot carry both, and
    accepting it would produce a design nobody can build.
    """
    if len(codes) < 2:
        raise StackError(
            "A stacked design needs at least two mutations.",
            "Select two or more variants, or add them individually.",
        )

    try:
        mutations = parse_mutation_set("/".join(codes))
    except MutationParseError as error:
        raise StackError(str(error), "Remove one of the two mutations at that position.") from error

    ordered = sorted(mutations, key=lambda m: (m.position, m.insertion_code or ""))
    short_codes = tuple(mutation.short() for mutation in ordered)

    missing = [code for code in short_codes if code not in positions]
    if missing:
        raise StackError(
            f"No sequence position is known for {', '.join(missing)}.",
            "These variants are not part of this run's candidate set.",
        )

    return StackedDesign(
        codes=short_codes,
        code="/".join(short_codes),
        positions=tuple(positions[code] for code in short_codes),
    )


def enumerate_stacks(
    codes: Sequence[str],
    positions: Mapping[str, int],
    *,
    size: int,
    limit: int,
) -> tuple[tuple[StackedDesign, ...], tuple[str, ...]]:
    """Every constructible combination of `size` mutations drawn from `codes`.

    Returns the designs and a list of notes describing what was left out and
    why — combinations sharing a position, and the cap if it was reached.
    Nothing is silently dropped: a truncated enumeration that does not say it was
    truncated is a design set that looks complete and is not.

    `limit` is an interface guard, not a scientific one. C(n, k) grows fast
    enough that an unbounded builder would hang the request rather than answer
    it, so the cap is stated in the notes and the caller can raise it.
    """
    if size < 2:
        raise StackError(
            "A stacked design needs at least two mutations.",
            "Choose a combination size of 2 or more.",
        )
    if size > len(codes):
        raise StackError(
            f"Cannot choose {size} mutations from a selection of {len(codes)}.",
            "Select more variants, or reduce the combination size.",
        )
    if limit < 1:
        raise StackError("The combination cap must be at least 1.", "Raise the cap.")

    designs: list[StackedDesign] = []
    notes: list[str] = []
    same_position = 0
    truncated = False

    for chosen in combinations(list(codes), size):
        try:
            designs.append(stack(chosen, positions))
        except StackError as error:
            # The only rejection `stack` makes for a well-formed selection is two
            # mutations at one position. Counted and reported, never hidden.
            if "appears twice" in str(error):
                same_position += 1
                continue
            raise
        if len(designs) >= limit:
            truncated = True
            break

    if same_position:
        notes.append(
            f"{same_position:,} combination(s) were skipped because they place two "
            "mutations at the same position, which no single construct can carry."
        )
    if truncated:
        notes.append(
            f"Stopped at the cap of {limit:,} combinations. More are constructible "
            "from this selection; raise the cap or narrow the selection to see them."
        )
    return tuple(designs), tuple(notes)


def pair_flags(
    design: StackedDesign,
    separations: Mapping[tuple[int, int], float],
    *,
    unknown_reason: str,
) -> tuple[PairFlag, ...]:
    """Flag every pair of mutated positions in a design against the 8A rule.

    `separations` is keyed by an ordered pair of sequence indices. A pair absent
    from the mapping is `UNKNOWN` and carries `unknown_reason` — it is never
    assumed to be beyond the cutoff, which is the whole reason `Proximity` has a
    third value.
    """
    flags: list[PairFlag] = []
    for (a_code, a_position), (b_code, b_position) in combinations(
        list(zip(design.codes, design.positions, strict=True)), 2
    ):
        key = (a_position, b_position) if a_position <= b_position else (b_position, a_position)
        separation = separations.get(key)
        if separation is None:
            flags.append(
                PairFlag(
                    a_code=a_code,
                    b_code=b_code,
                    a_position=a_position,
                    b_position=b_position,
                    proximity=Proximity.UNKNOWN,
                    reason=unknown_reason,
                )
            )
            continue
        flags.append(
            PairFlag(
                a_code=a_code,
                b_code=b_code,
                a_position=a_position,
                b_position=b_position,
                proximity=(
                    Proximity.WITHIN
                    if separation <= PAIR_PROXIMITY_ANGSTROM
                    else Proximity.BEYOND
                ),
                separation_angstrom=separation,
            )
        )
    return tuple(flags)


def additive(
    *,
    metric: str,
    label: str,
    unit: str | None,
    sign_convention: str,
    codes: Sequence[str],
    values: Mapping[str, float],
) -> AdditiveEstimate:
    """Sum a metric across the singles in a stack, or refuse to.

    Refusal is the interesting case. A component with no value for this metric
    makes the total `None`; the contributions that do exist are still returned,
    so the interface can show what is known without implying a total.
    """
    contributions: list[tuple[str, float]] = []
    missing: list[str] = []
    for code in codes:
        if code in values:
            contributions.append((code, values[code]))
        else:
            missing.append(code)

    total = None if missing else round(sum(value for _, value in contributions), 4)
    return AdditiveEstimate(
        metric=metric,
        label=label,
        unit=unit,
        sign_convention=sign_convention,
        total=total,
        contributions=tuple(contributions),
        missing=tuple(missing),
    )


def warning_for(designs: Iterable[StackedDesign], flags: Iterable[PairFlag]) -> dict[str, Any]:
    """The epistasis warning a design set must display, as data rather than copy.

    Returned as a record so the interface renders it in one place and cannot
    show a set containing stacked designs without it. `stacked` being zero is
    what turns the warning off — never a component's own judgement.
    """
    stacked = list(designs)
    all_flags = list(flags)
    within = [flag for flag in all_flags if flag.proximity is Proximity.WITHIN]
    unknown = [flag for flag in all_flags if flag.proximity is Proximity.UNKNOWN]

    return {
        "stacked_designs": len(stacked),
        "assumption": ADDITIVITY_ASSUMPTION,
        "cutoff_angstrom": PAIR_PROXIMITY_ANGSTROM,
        "distance_convention": PAIR_DISTANCE_CONVENTION,
        "pairs_total": len(all_flags),
        "pairs_within_cutoff": len(within),
        "pairs_unknown": len(unknown),
        "pairs": [flag.to_json() for flag in all_flags],
    }
