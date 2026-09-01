"""Numbering reconciliation.

These tests encode the failure this module exists to prevent: a residue that
looks like it corresponds to another and does not. Every case where the answer
is uncertain must surface as a question, never as a best guess.
"""

from __future__ import annotations

from codonlab.domain.numbering import (
    ObservedResidue,
    ReconcileMethod,
    ReconcileOutcome,
    ResidueSlot,
    align,
    contiguous_runs,
    offset_scheme,
    reconcile,
    reconcile_exact,
)


def chain(sequence: str, start: int = 1, *, gaps: set[int] | None = None) -> list[ObservedResidue]:
    """Build an observed chain numbered from `start`, omitting `gaps`.

    `gaps` are author numbers that are unresolved — present in the sequence but
    missing from the structure, as with a disordered loop.
    """
    gaps = gaps or set()
    residues = []
    for index, residue in enumerate(sequence):
        number = start + index
        if number in gaps:
            continue
        residues.append(ObservedResidue(slot=ResidueSlot(number=number), residue=residue))
    return residues


SEQUENCE = "MKAILVVLLYTFATANADTLCIGYHANNSTDTVDTVLEKNVTVTHSVNLLEDKHNG"


class TestContiguousRuns:
    def test_a_whole_chain_is_one_run(self) -> None:
        assert len(contiguous_runs(chain("MKAIL"))) == 1

    def test_a_missing_loop_splits_the_chain(self) -> None:
        runs = contiguous_runs(chain("MKAILVV", gaps={3, 4}))
        assert [len(run) for run in runs] == [2, 3]

    def test_insertion_codes_continue_their_run(self) -> None:
        """100, 100A, 100B is contiguous even though the number repeats."""
        observed = [
            ObservedResidue(ResidueSlot(100), "A"),
            ObservedResidue(ResidueSlot(100, "A"), "L"),
            ObservedResidue(ResidueSlot(100, "B"), "V"),
            ObservedResidue(ResidueSlot(101), "K"),
        ]
        assert len(contiguous_runs(observed)) == 1


class TestExactReconciliation:
    def test_identical_sequence_and_structure(self) -> None:
        result = reconcile(SEQUENCE, chain(SEQUENCE))
        assert result.outcome is ReconcileOutcome.RECONCILED
        assert result.method is ReconcileMethod.EXACT
        assert result.mismatches == ()
        assert result.coverage == 1.0
        assert result.identity == 1.0

    def test_structure_covering_only_part_of_the_sequence(self) -> None:
        """A construct that starts partway in must not shift the mapping."""
        fragment = SEQUENCE[20:40]
        result = reconcile(SEQUENCE, chain(fragment))
        assert result.outcome is ReconcileOutcome.RECONCILED
        # Canonical index 20 is the first residue the structure resolves.
        assert result.mapping[19] is None
        assert result.mapping[20] is not None
        assert result.mapping[39] is not None
        assert result.mapping[40] is None

    def test_author_numbering_need_not_start_at_one(self) -> None:
        """Crystallographers number by construct, not by array index."""
        result = reconcile(SEQUENCE, chain(SEQUENCE, start=26))
        assert result.outcome is ReconcileOutcome.RECONCILED
        first = result.mapping[0]
        assert first is not None and first.label == "26"

    def test_unresolved_loop_leaves_a_hole_not_a_shift(self) -> None:
        """The single most dangerous case: a missing loop must not slide every
        downstream residue by the length of the gap."""
        observed = chain(SEQUENCE, gaps={10, 11, 12})
        result = reconcile(SEQUENCE, observed)
        assert result.outcome is ReconcileOutcome.RECONCILED
        assert result.mapping[9] is None  # author 10, unresolved
        assert result.mapping[11] is None  # author 12, unresolved
        last = result.mapping[len(SEQUENCE) - 1]
        assert last is not None and last.number == len(SEQUENCE)
        assert result.covered == len(SEQUENCE) - 3

    def test_repeat_makes_the_match_ambiguous_rather_than_wrong(self) -> None:
        """Two valid placements is a question for the user, not a coin flip."""
        repeated = "AAAAGGGGAAAAGGGG"
        result = reconcile_exact(repeated, chain("GGGG"))
        assert result is not None
        assert result.outcome is ReconcileOutcome.AMBIGUOUS
        assert len(result.candidate_offsets) > 1
        assert result.mapping == ()


class TestFallingBackToAlignment:
    def test_a_point_difference_is_not_forced_into_an_exact_match(self) -> None:
        mutated = SEQUENCE[:30] + ("W" if SEQUENCE[30] != "W" else "C") + SEQUENCE[31:]
        result = reconcile(SEQUENCE, chain(mutated))
        assert result.outcome is ReconcileOutcome.NEEDS_ALIGNMENT
        assert result.method is None
        assert result.mapping == ()

    def test_reconcile_never_aligns_on_its_own(self) -> None:
        """Alignment is an explicit user decision. `reconcile` must only ask."""
        tagged = "HHHHHH" + SEQUENCE
        result = reconcile(SEQUENCE, chain(tagged))
        assert result.outcome is ReconcileOutcome.NEEDS_ALIGNMENT
        assert result.parameters is None


class TestAlignment:
    def test_resolves_a_point_difference_and_reports_it(self) -> None:
        index = 30
        replacement = "W" if SEQUENCE[index] != "W" else "C"
        mutated = SEQUENCE[:index] + replacement + SEQUENCE[index + 1 :]

        result = align(SEQUENCE, chain(mutated))
        assert result.outcome is ReconcileOutcome.RECONCILED
        assert result.method is ReconcileMethod.ALIGNMENT
        assert len(result.mismatches) == 1

        mismatch = result.mismatches[0]
        assert mismatch.canonical_index == index
        assert mismatch.canonical_residue == SEQUENCE[index]
        assert mismatch.observed_residue == replacement
        # Positions are reported 1-based, as a biologist reads them.
        assert mismatch.canonical_position == index + 1

    def test_states_its_parameters(self) -> None:
        """An alignment whose parameters are not stated is not reproducible."""
        result = align(SEQUENCE, chain(SEQUENCE))
        assert result.parameters is not None
        assert set(result.parameters) == {"match", "mismatch", "gap_open", "gap_extend"}
        assert "Needleman-Wunsch" in result.note

    def test_free_end_gaps_do_not_penalise_a_partial_construct(self) -> None:
        fragment = SEQUENCE[15:35]
        result = align(SEQUENCE, chain(fragment))
        assert result.mapping[15] is not None
        assert result.mapping[34] is not None
        assert result.mapping[0] is None
        assert result.mismatches == ()

    def test_an_n_terminal_tag_does_not_shift_the_mapping(self) -> None:
        """The tag has no counterpart in the reference and must consume no
        canonical positions."""
        result = align(SEQUENCE, chain("HHHHHH" + SEQUENCE))
        first = result.mapping[0]
        assert first is not None
        # Canonical residue 1 maps to the 7th residue of the construct, because
        # six histidines precede it.
        assert first.number == 7
        assert result.mismatches == ()


class TestConstructNumbering:
    def test_signal_peptide_offset(self) -> None:
        """P37957 is 212 aa full length; the mature lipase is numbered from 1
        after a 31-residue signal peptide. Getting this backwards is a 31-residue
        error in every mutation code downstream."""
        full_length = "M" * 212
        mature = offset_scheme(full_length, -31)
        assert mature[31].number == 1  # first mature residue
        assert mature[0].number == -30  # inside the signal peptide
        assert mature[211].number == 181  # last residue, mature numbering

    def test_identity_offset_is_one_based(self) -> None:
        scheme = offset_scheme("MKAIL", 0)
        assert [slot.number for slot in scheme] == [1, 2, 3, 4, 5]
