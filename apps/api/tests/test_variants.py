"""Enumeration, and the numbering rule it exists to protect.

The expensive error this application can make is an off-by-one in residue
numbering. A candidate is generated from a sequence index and named with the
canonical scheme's label for that index; these tests assert the two never get
swapped, and that a position the scheme cannot name produces nothing at all
rather than something plausible.
"""

from __future__ import annotations

from codonlab.domain.variants import (
    SUBSTITUTIONS,
    enumerate_single_substitutions,
    hgvs_of,
    is_writable,
    label_of,
    substitutions_at,
)


def sequential(length: int, offset: int = 0) -> list[str | None]:
    return [str(index + 1 + offset) for index in range(length)]


def test_nineteen_substitutions_per_standard_residue() -> None:
    assert len(SUBSTITUTIONS) == 20
    result = enumerate_single_substitutions("ACD", sequential(3))
    assert len(result.candidates) == 3 * 19


def test_the_wild_type_is_never_a_candidate() -> None:
    result = enumerate_single_substitutions("AAA", sequential(3))
    assert all(candidate.wild != candidate.mutant for candidate in result.candidates)
    assert "A1A" not in {candidate.code for candidate in result.candidates}


def test_codes_are_written_in_the_canonical_scheme_not_the_sequence_index() -> None:
    """The whole numbering subsystem, in one assertion.

    On the seeded lipase, sequence index 108 is Ser77 under the confirmed
    mature-protein scheme. A candidate named S108A would point a bench scientist
    at a residue 31 positions from the one it means.
    """
    sequence = "A" * 107 + "S" + "A" * 4
    labels = sequential(len(sequence), offset=-31)

    result = enumerate_single_substitutions(sequence, labels)
    codes = {candidate.code for candidate in result.candidates}

    assert "S77A" in codes
    assert "S108A" not in codes

    serine = next(c for c in result.candidates if c.code == "S77A")
    # The index is kept, because constraints and structures join on it.
    assert serine.sequence_position == 108
    assert serine.label == "77"


def test_a_position_the_scheme_does_not_cover_produces_nothing() -> None:
    """No label means no unambiguous name, so no candidate. Not a fallback to
    the sequence index, which would be a code that means something else."""
    result = enumerate_single_substitutions("ACD", ["1", None, "3"])
    assert len(result.candidates) == 2 * 19
    assert result.uncovered == (2,)
    assert all(candidate.sequence_position != 2 for candidate in result.candidates)


def test_a_non_standard_residue_produces_nothing() -> None:
    result = enumerate_single_substitutions("AXD", sequential(3))
    assert result.non_standard == (2,)
    assert len(result.candidates) == 2 * 19


def test_a_label_no_mutation_code_can_express_produces_nothing() -> None:
    """A mature-protein scheme numbers the signal peptide it excludes at zero
    and below. `A-30C` is not a mutation code in any notation."""
    sequence = "A" * 5
    labels = sequential(5, offset=-3)  # -2, -1, 0, 1, 2
    result = enumerate_single_substitutions(sequence, labels)

    assert result.unwritable == (1, 2, 3)
    assert {candidate.label for candidate in result.candidates} == {"1", "2"}
    assert all(not candidate.code.startswith("A-") for candidate in result.candidates)


def test_insertion_codes_survive_enumeration() -> None:
    """100/100A/100B are three residues that advance the author number once."""
    result = enumerate_single_substitutions("HHH", ["100", "100A", "100B"])
    codes = {candidate.code for candidate in result.candidates}
    assert "H100AY" in codes
    assert label_of("H100AY") == "100A"
    assert hgvs_of("H100AY") == "p.His100ATyr"


def test_writability_is_decided_by_the_mutation_parser() -> None:
    assert is_writable("A", "77", "V") is True
    assert is_writable("A", "0", "V") is False
    assert is_writable("A", "-3", "V") is False


def test_enumeration_is_reproducible() -> None:
    labels = sequential(6)
    first = enumerate_single_substitutions("ACDEFG", labels)
    second = enumerate_single_substitutions("ACDEFG", labels)
    assert [c.code for c in first.candidates] == [c.code for c in second.candidates]


def test_hgvs_renders_both_forms_of_a_code() -> None:
    assert hgvs_of("S77A") == "p.Ser77Ala"
    # A code that cannot be read is returned unchanged, never mangled into
    # something that looks authoritative.
    assert hgvs_of("not a code") == "not a code"
    assert label_of("not a code") == ""


def test_substitutions_at_rejects_a_position_outside_the_sequence() -> None:
    try:
        substitutions_at("ACD", 9, "9")
    except ValueError as error:
        assert "outside" in str(error)
    else:  # pragma: no cover - the call must raise
        raise AssertionError("expected a ValueError")
