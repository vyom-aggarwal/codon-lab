"""Resolving one numbering scheme against another.

The structure viewer addresses residues in the structure file's own author
numbering. The table shows the canonical scheme the user confirmed. On the
seeded lipase those are 108 and Ser77 for the same residue, so getting this
wrong renders a structure beautifully, focused on the wrong residue — which is
worse than not rendering it at all, because it looks right.

Everything here is a function of its arguments: a label list per scheme, indexed
by 1-based sequence position, exactly as `NumberingScheme.offsets` stores them.
That makes the resolution testable without a structure, a browser, or a GPU,
which is the point — a visual check cannot tell a correct focus from a confident
wrong one.

Nothing here converts between schemes by arithmetic. There is no offset: the
lookup goes through the sequence index both schemes are indexed by, because a
constant offset is a lie for the three cases that actually occur (Ambler
numbering skips residues, crystal structures leave gaps, insertion codes are not
integers).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from codonlab.domain.mutation import MutationParseError, parse_mutation


class SchemeResolutionError(ValueError):
    """A residue could not be located unambiguously in a numbering scheme."""

    def __init__(self, message: str, remedy: str) -> None:
        super().__init__(message)
        self.remedy = remedy


def positions_by_label(labels: Sequence[str | None]) -> dict[str, int]:
    """Map each label to the 1-based sequence position carrying it.

    Duplicates are refused rather than resolved. A scheme that gives two residues
    the same label cannot say which one a mutation code means, and silently
    keeping the last one — which is what a plain dict comprehension does — would
    put the viewer on a residue the user did not name.
    """
    found: dict[str, int] = {}
    duplicates: dict[str, list[int]] = {}

    for index, label in enumerate(labels):
        if label is None:
            continue
        position = index + 1
        if label in found:
            duplicates.setdefault(label, [found[label]]).append(position)
            continue
        found[label] = position

    if duplicates:
        detail = ", ".join(
            f"{label} at sequence positions {positions}" for label, positions in duplicates.items()
        )
        raise SchemeResolutionError(
            f"This numbering scheme labels more than one residue the same way: {detail}.",
            "Reconcile the structure again — a scheme cannot name two residues identically.",
        )
    return found


def author_label_at(author_labels: Sequence[str | None], sequence_position: int) -> str | None:
    """How the structure numbers the residue at this 1-based sequence index.

    None where the structure does not cover it — an unresolved loop, or a
    construct shorter than the sequence. None is not a failure; it is the honest
    answer, and the caller renders it as unavailable rather than guessing.
    """
    if not 1 <= sequence_position <= len(author_labels):
        return None
    return author_labels[sequence_position - 1]


@dataclass(frozen=True, slots=True)
class FocusResolution:
    """Where a mutation code points, in every numbering that matters."""

    code: str
    #: The label the code is written in — the canonical scheme's name for it.
    canonical_label: str
    #: 1-based index into the target sequence. What everything internal joins on.
    sequence_position: int
    #: What the structure file calls it. What the viewer must be given.
    author_label: str | None
    #: Set when the residue cannot be located in the structure, and why.
    unavailable: str | None = None

    @property
    def is_focusable(self) -> bool:
        return self.author_label is not None


def resolve_focus(
    code: str,
    canonical_labels: Sequence[str | None],
    author_labels: Sequence[str | None],
) -> FocusResolution:
    """Resolve a mutation code to the residue the structure viewer should focus.

    `code` is written in the canonical scheme — `S77A`, not `S108A`. Both label
    lists are indexed by sequence position, so the resolution is: find the
    sequence index the canonical scheme gives this label, then read what the
    structure calls that same index.
    """
    try:
        mutation = parse_mutation(code)
    except MutationParseError as error:
        raise SchemeResolutionError(
            f"{code!r} is not a mutation code, so it names no residue.",
            "Mutation codes look like S77A or p.Ser77Ala.",
        ) from error

    label = mutation.label
    position = positions_by_label(canonical_labels).get(label)
    if position is None:
        raise SchemeResolutionError(
            f"The canonical numbering scheme has no residue labelled {label}.",
            f"{code} was written against a different scheme, or the scheme changed "
            "since the run — re-run against the confirmed scheme.",
        )

    author = author_label_at(author_labels, position)
    unavailable = (
        None
        if author is not None
        else (
            "The structure does not cover this residue, so there is nothing to "
            "focus on. Unresolved regions are left empty rather than closed up."
        )
    )
    return FocusResolution(
        code=code,
        canonical_label=label,
        sequence_position=position,
        author_label=author,
        unavailable=unavailable,
    )
