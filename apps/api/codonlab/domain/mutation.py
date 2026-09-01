"""Mutation codes.

A mutation code is meaningless without the numbering scheme it is written in.
Every function here that renders one takes a scheme label and puts it in the
output, so it is not possible to produce a bare `A123V` through this module and
have it travel somewhere that forgets what the 123 referred to.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from codonlab.domain.aminoacid import ONE_TO_THREE, one_to_three

# wild-type residue, position, optional PDB insertion code, mutant residue.
# The insertion code is greedy on letters before the final residue, so H100AY
# parses as His-100A -> Tyr rather than as His-100 -> Ala with a stray Y.
_CODE = re.compile(
    r"^(?P<wild>[A-Z])(?P<position>\d+)(?P<insertion>[A-Z]*)(?P<mutant>[A-Z])$",
    re.IGNORECASE,
)


class MutationParseError(ValueError):
    """Raised when a string is not a mutation code.

    Never swallowed into a default. A code we cannot read is shown back to the
    user unresolved rather than guessed at.
    """


@dataclass(frozen=True, slots=True)
class Mutation:
    """A single substitution at one position, in some numbering scheme.

    The scheme is not stored here — a Mutation is only ever interpreted through
    the Target that owns it, and duplicating the scheme onto every mutation
    would create two sources of truth for the thing most worth getting right.
    """

    wild: str
    position: int
    mutant: str
    insertion_code: str | None = None

    def __post_init__(self) -> None:
        for residue in (self.wild, self.mutant):
            if residue not in ONE_TO_THREE:
                raise MutationParseError(f"{residue!r} is not an amino acid code")
        if self.position < 1:
            raise MutationParseError("residue positions are 1-based")

    @property
    def is_synonymous(self) -> bool:
        return self.wild == self.mutant

    @property
    def label(self) -> str:
        """The position as written, including any insertion code: '100A'."""
        return f"{self.position}{self.insertion_code or ''}"

    def short(self) -> str:
        """`A123V`. Prefer `render` — this form omits the numbering scheme."""
        return f"{self.wild}{self.label}{self.mutant}"

    def hgvs(self) -> str:
        """`p.Ala123Val`, the three-letter form biologists read in papers."""
        return f"p.{one_to_three(self.wild)}{self.label}{one_to_three(self.mutant)}"

    def render(self, scheme_label: str) -> str:
        """Both forms plus the scheme. This is what the interface shows."""
        return f"{self.short()} ({self.hgvs()}, {scheme_label})"


def parse_mutation(code: str) -> Mutation:
    """Parse `A123V`, `p.Ala123Val`, or `H100AY`."""
    text = code.strip()
    if not text:
        raise MutationParseError("empty mutation code")

    if text.lower().startswith("p."):
        return _parse_hgvs(text[2:])

    match = _CODE.match(text)
    if match is None:
        raise MutationParseError(f"{code!r} is not a mutation code")
    return Mutation(
        wild=match["wild"].upper(),
        position=int(match["position"]),
        mutant=match["mutant"].upper(),
        insertion_code=(match["insertion"] or None) and match["insertion"].upper(),
    )


_HGVS = re.compile(
    r"^(?P<wild>[A-Za-z]{3})(?P<position>\d+)(?P<insertion>[A-Z]*)(?P<mutant>[A-Za-z]{3})$"
)


def _parse_hgvs(body: str) -> Mutation:
    text = body.strip().strip("()")
    match = _HGVS.match(text)
    if match is None:
        raise MutationParseError(f"p.{body!r} is not a three-letter mutation code")

    from codonlab.domain.aminoacid import THREE_TO_ONE

    wild = THREE_TO_ONE.get(match["wild"].upper())
    mutant = THREE_TO_ONE.get(match["mutant"].upper())
    if wild is None or mutant is None:
        raise MutationParseError(f"p.{body!r} names an unknown amino acid")

    return Mutation(
        wild=wild,
        position=int(match["position"]),
        mutant=mutant,
        insertion_code=(match["insertion"] or None) and match["insertion"].upper(),
    )


def parse_mutation_set(codes: str) -> tuple[Mutation, ...]:
    """Parse `A123V/L45M` or `A123V,L45M` into an ordered set of mutations.

    Rejects two mutations at the same position — a variant cannot carry both,
    and accepting it would silently produce a design that cannot be built.
    """
    parts = [part for part in re.split(r"[/,+\s]+", codes.strip()) if part]
    mutations = tuple(parse_mutation(part) for part in parts)

    seen: dict[str, Mutation] = {}
    for mutation in mutations:
        if mutation.label in seen:
            raise MutationParseError(
                f"position {mutation.label} appears twice: "
                f"{seen[mutation.label].short()} and {mutation.short()}"
            )
        seen[mutation.label] = mutation
    return mutations


def format_mutation_set(mutations: tuple[Mutation, ...]) -> str:
    """`A123V/L45M`, ordered by position so the same set always renders alike."""
    ordered = sorted(mutations, key=lambda m: (m.position, m.insertion_code or ""))
    return "/".join(mutation.short() for mutation in ordered)
