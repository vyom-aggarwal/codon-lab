"""Matching uploaded bench measurements to the variants a run ranked.

Specification §5.9: "fuzzy-join to variants by mutation code with manual
override". This module is the join. It is pure — no database, no session — so
every rule below is testable without a stack.

Three decisions shape it, all recorded in ARCHITECTURE.md §17.

**A join is exact, or it is not a join.** A row matches a variant when the
parsed wild-type residue, the position *and* the mutant residue all agree with
the canonical code. Nothing is matched on string similarity: ``A123V`` and
``A123L`` differ by one character and are different experiments, so an
edit-distance threshold would silently attribute a measurement to the wrong
variant. That is the one error this module exists to prevent, and there is no
cutoff anywhere in it that could be set wrong.

**A wild-type mismatch is a signal, not a nuisance.** When the position and the
mutant agree but the wild-type residue does not, the row is *not* joined with a
warning — it is held back, because a systematic wild-type mismatch is what a
numbering-scheme shift looks like. Consuming that signal as a per-row warning
would throw away the evidence needed to diagnose the whole file. HANDOFF.md §8
records mutation codes written in the wrong scheme as the single most expensive
error class in this application.

**An offset is proposed only when it is unanimous and unique.** If one constant
shift explains *every* unjoined row that can testify, and no other shift does,
it is offered to the user with the evidence. Otherwise nothing is offered and
the reason is stated. This is deliberately the same shape as
``domain/numbering.reconcile``, which returns ``NEEDS_ALIGNMENT`` and stops
rather than picking among candidate offsets: a scheme shift is a systematic
transform, so "explains most rows" is not a weaker version of the right answer,
it is evidence that this is not a scheme shift at all. There is no "fraction of
rows that must agree" constant here, because a threshold set by anyone but the
owner would be an invented scientific default.

Nothing here is ever applied silently. A proposal is returned; the caller shows
it; the user accepts or rejects it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from codonlab.domain.mutation import (
    Mutation,
    MutationParseError,
    format_mutation_set,
    parse_mutation_set,
)


@dataclass(frozen=True, slots=True)
class UploadedRow:
    """One row of an upload, after column mapping and before interpretation.

    ``raw_label`` is kept exactly as the file wrote it, all the way into
    ``Measurement.raw_label``, so a row that failed to join can be read back in
    the user's own notation rather than in ours.
    """

    #: 1-based row number in the uploaded file, so a message can name the row.
    index: int
    raw_label: str
    value: float
    sd: float | None = None
    replicate: int | None = None
    extra: Mapping[str, str] | None = None


@dataclass(frozen=True, slots=True)
class KnownVariant:
    """A variant the run already carries, as the join needs to see it.

    ``label`` is the canonical scheme's name for the position — the thing a
    mutation code is written in. ``sequence_position`` is carried through only
    so the caller can hand it back; the join never matches on it, because
    matching on a sequence index would reintroduce the very confusion the
    canonical scheme exists to remove.
    """

    code: str
    wild: str
    label: str
    mutant: str
    sequence_position: int | None = None


class JoinOutcome(StrEnum):
    """Why a row did or did not join. Every value is shown to the user."""

    JOINED = "joined"
    #: The text is not a mutation code in any notation this product reads.
    UNPARSEABLE = "unparseable"
    #: Reads as a mutation code, but this run has no such position at all.
    #: The whole-file offset check is built from these and the mismatches.
    UNKNOWN_POSITION = "unknown_position"
    #: The position is known and its wild-type residue disagrees with the row.
    #: The scheme-drift signal.
    WILD_TYPE_MISMATCH = "wild_type_mismatch"
    #: Position and wild-type agree; this run has no variant for that mutant.
    #: Usually a mutation the lab made that the run did not rank.
    NO_SUCH_VARIANT = "no_such_variant"
    #: More than one mutation in the code, and no design stacks that exact set.
    UNKNOWN_COMBINATION = "unknown_combination"


@dataclass(frozen=True, slots=True)
class JoinedRow:
    row: UploadedRow
    outcome: JoinOutcome
    #: The canonical code this row joined to, or None.
    code: str | None
    #: What happened, in the words the interface shows. Never empty for a
    #: non-join: a row the product could not place says why on its own line.
    detail: str

    @property
    def joined(self) -> bool:
        return self.outcome is JoinOutcome.JOINED


@dataclass(frozen=True, slots=True)
class ShiftedRow:
    """One row as a candidate offset would reinterpret it."""

    index: int
    raw_label: str
    #: The canonical code the shift would attribute this row to.
    code: str


@dataclass(frozen=True, slots=True)
class OffsetProposal:
    """A single constant shift that explains every unjoined row that can testify.

    Returned for the user to accept or reject. Never applied by this module, and
    never applied by the caller without an explicit instruction — the whole
    point of surfacing it is that the decision is the user's.
    """

    offset: int
    #: Rows the shift places on a variant this run actually has.
    would_join: tuple[ShiftedRow, ...]
    #: Rows whose wild-type residue the shift explains, but for which the run
    #: holds no variant with that mutant. They stay unjoined if it is accepted,
    #: and saying so up front stops the proposal overstating what it fixes.
    explained_without_variant: tuple[ShiftedRow, ...]
    #: How many rows testified to the offset at all.
    witnesses: int


@dataclass(frozen=True, slots=True)
class JoinResult:
    rows: tuple[JoinedRow, ...]
    proposal: OffsetProposal | None
    #: Why no offset is proposed, when none is. Stated rather than left blank,
    #: so "we found nothing" and "we did not look" are distinguishable.
    proposal_note: str

    @property
    def joined_count(self) -> int:
        return sum(1 for row in self.rows if row.joined)

    @property
    def unjoined_count(self) -> int:
        return len(self.rows) - self.joined_count


def _numeric_label(label: str) -> int | None:
    """The label as an integer, or None when it carries an insertion code.

    Insertion codes break the constant-offset assumption exactly as they do in
    ``numbering.reconcile_exact``: 100, 100A and 100B are three residues that
    advance the author number once. Such rows are excluded from offset detection
    rather than approximated.
    """
    try:
        return int(label)
    except ValueError:
        return None


def _parse(text: str) -> tuple[Mutation, ...] | None:
    """Parse one cell into an ordered mutation set, or None if it is not one.

    Delegates to ``domain.mutation``, which already reads ``A123V``,
    ``p.Ala123Val``, ``H100AY`` and ``/``, ``,``, ``+`` separated sets. There is
    one definition of what a mutation code is in this codebase and this is not a
    second one.
    """
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return parse_mutation_set(stripped)
    except MutationParseError:
        return None


def join(
    rows: Iterable[UploadedRow],
    variants: Iterable[KnownVariant],
    *,
    scheme_label: str,
) -> JoinResult:
    """Match every uploaded row against the run's variants.

    Returns one ``JoinedRow`` per input row, in input order, plus at most one
    offset proposal. **Every row comes back**, joined or not: ``Measurement``
    carries a nullable ``variant_id`` precisely so a row that could not be
    placed survives import and can be resolved by hand, rather than being
    dropped at the door.

    ``scheme_label`` is only used in the messages. It is required rather than
    optional because a message about a position that does not name its numbering
    scheme is the ambiguity this application spends the most effort avoiding.
    """
    known = list(variants)
    by_code = {variant.code: variant for variant in known}

    # Position label -> the wild-type residue the canonical scheme has there.
    # Built from the variants themselves, so it cannot disagree with them.
    wild_at: dict[str, str] = {}
    for variant in known:
        wild_at.setdefault(variant.label, variant.wild)

    # Position label -> the mutants this run actually ranked there. Separates
    # "no such position" from "that substitution was not ranked", which are
    # different problems with different remedies.
    mutants_at: dict[str, set[str]] = {}
    for variant in known:
        mutants_at.setdefault(variant.label, set()).add(variant.mutant)

    results: list[JoinedRow] = []
    #: Rows eligible to testify about a whole-file offset, as (row, mutation).
    witnesses: list[tuple[UploadedRow, Mutation]] = []

    for row in rows:
        parsed = _parse(row.raw_label)
        if parsed is None:
            results.append(
                JoinedRow(
                    row=row,
                    outcome=JoinOutcome.UNPARSEABLE,
                    code=None,
                    detail=f"{row.raw_label!r} is not a mutation code.",
                )
            )
            continue

        code = format_mutation_set(parsed)
        if code in by_code:
            results.append(JoinedRow(row=row, outcome=JoinOutcome.JOINED, code=code, detail=""))
            continue

        if len(parsed) > 1:
            # A stacked design joins by its whole set or not at all. Attributing
            # a combination measurement to one of its components would be a
            # correspondence nothing in the data supports.
            results.append(
                JoinedRow(
                    row=row,
                    outcome=JoinOutcome.UNKNOWN_COMBINATION,
                    code=None,
                    detail=(
                        f"No design in this run stacks {code} in {scheme_label} numbering."
                    ),
                )
            )
            continue

        mutation = parsed[0]
        label = mutation.label
        here = wild_at.get(label)

        if here is None:
            results.append(
                JoinedRow(
                    row=row,
                    outcome=JoinOutcome.UNKNOWN_POSITION,
                    code=None,
                    detail=f"This run has no position {label} in {scheme_label} numbering.",
                )
            )
            witnesses.append((row, mutation))
            continue

        if here != mutation.wild:
            results.append(
                JoinedRow(
                    row=row,
                    outcome=JoinOutcome.WILD_TYPE_MISMATCH,
                    code=None,
                    detail=(
                        f"Position {label} is {here} in {scheme_label} numbering, "
                        f"not {mutation.wild}."
                    ),
                )
            )
            witnesses.append((row, mutation))
            continue

        results.append(
            JoinedRow(
                row=row,
                outcome=JoinOutcome.NO_SUCH_VARIANT,
                code=None,
                detail=(
                    f"{mutation.wild}{label} is in this run, but {mutation.mutant} "
                    "was not among its ranked substitutions."
                ),
            )
        )

    proposal, note = _propose_offset(witnesses, wild_at, mutants_at, by_code)
    return JoinResult(rows=tuple(results), proposal=proposal, proposal_note=note)


def _propose_offset(
    witnesses: Sequence[tuple[UploadedRow, Mutation]],
    wild_at: Mapping[str, str],
    mutants_at: Mapping[str, set[str]],
    by_code: Mapping[str, KnownVariant],
) -> tuple[OffsetProposal | None, str]:
    """The one shift that explains every witness, if exactly one does.

    A witness is an unjoined row whose position is either absent from the run or
    holds a different wild-type residue — the two shapes a numbering shift takes.
    Rows that failed for any other reason are not evidence about numbering and
    do not vote.

    Note what the unanimity rule buys with a single witness: one row is
    explained by many offsets, so the intersection is large, so nothing is
    proposed. One row is not evidence of a systematic shift, and the rule
    reaches that conclusion without a minimum-rows constant to get wrong.
    """
    if not witnesses:
        return None, "Every row was placed, so no numbering shift was looked for."

    testable = [
        (row, mutation)
        for row, mutation in witnesses
        if _numeric_label(mutation.label) is not None
    ]
    if not testable:
        return None, (
            "The unplaced rows all carry insertion codes, which a constant "
            "numbering shift cannot describe."
        )

    numeric_positions = {
        value: residue
        for label, residue in wild_at.items()
        if (value := _numeric_label(label)) is not None
    }
    if not numeric_positions:
        return None, "This run has no plainly numbered positions to shift onto."

    def offsets_for(mutation: Mutation) -> set[int]:
        position = _numeric_label(mutation.label)
        assert position is not None  # guaranteed by the `testable` filter above
        return {
            candidate - position
            for candidate, residue in numeric_positions.items()
            if residue == mutation.wild and candidate != position
        }

    # An offset survives only if it explains every witness — see the docstring.
    surviving = offsets_for(testable[0][1])
    for _, mutation in testable[1:]:
        surviving &= offsets_for(mutation)
        if not surviving:
            break

    if not surviving:
        return None, (
            f"No single numbering shift explains all {len(testable)} unplaced rows, "
            "so none is offered."
        )
    if len(surviving) > 1:
        return None, (
            f"{len(surviving)} different numbering shifts explain the unplaced rows "
            "equally well, so none is offered. Resolve these rows by hand."
        )

    offset = surviving.pop()
    would_join: list[ShiftedRow] = []
    without_variant: list[ShiftedRow] = []
    for row, mutation in testable:
        position = _numeric_label(mutation.label)
        assert position is not None
        label = str(position + offset)
        shifted = f"{mutation.wild}{label}{mutation.mutant}"
        target = ShiftedRow(index=row.index, raw_label=row.raw_label, code=shifted)
        if shifted in by_code and mutation.mutant in mutants_at.get(label, set()):
            would_join.append(target)
        else:
            without_variant.append(target)

    return (
        OffsetProposal(
            offset=offset,
            would_join=tuple(would_join),
            explained_without_variant=tuple(without_variant),
            witnesses=len(testable),
        ),
        "",
    )


def apply_offset(
    result: JoinResult,
    variants: Iterable[KnownVariant],
    *,
    offset: int,
    scheme_label: str,
) -> JoinResult:
    """Re-join every unplaced row with a numbering shift the user accepted.

    Only ever called with an offset a person chose. Rows that were already
    joined are untouched, and rows the shift still cannot place stay unjoined
    with a fresh reason — accepting a shift is not a promise that everything
    resolves.
    """
    known = list(variants)

    shifted_rows: list[UploadedRow] = []
    passthrough: dict[int, JoinedRow] = {}
    for entry in result.rows:
        parsed = None if entry.joined else _parse(entry.row.raw_label)
        position = (
            None
            if parsed is None or len(parsed) != 1
            else _numeric_label(parsed[0].label)
        )
        if parsed is None or position is None:
            passthrough[entry.row.index] = entry
            continue
        mutation = parsed[0]
        shifted_rows.append(
            UploadedRow(
                index=entry.row.index,
                # Only the code being tested moves. `raw_label` on the original
                # row is what the file said and is restored below, so accepting
                # a shift never overwrites the user's own notation.
                raw_label=f"{mutation.wild}{position + offset}{mutation.mutant}",
                value=entry.row.value,
                sd=entry.row.sd,
                replicate=entry.row.replicate,
                extra=entry.row.extra,
            )
        )

    rejoined = join(shifted_rows, known, scheme_label=scheme_label)
    by_index = {entry.row.index: entry for entry in rejoined.rows}

    merged: list[JoinedRow] = []
    for entry in result.rows:
        if entry.row.index in passthrough:
            merged.append(passthrough[entry.row.index])
            continue
        fresh = by_index[entry.row.index]
        merged.append(
            JoinedRow(
                row=entry.row,
                outcome=fresh.outcome,
                code=fresh.code,
                detail=fresh.detail,
            )
        )

    return JoinResult(
        rows=tuple(merged),
        proposal=None,
        proposal_note=f"A numbering shift of {offset:+d} was applied.",
    )


def resolve_manually(
    result: JoinResult, *, row_index: int, code: str | None, known_codes: Sequence[str]
) -> JoinResult:
    """Point one row at a variant by hand, or explicitly unjoin it.

    Specification §5.9 requires manual override. The override is by canonical
    code and is checked against the run's own variants, so a typo produces a
    refusal rather than a measurement filed against nothing.
    """
    if code is not None and code not in set(known_codes):
        raise ValueError(f"{code!r} is not a variant in this run")

    merged: list[JoinedRow] = []
    for entry in result.rows:
        if entry.row.index != row_index:
            merged.append(entry)
        elif code is None:
            merged.append(
                JoinedRow(
                    row=entry.row,
                    outcome=JoinOutcome.NO_SUCH_VARIANT,
                    code=None,
                    detail="Unjoined by hand.",
                )
            )
        else:
            merged.append(
                JoinedRow(
                    row=entry.row,
                    outcome=JoinOutcome.JOINED,
                    code=code,
                    detail=f"Joined to {code} by hand.",
                )
            )
    return JoinResult(
        rows=tuple(merged), proposal=result.proposal, proposal_note=result.proposal_note
    )
