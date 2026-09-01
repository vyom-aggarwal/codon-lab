"""Residue numbering reconciliation.

Off-by-one numbering is the most expensive error this application can make, so
nothing in this module infers silently. Reconciliation either succeeds by exact
correspondence, or it reports precisely why it could not and hands the decision
back to the user.

Two facts about real structures shape the design:

* Crystal structures have unresolved residues. A chain is normally a set of
  discontinuous runs of author numbering, not one contiguous block, so exact
  matching is done per run and the runs must agree on a single offset.
* Author numbering carries insertion codes and can start anywhere, including at
  negative numbers for expression tags. It is never assumed to start at 1.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class ResidueSlot:
    """A position as written in some numbering scheme."""

    number: int
    insertion_code: str | None = None

    @property
    def label(self) -> str:
        return f"{self.number}{self.insertion_code or ''}"

    @property
    def sort_key(self) -> tuple[int, str]:
        """Order within a chain: 100 precedes 100A precedes 100B.

        Explicit rather than dataclass `order=True`, which generates a
        comparison that raises the moment a slot without an insertion code is
        compared against one with — the exact pairing that occurs wherever
        insertion codes are used at all.
        """
        return (self.number, self.insertion_code or "")


@dataclass(frozen=True, slots=True)
class ObservedResidue:
    """One residue actually present in a structure chain."""

    slot: ResidueSlot
    residue: str


class ReconcileMethod(StrEnum):
    EXACT = "exact"
    ALIGNMENT = "alignment"


class ReconcileOutcome(StrEnum):
    RECONCILED = "reconciled"
    #: The observed residues match at more than one offset. Happens with short
    #: chains and internal repeats. The user picks; the app must not.
    AMBIGUOUS = "ambiguous"
    #: No exact correspondence. Alignment is offered as an explicit next step.
    NEEDS_ALIGNMENT = "needs_alignment"


@dataclass(frozen=True, slots=True)
class Mismatch:
    """A position where the structure and the sequence disagree."""

    canonical_index: int
    canonical_residue: str
    observed_slot: ResidueSlot
    observed_residue: str

    @property
    def canonical_position(self) -> int:
        return self.canonical_index + 1


#: Semi-global alignment parameters, stated wherever an alignment is used.
#:
#: Identity scoring rather than BLOSUM62 on purpose: this aligns a structure
#: against its own sequence, where the question is "which residue is which",
#: not "are these homologous". A substitution matrix would let a chemically
#: conservative difference slide into a match, which is exactly the silent
#: off-by-one this module exists to prevent.
#:
#: End gaps are free, so a 181-residue construct maps onto a 286-residue
#: sequence without being penalised for the ends it does not cover.
ALIGNMENT_PARAMETERS: dict[str, float] = {
    "match": 2.0,
    "mismatch": -1.0,
    "gap_open": -10.0,
    "gap_extend": -0.5,
}
ALIGNMENT_DESCRIPTION = (
    "Semi-global (free end gaps) Needleman-Wunsch with affine gap penalties and identity scoring"
)


@dataclass(frozen=True, slots=True)
class Reconciliation:
    outcome: ReconcileOutcome
    method: ReconcileMethod | None
    #: One entry per canonical residue: the slot it corresponds to, or None
    #: where the structure does not resolve it.
    mapping: tuple[ResidueSlot | None, ...]
    mismatches: tuple[Mismatch, ...]
    #: Offsets that matched, when the outcome is AMBIGUOUS.
    candidate_offsets: tuple[int, ...]
    parameters: dict[str, float] | None
    note: str

    @property
    def covered(self) -> int:
        return sum(1 for slot in self.mapping if slot is not None)

    @property
    def coverage(self) -> float:
        if not self.mapping:
            return 0.0
        return self.covered / len(self.mapping)

    @property
    def identity(self) -> float:
        """Fraction of resolved positions where the residues agree."""
        if self.covered == 0:
            return 0.0
        return (self.covered - len(self.mismatches)) / self.covered


def contiguous_runs(observed: Sequence[ObservedResidue]) -> list[list[ObservedResidue]]:
    """Split a chain into runs of consecutive author numbering.

    A break in numbering means unresolved density. Insertion codes continue the
    run they sit inside, since 100, 100A, 100B is contiguous in the structure
    even though the numbers repeat.
    """
    runs: list[list[ObservedResidue]] = []
    current: list[ObservedResidue] = []

    for residue in observed:
        if not current:
            current = [residue]
            continue
        previous = current[-1].slot
        same_number_insertion = residue.slot.number == previous.number
        next_number = residue.slot.number == previous.number + 1
        if same_number_insertion or next_number:
            current.append(residue)
        else:
            runs.append(current)
            current = [residue]

    if current:
        runs.append(current)
    return runs


def _run_sequence(run: Sequence[ObservedResidue]) -> str:
    return "".join(residue.residue for residue in run)


def _offsets_for(canonical: str, fragment: str) -> list[int]:
    """Every index in `canonical` where `fragment` occurs exactly."""
    if not fragment:
        return []
    found: list[int] = []
    start = canonical.find(fragment)
    while start != -1:
        found.append(start)
        start = canonical.find(fragment, start + 1)
    return found


def reconcile_exact(canonical: str, observed: Sequence[ObservedResidue]) -> Reconciliation | None:
    """Map by exact correspondence, or return None if there is none.

    Every run of the chain must be placeable at the same offset. Requiring one
    shared offset is what makes this safe: a structure whose loops sit at
    inconsistent offsets is a structure we have misunderstood, and it falls
    through to explicit alignment rather than being forced.
    """
    runs = contiguous_runs(observed)
    if not runs:
        return None

    # Insertion codes break the constant-offset assumption below: 100, 100A,
    # 100B occupy three sequence positions but advance the author number once.
    # Rather than approximate, hand these to alignment, which maps residue by
    # residue and cannot drift.
    if any(residue.slot.insertion_code for residue in observed):
        return None

    # Anchor on the longest run — it has the fewest spurious matches.
    anchor = max(runs, key=len)

    candidates: list[int] = []
    for position in _offsets_for(canonical, _run_sequence(anchor)):
        # The offset relates author numbering to sequence index, NOT position
        # within the resolved residues. Author numbering is continuous across an
        # unresolved loop, so this is the frame that survives missing density;
        # indexing into the resolved list would slide every residue after a gap
        # by the length of that gap.
        delta = position - anchor[0].slot.number
        if _placement_fits(canonical, runs, delta):
            candidates.append(delta)

    if not candidates:
        return None

    if len(candidates) > 1:
        return Reconciliation(
            outcome=ReconcileOutcome.AMBIGUOUS,
            method=ReconcileMethod.EXACT,
            mapping=(),
            mismatches=(),
            candidate_offsets=tuple(candidates),
            parameters=None,
            note=(
                f"The chain matches the sequence at {len(candidates)} different "
                "offsets. Choose which one is correct."
            ),
        )

    return _build(canonical, observed, candidates[0], ReconcileMethod.EXACT, None)


def _placement_fits(
    canonical: str,
    runs: Sequence[Sequence[ObservedResidue]],
    delta: int,
) -> bool:
    """True when every run lands inside the sequence and matches exactly.

    Requiring all runs to agree on one delta is the safety property: a structure
    whose fragments only fit at inconsistent offsets is one we have
    misunderstood, and it goes to explicit alignment rather than being forced.
    """
    for run in runs:
        start = run[0].slot.number + delta
        fragment = _run_sequence(run)
        if start < 0 or start + len(fragment) > len(canonical):
            return False
        if canonical[start : start + len(fragment)] != fragment:
            return False
    return True


def _build(
    canonical: str,
    observed: Sequence[ObservedResidue],
    delta: int,
    method: ReconcileMethod,
    parameters: dict[str, float] | None,
) -> Reconciliation:
    mapping: list[ResidueSlot | None] = [None] * len(canonical)
    mismatches: list[Mismatch] = []

    for residue in observed:
        index = residue.slot.number + delta
        if not 0 <= index < len(canonical):
            continue
        mapping[index] = residue.slot
        if canonical[index] != residue.residue:
            mismatches.append(
                Mismatch(
                    canonical_index=index,
                    canonical_residue=canonical[index],
                    observed_slot=residue.slot,
                    observed_residue=residue.residue,
                )
            )

    resolved = sum(1 for slot in mapping if slot is not None)
    note = (
        f"{resolved} of {len(canonical)} residues resolved in the structure"
        if method is ReconcileMethod.EXACT
        else f"{resolved} of {len(canonical)} residues aligned"
    )
    return Reconciliation(
        outcome=ReconcileOutcome.RECONCILED,
        method=method,
        mapping=tuple(mapping),
        mismatches=tuple(mismatches),
        candidate_offsets=(),
        parameters=parameters,
        note=note,
    )


def align(canonical: str, observed: Sequence[ObservedResidue]) -> Reconciliation:
    """Map by semi-global alignment. Only reached on explicit user approval.

    Gotoh's affine-gap algorithm. End gaps in the canonical sequence are free,
    so a construct covering part of the protein is not penalised for the rest.
    """
    query = _run_sequence(observed)
    if not query or not canonical:
        return Reconciliation(
            outcome=ReconcileOutcome.NEEDS_ALIGNMENT,
            method=None,
            mapping=(),
            mismatches=(),
            candidate_offsets=(),
            parameters=None,
            note="Nothing to align.",
        )

    match = ALIGNMENT_PARAMETERS["match"]
    mismatch = ALIGNMENT_PARAMETERS["mismatch"]
    gap_open = ALIGNMENT_PARAMETERS["gap_open"]
    gap_extend = ALIGNMENT_PARAMETERS["gap_extend"]

    rows, columns = len(query), len(canonical)
    negative = float("-inf")

    # best[i][j] ends with query[i-1] aligned to canonical[j-1];
    # gap_q ends with a gap in the query; gap_c ends with a gap in canonical.
    best = [[negative] * (columns + 1) for _ in range(rows + 1)]
    gap_q = [[negative] * (columns + 1) for _ in range(rows + 1)]
    gap_c = [[negative] * (columns + 1) for _ in range(rows + 1)]
    best[0][0] = 0.0

    for j in range(1, columns + 1):
        # Free leading gap in the canonical sequence.
        best[0][j] = 0.0
    for i in range(1, rows + 1):
        gap_c[i][0] = gap_open + gap_extend * (i - 1)
        best[i][0] = gap_c[i][0]

    for i in range(1, rows + 1):
        for j in range(1, columns + 1):
            score = match if query[i - 1] == canonical[j - 1] else mismatch
            best_diag = max(best[i - 1][j - 1], gap_q[i - 1][j - 1], gap_c[i - 1][j - 1])
            gap_q[i][j] = max(best[i][j - 1] + gap_open, gap_q[i][j - 1] + gap_extend)
            gap_c[i][j] = max(best[i - 1][j] + gap_open, gap_c[i - 1][j] + gap_extend)
            best[i][j] = max(best_diag + score, gap_q[i][j], gap_c[i][j])

    # Free trailing gap: start the traceback from the best cell in the last row.
    end_column = max(
        range(columns + 1),
        key=lambda j: max(best[rows][j], gap_q[rows][j], gap_c[rows][j]),
    )

    mapping: list[ResidueSlot | None] = [None] * len(canonical)
    mismatches: list[Mismatch] = []
    i, j = rows, end_column

    while i > 0 and j > 0:
        score = match if query[i - 1] == canonical[j - 1] else mismatch
        best_diag = max(best[i - 1][j - 1], gap_q[i - 1][j - 1], gap_c[i - 1][j - 1])
        current = max(best[i][j], gap_q[i][j], gap_c[i][j])

        if current == best_diag + score:
            mapping[j - 1] = observed[i - 1].slot
            if canonical[j - 1] != query[i - 1]:
                mismatches.append(
                    Mismatch(
                        canonical_index=j - 1,
                        canonical_residue=canonical[j - 1],
                        observed_slot=observed[i - 1].slot,
                        observed_residue=query[i - 1],
                    )
                )
            i, j = i - 1, j - 1
        elif current == gap_c[i][j]:
            i -= 1  # residue in the structure with no sequence counterpart
        else:
            j -= 1  # residue in the sequence not resolved in the structure

    resolved = sum(1 for slot in mapping if slot is not None)
    return Reconciliation(
        outcome=ReconcileOutcome.RECONCILED,
        method=ReconcileMethod.ALIGNMENT,
        mapping=tuple(mapping),
        mismatches=tuple(reversed(mismatches)),
        candidate_offsets=(),
        parameters=dict(ALIGNMENT_PARAMETERS),
        note=f"{resolved} of {len(canonical)} residues aligned. {ALIGNMENT_DESCRIPTION}.",
    )


def reconcile(canonical: str, observed: Sequence[ObservedResidue]) -> Reconciliation:
    """Try exact correspondence. Never falls through to alignment on its own.

    A NEEDS_ALIGNMENT outcome is a question for the user, not a stage the caller
    should quietly satisfy by calling `align`.
    """
    exact = reconcile_exact(canonical, observed)
    if exact is not None:
        return exact

    return Reconciliation(
        outcome=ReconcileOutcome.NEEDS_ALIGNMENT,
        method=None,
        mapping=(),
        mismatches=(),
        candidate_offsets=(),
        parameters=None,
        note=(
            "The structure does not correspond exactly to the sequence. This is "
            "normal for an engineered construct carrying a tag, a truncation, or "
            "a point mutation. Alignment can resolve it, and will show every "
            "difference before anything is applied."
        ),
    )


def offset_scheme(canonical: str, offset: int) -> tuple[ResidueSlot | None, ...]:
    """A scheme that renumbers the canonical sequence by a constant offset.

    Used for construct numbering: mature-protein numbering of a sequence that
    includes a signal peptide is `offset_scheme(sequence, -signal_length)`.
    """
    return tuple(ResidueSlot(number=index + 1 + offset) for index in range(len(canonical)))
