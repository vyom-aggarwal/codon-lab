"""Joining uploaded bench rows to the variants a run ranked.

Specification §5.9. Every test here guards the same class of failure: a
measurement attributed to a variant that did not produce it. That is worse than
an unjoined row, because an unjoined row is visible and a misattributed one
silently corrupts the scorecard the lab is meant to trust.

The offset tests are the interesting half. They pin the rule from
ARCHITECTURE.md §17 — unanimous *and* unique — from both sides: a shift that
explains everything is offered, and a shift that explains most of it is not.
"""

from __future__ import annotations

import pytest

from codonlab.domain.joining import (
    JoinOutcome,
    KnownVariant,
    UploadedRow,
    apply_offset,
    join,
    resolve_manually,
)

SCHEME = "mature"


def variants(*codes: str) -> list[KnownVariant]:
    """Build the run's variant set from canonical codes."""
    out = []
    for code in codes:
        out.append(
            KnownVariant(
                code=code, wild=code[0], label=code[1:-1], mutant=code[-1]
            )
        )
    return out


def rows(*labels: str) -> list[UploadedRow]:
    return [
        UploadedRow(index=index, raw_label=label, value=float(index))
        for index, label in enumerate(labels, start=1)
    ]


# --------------------------------------------------------------------------- #
# Exact joining
# --------------------------------------------------------------------------- #


def test_an_exact_code_joins() -> None:
    result = join(rows("S77A"), variants("S77A", "A10V"), scheme_label=SCHEME)
    assert result.rows[0].outcome is JoinOutcome.JOINED
    assert result.rows[0].code == "S77A"
    assert result.joined_count == 1


def test_the_three_letter_form_joins_to_the_same_variant() -> None:
    """Biologists write `p.Ser77Ala` in papers and `S77A` in spreadsheets. Both
    are the same experiment and must not land on two different rows."""
    result = join(rows("p.Ser77Ala"), variants("S77A"), scheme_label=SCHEME)
    assert result.rows[0].code == "S77A"


def test_whitespace_and_case_do_not_prevent_a_join() -> None:
    result = join(rows("  s77a  "), variants("S77A"), scheme_label=SCHEME)
    assert result.rows[0].outcome is JoinOutcome.JOINED


def test_a_stacked_design_joins_by_its_whole_set_in_any_order() -> None:
    result = join(
        rows("S77A+A10V"), variants("A10V/S77A"), scheme_label=SCHEME
    )
    assert result.rows[0].code == "A10V/S77A"


# --------------------------------------------------------------------------- #
# What must never join
# --------------------------------------------------------------------------- #


def test_a_different_mutant_residue_does_not_join() -> None:
    """The whole reason there is no similarity threshold in this module.
    `S77A` and `S77L` differ by one character and are different experiments."""
    result = join(rows("S77L"), variants("S77A"), scheme_label=SCHEME)
    entry = result.rows[0]
    assert entry.outcome is JoinOutcome.NO_SUCH_VARIANT
    assert entry.code is None
    assert "L" in entry.detail


def test_a_wild_type_mismatch_is_held_back_rather_than_warned_through() -> None:
    """Position and mutant agree, wild-type does not. Joining this with a
    warning would consume the evidence that the file is in another scheme."""
    result = join(rows("T77A"), variants("S77A"), scheme_label=SCHEME)
    entry = result.rows[0]
    assert entry.outcome is JoinOutcome.WILD_TYPE_MISMATCH
    assert entry.code is None
    assert "S" in entry.detail and SCHEME in entry.detail


def test_text_that_is_not_a_mutation_code_is_reported_not_dropped() -> None:
    result = join(rows("empty well"), variants("S77A"), scheme_label=SCHEME)
    assert result.rows[0].outcome is JoinOutcome.UNPARSEABLE
    assert len(result.rows) == 1


def test_a_combination_never_joins_to_one_of_its_components() -> None:
    """A measurement of the double mutant is not a measurement of either single."""
    result = join(rows("A10V/S77A"), variants("A10V", "S77A"), scheme_label=SCHEME)
    entry = result.rows[0]
    assert entry.outcome is JoinOutcome.UNKNOWN_COMBINATION
    assert entry.code is None


def test_every_row_survives_the_join_whatever_happened_to_it() -> None:
    """`Measurement.variant_id` is nullable for exactly this reason."""
    uploaded = rows("S77A", "T77A", "not a code", "A10V/S77A", "Q999W")
    result = join(uploaded, variants("S77A"), scheme_label=SCHEME)
    assert len(result.rows) == len(uploaded)
    assert [entry.row.index for entry in result.rows] == [1, 2, 3, 4, 5]
    assert result.joined_count == 1
    assert result.unjoined_count == 4
    # Nothing unjoined is left without an explanation.
    assert all(entry.detail for entry in result.rows if not entry.joined)


def test_the_raw_label_is_preserved_exactly_as_written() -> None:
    result = join(rows("  p.Ser77Ala "), variants("S77A"), scheme_label=SCHEME)
    assert result.rows[0].row.raw_label == "  p.Ser77Ala "


# --------------------------------------------------------------------------- #
# The offset proposal: unanimous and unique
# --------------------------------------------------------------------------- #


def test_one_shift_explaining_every_unplaced_row_is_proposed() -> None:
    """The real case: a file written in precursor numbering against a project
    whose canonical scheme is the mature protein."""
    known = variants("A1N", "E2K", "H3Y")
    result = join(rows("A32N", "E33K", "H34Y"), known, scheme_label=SCHEME)

    assert result.joined_count == 0
    assert result.proposal is not None
    assert result.proposal.offset == -31
    assert result.proposal.witnesses == 3
    assert {row.code for row in result.proposal.would_join} == {"A1N", "E2K", "H3Y"}


def test_a_shift_that_explains_most_rows_is_not_proposed() -> None:
    """The discriminating test for the unanimity rule. Two rows agree on -31 and
    one does not; a 'fraction of rows' threshold would accept this, and the rule
    that has no threshold rejects it."""
    known = variants("A1N", "E2K", "H3Y")
    result = join(rows("A32N", "E33K", "H99Y"), known, scheme_label=SCHEME)

    assert result.proposal is None
    assert "No single numbering shift" in result.proposal_note


def test_a_single_unplaced_row_proposes_nothing() -> None:
    """One row is not evidence of a systematic shift. The unanimity rule reaches
    that on its own — several offsets explain one row, so uniqueness fails —
    without a minimum-rows constant that could be set wrong."""
    known = variants("A1N", "A5N", "A9N")
    result = join(rows("A40N"), known, scheme_label=SCHEME)
    assert result.proposal is None
    assert "explain the unplaced rows equally well" in result.proposal_note


def test_an_ambiguous_shift_is_refused_and_says_how_many_were_possible() -> None:
    """Mirrors `numbering.reconcile` refusing with nine candidate offsets."""
    known = variants("A1N", "A2N")
    result = join(rows("A10N"), known, scheme_label=SCHEME)
    assert result.proposal is None
    assert "2 different numbering shifts" in result.proposal_note


def test_nothing_is_proposed_when_every_row_joined() -> None:
    result = join(rows("S77A"), variants("S77A"), scheme_label=SCHEME)
    assert result.proposal is None
    assert "no numbering shift was looked for" in result.proposal_note


def test_a_proposal_says_which_rows_it_would_not_fix() -> None:
    """A proposal that overstates what it repairs is a proposal the user cannot
    weigh. `H3W` is explained by the shift but was never ranked by the run."""
    known = variants("A1N", "E2K", "H3Y")
    result = join(rows("A32N", "E33K", "H34W"), known, scheme_label=SCHEME)

    assert result.proposal is not None
    assert result.proposal.offset == -31
    assert {row.code for row in result.proposal.would_join} == {"A1N", "E2K"}
    assert [row.code for row in result.proposal.explained_without_variant] == ["H3W"]


def test_a_proposal_is_never_applied_by_the_join_itself() -> None:
    known = variants("A1N", "E2K", "H3Y")
    result = join(rows("A32N", "E33K", "H34Y"), known, scheme_label=SCHEME)
    assert result.proposal is not None
    assert result.joined_count == 0, "a proposal must not silently join anything"


def test_insertion_coded_rows_cannot_testify_to_a_constant_shift() -> None:
    known = variants("A1N", "E2K")
    result = join(rows("H100AY"), known, scheme_label=SCHEME)
    assert result.proposal is None
    assert "insertion codes" in result.proposal_note


# --------------------------------------------------------------------------- #
# Accepting a shift
# --------------------------------------------------------------------------- #


def test_accepting_a_shift_joins_the_rows_it_explains() -> None:
    known = variants("A1N", "E2K", "H3Y")
    first = join(rows("A32N", "E33K", "H34Y"), known, scheme_label=SCHEME)
    assert first.proposal is not None

    second = apply_offset(first, known, offset=first.proposal.offset, scheme_label=SCHEME)
    assert second.joined_count == 3
    assert [entry.code for entry in second.rows] == ["A1N", "E2K", "H3Y"]


def test_accepting_a_shift_does_not_overwrite_what_the_file_said() -> None:
    """`raw_label` is the user's own notation and is what an unjoined row is
    read back in. The shift changes which variant we test, never the record."""
    known = variants("A1N", "E2K", "H3Y")
    first = join(rows("A32N", "E33K", "H34Y"), known, scheme_label=SCHEME)
    second = apply_offset(first, known, offset=-31, scheme_label=SCHEME)
    assert [entry.row.raw_label for entry in second.rows] == ["A32N", "E33K", "H34Y"]


def test_a_shift_leaves_rows_it_cannot_place_unjoined_with_a_reason() -> None:
    known = variants("A1N", "E2K", "H3Y")
    first = join(rows("A32N", "E33K", "H34W"), known, scheme_label=SCHEME)
    second = apply_offset(first, known, offset=-31, scheme_label=SCHEME)

    assert second.joined_count == 2
    unplaced = [entry for entry in second.rows if not entry.joined]
    assert len(unplaced) == 1
    assert unplaced[0].row.raw_label == "H34W"
    assert unplaced[0].detail


def test_rows_already_joined_are_untouched_by_a_shift() -> None:
    known = variants("A1N", "E2K", "S77A")
    first = join(rows("S77A", "A32N", "E33K"), known, scheme_label=SCHEME)
    assert first.joined_count == 1
    second = apply_offset(first, known, offset=-31, scheme_label=SCHEME)
    assert second.rows[0].code == "S77A"
    assert second.joined_count == 3


def test_applying_a_shift_records_it_in_the_note() -> None:
    known = variants("A1N")
    first = join(rows("A32N"), known, scheme_label=SCHEME)
    second = apply_offset(first, known, offset=-31, scheme_label=SCHEME)
    assert "-31" in second.proposal_note


# --------------------------------------------------------------------------- #
# Manual override
# --------------------------------------------------------------------------- #


def test_a_row_can_be_pointed_at_a_variant_by_hand() -> None:
    known = variants("S77A")
    result = join(rows("weird label"), known, scheme_label=SCHEME)
    resolved = resolve_manually(
        result, row_index=1, code="S77A", known_codes=["S77A"]
    )
    assert resolved.rows[0].outcome is JoinOutcome.JOINED
    assert resolved.rows[0].code == "S77A"
    assert "by hand" in resolved.rows[0].detail


def test_a_manual_override_to_an_unknown_variant_is_refused() -> None:
    """A typo must produce a refusal, not a measurement filed against nothing."""
    result = join(rows("weird label"), variants("S77A"), scheme_label=SCHEME)
    with pytest.raises(ValueError, match="not a variant in this run"):
        resolve_manually(result, row_index=1, code="Q999W", known_codes=["S77A"])


def test_a_joined_row_can_be_unjoined_by_hand() -> None:
    known = variants("S77A")
    result = join(rows("S77A"), known, scheme_label=SCHEME)
    resolved = resolve_manually(result, row_index=1, code=None, known_codes=["S77A"])
    assert resolved.rows[0].outcome is not JoinOutcome.JOINED
    assert resolved.rows[0].code is None


def test_a_manual_override_touches_only_the_row_named() -> None:
    known = variants("S77A", "A10V")
    result = join(rows("S77A", "nonsense"), known, scheme_label=SCHEME)
    resolved = resolve_manually(
        result, row_index=2, code="A10V", known_codes=["S77A", "A10V"]
    )
    assert resolved.rows[0].code == "S77A"
    assert resolved.rows[1].code == "A10V"
