"""Predicted against measured, and the statistics that may not stand alone.

Specification §5.9, ARCHITECTURE.md §13. The headline test in this file is
`test_a_constant_offset_is_invisible_to_rank_and_caught_by_bias`: it builds the
exact predictor §13 describes — perfectly ordered, two units high — and asserts
that the rank statistics call it flawless while the bias term catches it. That
is the whole argument for the scorecard's shape, written as an executable claim
rather than a paragraph.

The rest guard the two gates on absolute error: units must match, and sign
conventions must match. Both return a stated reason rather than a number.
"""

from __future__ import annotations

import pytest

from codonlab.domain.scorecard import (
    Convention,
    Paired,
    build,
    calibration,
    commensurable,
    error_terms,
    precision_at_k,
    spearman,
)

DDG = Convention(metric="ddg_kcal_mol", unit="kcal/mol", higher_is_better=False)
MEASURED_DDG = Convention(metric="ddg_kcal_mol", unit="kcal/mol", higher_is_better=False)
T50 = Convention(metric="t50_celsius", unit="°C", higher_is_better=True)
LLR = Convention(metric="esm_llr", unit="log-odds", higher_is_better=True)


def paired(*values: tuple[str, float, float]) -> list[Paired]:
    return [Paired(code=code, predicted=p, measured=m) for code, p, m in values]


# --------------------------------------------------------------------------- #
# The claim ARCHITECTURE.md §13 rests on
# --------------------------------------------------------------------------- #


def test_a_constant_offset_is_invisible_to_rank_and_caught_by_bias() -> None:
    """§13's worked example, as a test.

    A predictor that is perfectly ordered but reads 2 kcal/mol high scores a
    flawless rank correlation and a flawless precision@k. Only the bias term
    reports the 2 kcal/mol. This is why a rank statistic alone is a defect.
    """
    pairs = paired(
        ("A1V", 2.5, 0.5),
        ("A2V", 3.0, 1.0),
        ("A3V", 3.5, 1.5),
        ("A4V", 4.0, 2.0),
        ("A5V", 4.5, 2.5),
    )
    card = build(model_id="offset", pairs=pairs, predicted=DDG, measured=MEASURED_DDG, k=3)

    assert card.spearman == pytest.approx(1.0)
    assert card.precision is not None
    assert card.precision.value == pytest.approx(1.0)

    assert card.error is not None
    assert card.error.mean_signed_error == pytest.approx(2.0)
    assert card.error.mae == pytest.approx(2.0)
    assert card.error.unit == "kcal/mol"


def test_a_scorecard_always_carries_the_error_family_or_the_reason_it_cannot() -> None:
    """There is no way to obtain a rank figure from `build` without also
    obtaining either the error terms or the sentence explaining their absence."""
    comparable = build(
        model_id="m", pairs=paired(("A1V", 1.0, 1.0), ("A2V", 2.0, 2.0)),
        predicted=DDG, measured=MEASURED_DDG, k=1,
    )
    assert comparable.error is not None
    assert comparable.rank_only is False

    incomparable = build(
        model_id="m", pairs=paired(("A1V", 1.0, 48.0), ("A2V", 2.0, 47.0)),
        predicted=DDG, measured=T50, k=1,
    )
    assert incomparable.error is None
    assert incomparable.rank_only is True
    assert incomparable.commensurability.reason


# --------------------------------------------------------------------------- #
# Gate one: units
# --------------------------------------------------------------------------- #


def test_a_ddg_and_a_temperature_are_not_commensurable() -> None:
    """Specification §7: never claim a Tm shift in °C from a ddG prediction."""
    verdict = commensurable(DDG, T50)
    assert verdict.comparable is False
    assert "kcal/mol" in verdict.reason and "°C" in verdict.reason
    assert "No conversion is applied" in verdict.reason


def test_units_alone_block_the_comparison_even_when_directions_agree() -> None:
    """Isolates the unit gate.

    `DDG` and `T50` differ in unit *and* in direction, so a test using that pair
    passes even if the unit check is deleted — found by mutating the check away
    and watching the wrong assertion fail. An ESM log-odds ratio and a T50 are
    both higher-is-better and still cannot be subtracted, which pins the unit
    gate on its own.
    """
    verdict = commensurable(LLR, T50)
    assert LLR.higher_is_better == T50.higher_is_better
    assert verdict.comparable is False
    assert "log-odds" in verdict.reason and "°C" in verdict.reason
    assert error_terms(paired(("A1V", 1.0, 48.0)), LLR, T50) is None


def test_no_error_term_is_produced_across_units() -> None:
    pairs = paired(("A1V", 1.0, 48.0), ("A2V", 2.0, 47.0))
    assert error_terms(pairs, DDG, T50) is None
    assert calibration(pairs, DDG, T50) == ()


def test_rank_statistics_survive_a_unit_mismatch() -> None:
    """A rank needs an order, not a unit. Blocking the rank figure too would
    throw away the one thing that is legitimately computable here."""
    pairs = paired(("A1V", 1.0, 46.0), ("A2V", 2.0, 47.0), ("A3V", 3.0, 48.0))
    card = build(model_id="m", pairs=pairs, predicted=DDG, measured=T50, k=2)
    assert card.spearman is not None
    assert card.precision is not None
    assert card.error is None


# --------------------------------------------------------------------------- #
# Gate two: sign conventions
# --------------------------------------------------------------------------- #


def test_opposed_sign_conventions_block_the_error_term() -> None:
    """Same unit, opposite meaning. Subtracting these would produce a large
    error that is an artefact of notation."""
    flipped = Convention(metric="ddg_kcal_mol", unit="kcal/mol", higher_is_better=True)
    verdict = commensurable(DDG, flipped)
    assert verdict.comparable is False
    assert "lower is better" in verdict.reason
    assert "higher is better" in verdict.reason


def test_the_product_refuses_to_negate_a_series_on_the_users_behalf() -> None:
    flipped = Convention(metric="ddg_kcal_mol", unit="kcal/mol", higher_is_better=True)
    reason = commensurable(DDG, flipped).reason
    assert "does not make on your behalf" in reason
    assert error_terms(paired(("A1V", 1.0, -1.0)), DDG, flipped) is None


# --------------------------------------------------------------------------- #
# Spearman
# --------------------------------------------------------------------------- #


def test_spearman_is_oriented_so_that_positive_means_agreement() -> None:
    """A ddG reported destabilizing-positive and a T50 reported higher-is-better
    both rank the better variant first, so a predictor that is right scores +1
    without the reader reconciling two conventions in their head."""
    pairs = paired(("A1V", -1.0, 50.0), ("A2V", 0.0, 48.0), ("A3V", 1.0, 46.0))
    assert spearman(pairs, DDG, T50) == pytest.approx(1.0)


def test_a_systematically_inverted_predictor_scores_minus_one() -> None:
    pairs = paired(("A1V", -1.0, 46.0), ("A2V", 0.0, 48.0), ("A3V", 1.0, 50.0))
    assert spearman(pairs, DDG, T50) == pytest.approx(-1.0)


def test_spearman_is_undefined_rather_than_zero_on_one_pair() -> None:
    """Returning 0.0 would be a fabricated number where none exists."""
    assert spearman(paired(("A1V", 1.0, 1.0)), DDG, MEASURED_DDG) is None


def test_spearman_is_undefined_when_a_series_has_no_variation() -> None:
    pairs = paired(("A1V", 1.0, 5.0), ("A2V", 1.0, 6.0), ("A3V", 1.0, 7.0))
    assert spearman(pairs, DDG, MEASURED_DDG) is None


def test_ties_are_averaged_rather_than_ordered_arbitrarily() -> None:
    """A predictor returning the same value twice must not be credited with an
    ordering it did not express."""
    pairs = paired(("A1V", 1.0, 10.0), ("A2V", 1.0, 20.0), ("A3V", 2.0, 30.0))
    first = spearman(pairs, LLR, T50)
    reordered = spearman(list(reversed(pairs)), LLR, T50)
    assert first is not None
    assert first == pytest.approx(reordered)


# --------------------------------------------------------------------------- #
# precision@k
# --------------------------------------------------------------------------- #


def test_precision_at_k_counts_agreement_in_the_top_k() -> None:
    pairs = paired(
        ("A1V", -3.0, 55.0),
        ("A2V", -2.0, 54.0),
        ("A3V", 1.0, 47.0),
        ("A4V", 2.0, 46.0),
    )
    result = precision_at_k(pairs, DDG, T50, k=2)
    assert result is not None
    assert result.value == pytest.approx(1.0)
    assert set(result.hits) == {"A1V", "A2V"}


def test_precision_at_k_is_refused_when_there_are_fewer_than_k_pairs() -> None:
    """precision@10 over six measurements would divide by a k that does not
    exist. The honest answer is that the question cannot be asked yet."""
    pairs = paired(("A1V", 1.0, 1.0), ("A2V", 2.0, 2.0))
    assert precision_at_k(pairs, DDG, MEASURED_DDG, k=10) is None


def test_precision_at_k_is_deterministic_when_values_tie_at_the_boundary() -> None:
    pairs = paired(
        ("A1V", 1.0, 10.0), ("A2V", 1.0, 20.0), ("A3V", 1.0, 30.0), ("A4V", 5.0, 40.0)
    )
    first = precision_at_k(pairs, LLR, T50, k=2)
    second = precision_at_k(list(reversed(pairs)), LLR, T50, k=2)
    assert first is not None and second is not None
    assert first.hits == second.hits


# --------------------------------------------------------------------------- #
# Error and bias
# --------------------------------------------------------------------------- #


def test_mae_and_bias_differ_when_errors_point_both_ways() -> None:
    """A predictor scattered either side of the truth has a real MAE and almost
    no bias. Reporting only one of them would describe a different predictor."""
    pairs = paired(("A1V", 1.0, 0.0), ("A2V", 0.0, 1.0))
    terms = error_terms(pairs, DDG, MEASURED_DDG)
    assert terms is not None
    assert terms.mae == pytest.approx(1.0)
    assert terms.mean_signed_error == pytest.approx(0.0)


def test_the_bias_sign_convention_is_stated_not_assumed() -> None:
    terms = error_terms(paired(("A1V", 3.0, 1.0)), DDG, MEASURED_DDG)
    assert terms is not None
    assert "Predicted minus measured" in terms.sign_note
    assert "reads high" in terms.sign_note
    assert terms.mean_signed_error > 0


# --------------------------------------------------------------------------- #
# Calibration
# --------------------------------------------------------------------------- #


def test_a_calibrated_predictor_sits_on_the_identity_line() -> None:
    pairs = paired(*[(f"A{i}V", float(i), float(i)) for i in range(1, 21)])
    bins = calibration(pairs, DDG, MEASURED_DDG, bins=4)
    assert len(bins) == 4
    for entry in bins:
        assert entry.predicted == pytest.approx(entry.measured)


def test_an_offset_predictor_sits_on_a_parallel_line() -> None:
    """The failure a rank statistic cannot see, drawn."""
    pairs = paired(*[(f"A{i}V", float(i) + 2.0, float(i)) for i in range(1, 21)])
    bins = calibration(pairs, DDG, MEASURED_DDG, bins=4)
    for entry in bins:
        assert entry.predicted - entry.measured == pytest.approx(2.0)


def test_calibration_bins_carry_their_own_count() -> None:
    """So a bin resting on two points can be discounted by eye."""
    pairs = paired(*[(f"A{i}V", float(i), float(i)) for i in range(1, 9)])
    bins = calibration(pairs, DDG, MEASURED_DDG, bins=4)
    assert [entry.count for entry in bins] == [2, 2, 2, 2]
    assert sum(entry.count for entry in bins) == 8


def test_the_bin_count_falls_rather_than_producing_single_point_bins() -> None:
    pairs = paired(*[(f"A{i}V", float(i), float(i)) for i in range(1, 5)])
    bins = calibration(pairs, DDG, MEASURED_DDG, bins=10)
    assert len(bins) == 2
    assert all(entry.count >= 2 for entry in bins)


# --------------------------------------------------------------------------- #
# The card as a whole
# --------------------------------------------------------------------------- #


def test_a_card_reports_how_much_of_each_side_it_rests_on() -> None:
    card = build(
        model_id="m",
        pairs=paired(("A1V", 1.0, 1.0), ("A2V", 2.0, 2.0)),
        predicted=DDG,
        measured=MEASURED_DDG,
        k=1,
        predicted_without_measurement=4000,
        measured_without_prediction=17,
    )
    assert card.n == 2
    assert card.predicted_without_measurement == 4000
    assert card.measured_without_prediction == 17


def test_a_card_built_on_synthetic_predictions_says_so() -> None:
    card = build(
        model_id="mock_stability",
        pairs=paired(("A1V", 1.0, 1.0)),
        predicted=DDG,
        measured=MEASURED_DDG,
        k=1,
        is_mock=True,
    )
    assert card.is_mock is True


def test_accumulating_by_averaging_finished_cards_is_refused() -> None:
    """Averaging two Spearman coefficients is not a Spearman coefficient, and a
    card resting on 6 points must not weigh as much as one resting on 2,000."""
    from codonlab.domain.scorecard import accumulate

    with pytest.raises(NotImplementedError, match="pooling"):
        accumulate({})
