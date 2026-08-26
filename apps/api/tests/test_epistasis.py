"""Stacking mutations, and the three things that must not be overstated.

Specification §5.7. The failure modes these tests guard are all the same shape —
a number or a flag that looks like a measurement and is not:

- an unmeasured pair rendered as though it were measured and far apart,
- a partial sum presented as a total,
- a stacked design shown without the additivity assumption attached.
"""

from __future__ import annotations

import pytest

from catalyst.domain.epistasis import (
    ADDITIVITY_ASSUMPTION,
    PAIR_PROXIMITY_ANGSTROM,
    Proximity,
    StackError,
    additive,
    enumerate_stacks,
    pair_flags,
    stack,
    warning_for,
)

POSITIONS = {"A10V": 10, "L45M": 45, "S77A": 77, "T109N": 109}


# --------------------------------------------------------------------------- #
# Building a stack
# --------------------------------------------------------------------------- #


def test_a_stack_orders_its_mutations_by_position() -> None:
    """The same set of mutations must always produce the same code, or it would
    produce two variant rows for one construct and split its measured values."""
    first = stack(["S77A", "A10V"], POSITIONS)
    second = stack(["A10V", "S77A"], POSITIONS)
    assert first.code == second.code == "A10V/S77A"
    assert first.positions == (10, 77)


def test_two_mutations_at_one_position_are_refused() -> None:
    """No single construct can carry both, so accepting it would produce a design
    nobody can build."""
    with pytest.raises(StackError, match="appears twice"):
        stack(["A10V", "A10G"], {"A10V": 10, "A10G": 10})


def test_a_stack_of_one_is_refused() -> None:
    with pytest.raises(StackError):
        stack(["A10V"], POSITIONS)


def test_a_mutation_with_no_known_position_is_refused_not_guessed() -> None:
    with pytest.raises(StackError, match="No sequence position"):
        stack(["A10V", "Q999R"], POSITIONS)


def test_enumeration_produces_every_combination_of_the_requested_size() -> None:
    designs, notes = enumerate_stacks(list(POSITIONS), POSITIONS, size=2, limit=100)
    assert len(designs) == 6  # C(4, 2)
    assert notes == ()


def test_enumeration_says_when_it_stopped_at_the_cap() -> None:
    """A truncated enumeration that does not say so is a design set that looks
    complete and is not."""
    designs, notes = enumerate_stacks(list(POSITIONS), POSITIONS, size=2, limit=2)
    assert len(designs) == 2
    assert any("cap" in note for note in notes)


def test_enumeration_counts_combinations_that_share_a_position() -> None:
    positions = {"A10V": 10, "A10G": 10, "L45M": 45}
    designs, notes = enumerate_stacks(list(positions), positions, size=2, limit=100)
    assert {design.code for design in designs} == {"A10V/L45M", "A10G/L45M"}
    assert any("same position" in note for note in notes)


def test_choosing_more_than_were_offered_is_refused() -> None:
    with pytest.raises(StackError):
        enumerate_stacks(["A10V", "L45M"], POSITIONS, size=3, limit=10)


# --------------------------------------------------------------------------- #
# The 8A pair flag
# --------------------------------------------------------------------------- #


def test_a_pair_inside_the_cutoff_is_flagged() -> None:
    design = stack(["A10V", "L45M"], POSITIONS)
    flags = pair_flags(design, {(10, 45): 4.2}, unknown_reason="unused")
    assert flags[0].proximity is Proximity.WITHIN
    assert flags[0].is_flagged
    assert flags[0].separation_angstrom == 4.2
    assert flags[0].reason is None


def test_a_pair_outside_the_cutoff_is_not_flagged() -> None:
    design = stack(["A10V", "L45M"], POSITIONS)
    flags = pair_flags(design, {(10, 45): 12.0}, unknown_reason="unused")
    assert flags[0].proximity is Proximity.BEYOND
    assert not flags[0].is_flagged


def test_exactly_at_the_cutoff_counts_as_within() -> None:
    """`BRIEF.md` §5.7 says "within 8A". The boundary is pinned here so nobody
    has to re-derive whether the comparison is strict."""
    design = stack(["A10V", "L45M"], POSITIONS)
    flags = pair_flags(
        design, {(10, 45): PAIR_PROXIMITY_ANGSTROM}, unknown_reason="unused"
    )
    assert flags[0].proximity is Proximity.WITHIN


def test_an_unmeasured_pair_is_unknown_and_never_beyond() -> None:
    """The whole reason `Proximity` has three values.

    A pair absent from the separation map has not been measured. Reporting it as
    BEYOND would tell a bench scientist these two mutations cannot interact, on
    the basis of no evidence at all.
    """
    design = stack(["A10V", "L45M"], POSITIONS)
    flags = pair_flags(design, {}, unknown_reason="No structure is attached.")
    assert flags[0].proximity is Proximity.UNKNOWN
    assert flags[0].separation_angstrom is None
    assert flags[0].reason == "No structure is attached."


def test_an_unknown_pair_is_not_a_flagged_pair() -> None:
    """`is_flagged` must mean "measured and close", not "not known to be far"."""
    design = stack(["A10V", "L45M"], POSITIONS)
    flags = pair_flags(design, {}, unknown_reason="No structure is attached.")
    assert not flags[0].is_flagged


def test_separations_are_found_whichever_way_round_the_pair_is_given() -> None:
    design = stack(["L45M", "A10V"], POSITIONS)
    flags = pair_flags(design, {(10, 45): 3.0}, unknown_reason="unused")
    assert flags[0].proximity is Proximity.WITHIN


def test_a_triple_produces_all_three_pairs() -> None:
    design = stack(["A10V", "L45M", "S77A"], POSITIONS)
    flags = pair_flags(
        design, {(10, 45): 5.0, (10, 77): 30.0}, unknown_reason="not resolved"
    )
    assert len(flags) == 3
    states = {(flag.a_code, flag.b_code): flag.proximity for flag in flags}
    assert states[("A10V", "L45M")] is Proximity.WITHIN
    assert states[("A10V", "S77A")] is Proximity.BEYOND
    assert states[("L45M", "S77A")] is Proximity.UNKNOWN


# --------------------------------------------------------------------------- #
# Additive totals
# --------------------------------------------------------------------------- #


def test_an_additive_total_is_the_sum_of_its_components() -> None:
    estimate = additive(
        metric="ddg_kcal_per_mol",
        label="Predicted ΔΔG",
        unit="kcal/mol",
        sign_convention="destabilizing positive",
        codes=("A10V", "L45M"),
        values={"A10V": -0.5, "L45M": -1.25},
    )
    assert estimate.total == -1.75
    assert estimate.missing == ()


def test_a_missing_component_makes_the_total_unavailable() -> None:
    """Not a partial sum. Adding the components that exist and calling it the
    total understates the design by exactly the contribution nobody measured,
    and it does so with the authority of a number."""
    estimate = additive(
        metric="ddg_kcal_per_mol",
        label="Predicted ΔΔG",
        unit="kcal/mol",
        sign_convention="destabilizing positive",
        codes=("A10V", "L45M"),
        values={"A10V": -0.5},
    )
    assert estimate.total is None
    assert estimate.missing == ("L45M",)
    # What is known is still returned, so the interface can show it without
    # implying a total.
    assert estimate.contributions == (("A10V", -0.5),)


def test_the_additivity_assumption_travels_with_every_total() -> None:
    """Specification §5.7 calls the warning unmissable. Making it a required
    field is how this layer enforces that rather than trusting a component."""
    estimate = additive(
        metric="ddg_kcal_per_mol",
        label="Predicted ΔΔG",
        unit="kcal/mol",
        sign_convention="destabilizing positive",
        codes=("A10V",),
        values={"A10V": -0.5},
    )
    assert estimate.assumption == ADDITIVITY_ASSUMPTION
    assert "epistasis" in estimate.assumption
    assert "not a prediction" in estimate.assumption


def test_a_stacked_total_carries_no_interval_and_says_why() -> None:
    """Specification §7 wants an interval on a ΔΔG. A stacked design has none,
    and a blank could be read as zero uncertainty."""
    estimate = additive(
        metric="ddg_kcal_per_mol",
        label="Predicted ΔΔG",
        unit="kcal/mol",
        sign_convention="destabilizing positive",
        codes=("A10V",),
        values={"A10V": -0.5},
    )
    assert "No interval" in estimate.interval_note


def test_the_sign_convention_travels_with_the_total() -> None:
    estimate = additive(
        metric="ddg_kcal_per_mol",
        label="Predicted ΔΔG",
        unit="kcal/mol",
        sign_convention="destabilizing positive",
        codes=("A10V",),
        values={"A10V": 1.0},
    )
    assert estimate.sign_convention == "destabilizing positive"
    assert estimate.unit == "kcal/mol"


# --------------------------------------------------------------------------- #
# The warning
# --------------------------------------------------------------------------- #


def test_a_set_with_no_stacked_designs_raises_no_warning() -> None:
    warning = warning_for([], [])
    assert warning["stacked_designs"] == 0


def test_the_warning_counts_unknown_pairs_separately_from_flagged_ones() -> None:
    """A screen that reads only `pairs_within_cutoff` would report "no pairs are
    close" for a target with no structure. The unknown count exists so it cannot."""
    design = stack(["A10V", "L45M", "S77A"], POSITIONS)
    flags = pair_flags(design, {(10, 45): 5.0}, unknown_reason="not resolved")
    warning = warning_for([design], flags)
    assert warning["stacked_designs"] == 1
    assert warning["pairs_total"] == 3
    assert warning["pairs_within_cutoff"] == 1
    assert warning["pairs_unknown"] == 2


def test_the_warning_states_the_cutoff_and_how_it_was_measured() -> None:
    warning = warning_for([], [])
    assert warning["cutoff_angstrom"] == 8.0
    assert "non-hydrogen" in warning["distance_convention"]
    assert "CA-CA" in warning["distance_convention"]
