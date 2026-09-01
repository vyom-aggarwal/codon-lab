"""The candidate set a design run scores.

Two things this module refuses to do.

**It does not narrow.** Every single-residue substitution at every covered
position is generated, because any narrowing rule — only hydrophobics in the
core, only positions above some conservation threshold — is a scientific choice
this module has no authority to make. Narrowing happens later, from things the
user actually stated: the constraints they accepted and the budget they wrote
down.

**It does not write a mutation code in sequence numbering.** A candidate is
created from a sequence index and a label out of the target's canonical scheme,
and the code is written in the label. On the seeded lipase, sequence index 108
is Ser77 under the confirmed mature-protein scheme; a candidate called `S108A`
would name a residue 31 positions away from the one it means. Where the scheme
has no label for a position, no candidate is produced at all — a code that
cannot be written unambiguously is not written.

Position classification (core / boundary / surface) is deliberately absent. It
needs relative-solvent-accessibility cutoffs, which are an open decision with the
domain owner; a placeholder cutoff here would silently become the product's
advice. ``Variant.region`` stays null until that decision is made.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from codonlab.domain.aminoacid import STANDARD
from codonlab.domain.mutation import MutationParseError, parse_mutation

#: The 20 proteinogenic residues, in a fixed order so enumeration is reproducible.
SUBSTITUTIONS: tuple[str, ...] = tuple(sorted(STANDARD))


@dataclass(frozen=True, slots=True)
class VariantInput:
    """A candidate as a predictor sees it.

    Deliberately not the ``Variant`` table. A provider that took an ORM row would
    be a provider that needs a database session, and the seam between "what the
    product asks for" and "what a model can do" would leak in the direction that
    matters least. See ARCHITECTURE.md §4.

    ``label`` is the canonical scheme's name for the position and is what the
    code is written in. ``sequence_position`` is the 1-based index into the
    target sequence and is what everything internal joins on — constraints,
    structures, features. The two are kept apart on purpose: conflating them is
    the off-by-one this application exists to prevent.
    """

    wild: str
    label: str
    mutant: str
    sequence_position: int
    features: dict[str, object] = field(default_factory=dict)

    @property
    def code(self) -> str:
        """`S77A`, written in the canonical numbering scheme."""
        return f"{self.wild}{self.label}{self.mutant}"

    @property
    def mutations(self) -> tuple[str, ...]:
        return (self.code,)

    @property
    def is_single_point(self) -> bool:
        return True


def is_writable(wild: str, label: str, mutant: str) -> bool:
    """Whether `wild + label + mutant` is a mutation code anything can read back.

    Checked against the mutation parser rather than against a rule invented here,
    so there is one definition of what a code is. This is nomenclature, not
    science: a mature-protein scheme numbers the signal peptide at zero and
    below, and `A-30C` is not a mutation code in any notation a bench scientist
    uses.
    """
    try:
        parsed = parse_mutation(f"{wild}{label}{mutant}")
    except MutationParseError:
        return False
    return parsed.label == label


def substitutions_at(sequence: str, position: int, label: str | None) -> list[VariantInput]:
    """Every substitution at one 1-based sequence index, excluding the wild type."""
    if not 1 <= position <= len(sequence):
        raise ValueError(f"position {position} is outside a {len(sequence)}-residue sequence")

    wild = sequence[position - 1].upper()
    if wild not in STANDARD:
        # An X or a modified residue: there is no wild-type identity to mutate
        # away from, so no code could be written that a bench scientist could act
        # on. Skipped rather than guessed at.
        return []
    if label is None:
        # The canonical scheme does not cover this residue, so there is no
        # unambiguous way to name it. Refused, not approximated.
        return []

    return [
        VariantInput(wild=wild, label=label, mutant=mutant, sequence_position=position)
        for mutant in SUBSTITUTIONS
        if mutant != wild and is_writable(wild, label, mutant)
    ]


@dataclass(frozen=True, slots=True)
class Enumeration:
    candidates: tuple[VariantInput, ...]
    #: Sequence indices the canonical scheme does not label, and so cannot name.
    uncovered: tuple[int, ...]
    #: Sequence indices holding a residue outside the standard twenty.
    non_standard: tuple[int, ...]
    #: Sequence indices the scheme labels in a way no mutation code can express —
    #: in practice, the non-positive numbering a mature-protein scheme gives the
    #: signal peptide it excludes.
    unwritable: tuple[int, ...]


def enumerate_single_substitutions(sequence: str, labels: Sequence[str | None]) -> Enumeration:
    """The full single-point mutational space, in canonical numbering.

    19 candidates per covered standard residue. For a 200-residue protein that is
    a few thousand rows, which is the point: the run scores the space and the
    ranking narrows it, rather than a heuristic deciding in advance what is worth
    looking at.

    ``labels`` is the canonical scheme's label per sequence index. Passing the
    wrong scheme's labels would produce codes that are wrong in a way nothing
    downstream could detect, which is why the caller reads them from the scheme
    the user confirmed and from nowhere else.
    """
    candidates: list[VariantInput] = []
    uncovered: list[int] = []
    non_standard: list[int] = []
    unwritable: list[int] = []

    for position in range(1, len(sequence) + 1):
        label = labels[position - 1] if position <= len(labels) else None
        if sequence[position - 1].upper() not in STANDARD:
            non_standard.append(position)
            continue
        if label is None:
            uncovered.append(position)
            continue
        at_position = substitutions_at(sequence, position, label)
        if not at_position:
            unwritable.append(position)
            continue
        candidates.extend(at_position)

    return Enumeration(
        candidates=tuple(candidates),
        uncovered=tuple(uncovered),
        non_standard=tuple(non_standard),
        unwritable=tuple(unwritable),
    )


def hgvs_of(code: str) -> str:
    """``S77A`` to ``p.Ser77Ala``, insertion codes included.

    Delegates to the mutation parser rather than reimplementing it — there is one
    definition of what a mutation code is, and it is already tested. A code that
    does not parse is returned unchanged rather than mangled into something that
    looks authoritative.
    """
    try:
        return parse_mutation(code).hgvs()
    except MutationParseError:
        return code


def label_of(code: str) -> str:
    """The position as the canonical scheme names it: `77`, or `100A`.

    Read back out of the code rather than stored beside it, so the two can never
    disagree about which residue a variant is.
    """
    try:
        return parse_mutation(code).label
    except MutationParseError:
        return ""
