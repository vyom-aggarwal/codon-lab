"""Does the viewer focus the residue the mutation code names?

Testable without rendering anything, which is the point: a viewer that draws a
structure beautifully and focuses the wrong residue is the worst failure this
application has, and it is invisible to a visual check — the picture looks fine.

Every case below is built from a real scheme shape:

* the seeded lipase, where the canonical scheme is the mature protein and the
  structure is numbered full-length, so the offset is a genuine -31;
* firefly luciferase, where the canonical scheme *is* the author scheme and the
  offset is zero, which proves the resolution does not always shift;
* the Ambler convention for TEM-1, which skips 239 and 253;
* a crystal structure with an unresolved loop, where the honest answer is "not
  covered" rather than the nearest residue.
"""

from __future__ import annotations

import pytest

from codonlab.domain.schemes import (
    FocusResolution,
    SchemeResolutionError,
    author_label_at,
    positions_by_label,
    resolve_focus,
)

# --------------------------------------------------------------------------- #
# Real scheme shapes
# --------------------------------------------------------------------------- #

#: B. subtilis lipase A (UniProt P37957): 212 residues, 31-residue signal
#: peptide. The mature scheme runs -30..181; AlphaFold numbers 1..212.
LIPASE_LENGTH = 212
LIPASE_SIGNAL = 31
LIPASE_MATURE: list[str | None] = [
    str(index + 1 - LIPASE_SIGNAL) for index in range(LIPASE_LENGTH)
]
LIPASE_AUTHOR: list[str | None] = [str(index + 1) for index in range(LIPASE_LENGTH)]

#: Firefly luciferase (P08659): the confirmed canonical scheme is the AlphaFold
#: author numbering itself, so canonical and author coincide.
LUCIFERASE_LENGTH = 550
LUCIFERASE_LABELS: list[str | None] = [str(index + 1) for index in range(LUCIFERASE_LENGTH)]


def test_the_lipase_case_the_whole_subsystem_exists_for() -> None:
    """S77A names the catalytic serine. The structure calls it 108.

    UniProt annotates the nucleophile at 108, the confirmed mature scheme calls
    it Ser77, and the AlphaFold model numbers it 108. A viewer handed 77 would
    focus a residue 31 positions away — a different part of the fold — and it
    would look perfectly fine.
    """
    resolved = resolve_focus("S77A", LIPASE_MATURE, LIPASE_AUTHOR)

    assert resolved.canonical_label == "77"
    assert resolved.sequence_position == 108
    assert resolved.author_label == "108"
    assert resolved.is_focusable


def test_the_offset_is_the_signal_peptide_and_is_not_hard_coded() -> None:
    """Every residue shifts by the same 31 here, but by lookup, not arithmetic."""
    for canonical, expected_author in (("1", "32"), ("77", "108"), ("181", "212")):
        resolved = resolve_focus(f"A{canonical}V", LIPASE_MATURE, LIPASE_AUTHOR)
        assert resolved.author_label == expected_author


def test_a_zero_offset_target_is_not_shifted() -> None:
    """The resolution must not assume there is always an offset to apply.

    On luciferase the canonical scheme is the author scheme, and I40S focuses 40.
    A resolver that had learned "subtract the signal peptide" from the lipase
    would be wrong here, and wrong quietly.
    """
    resolved = resolve_focus("I40S", LUCIFERASE_LABELS, LUCIFERASE_LABELS)
    assert resolved.sequence_position == 40
    assert resolved.author_label == "40"


def test_signal_peptide_residues_still_map_without_shifting() -> None:
    """Mature numbering labels the signal peptide zero and below.

    `enumerate_single_substitutions` refuses to write a mutation code for those,
    so they never reach the viewer — but the scheme still maps them, and the
    mapping must not silently slide.
    """
    assert LIPASE_MATURE[0] == "-30"
    assert author_label_at(LIPASE_AUTHOR, 1) == "1"
    assert positions_by_label(LIPASE_MATURE)["-30"] == 1


# --------------------------------------------------------------------------- #
# Schemes that are not a constant offset
# --------------------------------------------------------------------------- #


def test_ambler_numbering_skips_residues_by_convention() -> None:
    """TEM-1 skips 239 and 253. A scheme stored as an offset could not say that."""
    canonical: list[str | None] = []
    number = 26
    for _ in range(263):
        while number in (239, 253):
            number += 1
        canonical.append(str(number))
        number += 1
    author: list[str | None] = [str(index + 1) for index in range(263)]

    assert "239" not in canonical
    assert "253" not in canonical
    before = resolve_focus("E238K", canonical, author)
    after = resolve_focus("G240S", canonical, author)
    # Consecutive residues in the structure, two apart in Ambler numbering.
    assert after.sequence_position - before.sequence_position == 1


def test_an_unresolved_loop_is_not_covered_rather_than_approximated() -> None:
    """A crystal structure missing a loop has no atoms there to focus on."""
    canonical: list[str | None] = [str(index + 1) for index in range(10)]
    author: list[str | None] = [str(index + 1) for index in range(10)]
    author[4] = None  # residue 5 unresolved

    resolved = resolve_focus("A5V", canonical, author)
    assert resolved.sequence_position == 5
    assert resolved.author_label is None
    assert resolved.is_focusable is False
    assert resolved.unavailable is not None
    assert "does not cover" in resolved.unavailable


def test_insertion_codes_survive_the_resolution() -> None:
    """100/100A/100B are three residues that advance the author number once."""
    canonical: list[str | None] = ["100", "100A", "100B"]
    author: list[str | None] = ["100", "100A", "100B"]

    resolved = resolve_focus("H100AY", canonical, author)
    assert resolved.canonical_label == "100A"
    assert resolved.sequence_position == 2
    assert resolved.author_label == "100A"


# --------------------------------------------------------------------------- #
# Refusals
# --------------------------------------------------------------------------- #


def test_a_scheme_that_names_two_residues_alike_is_refused() -> None:
    """The latent bug this module was extracted to fix.

    A plain dict comprehension keeps the last duplicate and resolves happily to a
    residue the user did not name. Refusing is the only safe answer.
    """
    with pytest.raises(SchemeResolutionError) as error:
        positions_by_label(["1", "2", "2", "3"])

    assert "more than one residue" in str(error.value)
    assert "2" in str(error.value)
    assert error.value.remedy


def test_a_label_the_canonical_scheme_does_not_have_is_refused() -> None:
    with pytest.raises(SchemeResolutionError) as error:
        resolve_focus("A999V", LIPASE_MATURE, LIPASE_AUTHOR)
    assert "no residue labelled 999" in str(error.value)


def test_something_that_is_not_a_mutation_code_names_no_residue() -> None:
    with pytest.raises(SchemeResolutionError):
        resolve_focus("not a code", LIPASE_MATURE, LIPASE_AUTHOR)


@pytest.mark.parametrize("position", [0, -1, LIPASE_LENGTH + 1])
def test_a_position_outside_the_sequence_has_no_label(position: int) -> None:
    assert author_label_at(LIPASE_AUTHOR, position) is None


def test_resolution_is_a_value_not_a_side_effect() -> None:
    """Pure: same arguments, same answer, nothing mutated."""
    first = resolve_focus("S77A", LIPASE_MATURE, LIPASE_AUTHOR)
    second = resolve_focus("S77A", LIPASE_MATURE, LIPASE_AUTHOR)
    assert first == second
    assert isinstance(first, FocusResolution)
    assert LIPASE_MATURE[107] == "77"


# --------------------------------------------------------------------------- #
# The production path uses this, rather than a copy of it
# --------------------------------------------------------------------------- #


def test_the_feature_calculation_refuses_a_duplicated_scheme() -> None:
    """`features.compute` resolves through `positions_by_label`, so a scheme that
    names two residues alike stops the run instead of mislabelling a column."""
    from pathlib import Path

    from codonlab.features.structure import StructureFeatureError, compute

    fixture = Path(__file__).parent / "fixtures" / "1crn.pdb"
    labels: list[str | None] = ["1"] * 46  # every residue labelled the same

    with pytest.raises(StructureFeatureError) as error:
        compute(
            structure_text=fixture.read_text(),
            chain_id="A",
            sequence="X" * 46,
            author_labels=labels,
        )
    assert "more than one residue" in str(error.value)
