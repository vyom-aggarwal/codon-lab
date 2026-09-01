"""Aggregation must expose disagreement rather than average it away.

Specification §6. The two failure modes these tests guard are opposite and both
fatal: combining incomparable scales into a number that sorts but means nothing,
and reporting agreement where there is only one opinion.
"""

from __future__ import annotations

from codonlab.domain.aggregate import Series, aggregate, normalised_ranks, top


def test_best_value_ranks_one_when_higher_is_better() -> None:
    ranks = normalised_ranks(Series({"a": 3.0, "b": 1.0, "c": 2.0}, higher_is_better=True))
    assert ranks == {"a": 1.0, "c": 0.5, "b": 0.0}


def test_best_value_ranks_one_when_lower_is_better() -> None:
    """A ΔΔG reported destabilizing-positive is better when it is lower."""
    ranks = normalised_ranks(Series({"a": 3.0, "b": 1.0, "c": 2.0}, higher_is_better=False))
    assert ranks == {"b": 1.0, "c": 0.5, "a": 0.0}


def test_ties_take_the_mean_of_the_ranks_they_span() -> None:
    """A predictor returning the same value twice must not manufacture an order
    between them out of dictionary iteration."""
    ranks = normalised_ranks(Series({"a": 1.0, "b": 1.0, "c": 0.0}, higher_is_better=True))
    assert ranks["a"] == ranks["b"]
    assert ranks["c"] < ranks["a"]


def test_every_value_tied_comes_out_flat() -> None:
    ranks = normalised_ranks(Series({"a": 1.0, "b": 1.0, "c": 1.0}, higher_is_better=True))
    assert set(ranks.values()) == {0.5}


def test_a_single_variant_ranks_one() -> None:
    assert normalised_ranks(Series({"a": 7.0}, higher_is_better=True)) == {"a": 1.0}


def test_an_empty_series_produces_nothing() -> None:
    assert normalised_ranks(Series({}, higher_is_better=True)) == {}


def test_scales_are_never_mixed() -> None:
    """A kcal/mol value and a log-likelihood ratio are combined as ranks. The
    consensus is therefore in [0, 1] no matter how large either raw value is."""
    result = aggregate(
        {
            "stability": Series({"x": -0.5, "y": 4000.0}, higher_is_better=False),
            "fitness": Series({"x": 2.0, "y": -9.0}, higher_is_better=True),
        }
    )
    by_code = {row.code: row for row in result}
    assert by_code["x"].consensus == 1.0
    assert by_code["y"].consensus == 0.0


def test_disagreement_is_reported_not_folded_into_the_consensus() -> None:
    """Two predictors that rank a variant oppositely produce a middling
    consensus — and a disagreement of 1, which is the useful part."""
    result = aggregate(
        {
            "one": Series({"x": 1.0, "y": 0.0}, higher_is_better=True),
            "two": Series({"x": 0.0, "y": 1.0}, higher_is_better=True),
        }
    )
    row = next(item for item in result if item.code == "x")
    assert row.consensus == 0.5
    assert row.disagreement == 1.0


def test_one_opinion_is_null_disagreement_not_zero() -> None:
    """Zero would read as unanimity. There is nothing to disagree about."""
    result = aggregate({"only": Series({"x": 1.0, "y": 2.0}, higher_is_better=True)})
    assert all(row.disagreement is None for row in result)
    assert all(row.sources_scored == 1 for row in result)


def test_a_partially_scored_variant_is_kept_and_counted() -> None:
    """Not imputed to the mean, not dropped. The count of opinions travels with
    the number so one is never mistaken for three."""
    result = aggregate(
        {
            "one": Series({"x": 1.0, "y": 0.0}, higher_is_better=True),
            "two": Series({"x": 1.0}, higher_is_better=True),
        }
    )
    by_code = {row.code: row for row in result}
    assert by_code["y"].sources_scored == 1
    assert by_code["y"].disagreement is None
    assert by_code["x"].sources_scored == 2


def test_ordering_is_deterministic() -> None:
    """An identical run must produce an identical order, not one that depends on
    set iteration — otherwise a diff between two runs invents movement."""
    sources = {
        "one": Series({"a": 1.0, "b": 1.0, "c": 0.0}, higher_is_better=True),
        "two": Series({"a": 1.0, "b": 1.0, "c": 0.0}, higher_is_better=True),
    }
    assert [row.code for row in aggregate(sources)] == [row.code for row in aggregate(sources)]
    # Ties break on the code, so the order is stable across processes too.
    assert [row.code for row in aggregate(sources)][:2] == ["a", "b"]


def test_an_absent_budget_truncates_nothing() -> None:
    result = aggregate({"one": Series({"a": 1.0, "b": 2.0, "c": 3.0}, higher_is_better=True)})
    assert len(top(result, None)) == 3
    assert len(top(result, 2)) == 2
    assert len(top(result, 99)) == 3
