"""A cost estimate the lab can act on, or none at all.

Specification §5.7 asks for a running budget and a cost estimate. The failure
mode guarded here is a plausible-looking total assembled from prices nobody
stated — attached to exactly the ordering decision `BRIEF.md` §1 describes.
"""

from __future__ import annotations

import pytest

from catalyst.domain.costing import (
    CostBasis,
    CostError,
    estimate_fragments,
    estimate_oligos,
    total_of,
)

PRICED = CostBasis(
    currency="USD",
    oligo_per_base=0.15,
    oligo_per_order=2.00,
    fragment_per_bp=0.07,
    fragment_per_order=5.00,
)
UNPRICED = CostBasis()


def test_an_unset_price_list_prices_nothing() -> None:
    assert not UNPRICED.priced
    assert not UNPRICED.can_price_oligos()
    assert not UNPRICED.can_price_fragments()


def test_prices_need_a_currency() -> None:
    """A bare number is not a price. Two labs reading 0.15 as pence and as
    dollars would order the same plate for different money."""
    with pytest.raises(CostError, match="currency"):
        CostBasis(oligo_per_base=0.15)


def test_a_negative_price_is_refused() -> None:
    with pytest.raises(CostError):
        CostBasis(currency="USD", oligo_per_base=-1.0)


def test_an_oligo_line_multiplies_length_and_adds_the_flat_charge() -> None:
    lines = estimate_oligos(PRICED, lengths=[30])
    assert lines[0].amount == pytest.approx(0.15 * 30 + 2.00)
    assert lines[0].unit == "base"


def test_a_fragment_line_prices_per_base_pair() -> None:
    lines = estimate_fragments(PRICED, lengths=[500])
    assert lines[0].amount == pytest.approx(0.07 * 500 + 5.00)
    assert lines[0].unit == "bp"


def test_an_unpriced_line_carries_the_reason_rather_than_a_number() -> None:
    lines = estimate_oligos(UNPRICED, lengths=[30, 32])
    assert [line.amount for line in lines] == [None, None]
    assert all("No oligo price" in (line.unpriced_reason or "") for line in lines)


def test_a_priced_set_totals() -> None:
    estimate = total_of(PRICED, estimate_oligos(PRICED, lengths=[30, 30]))
    assert estimate.total == pytest.approx(2 * (0.15 * 30 + 2.00))
    assert estimate.unavailable_reason is None


def test_one_unpriced_line_makes_the_whole_total_unavailable() -> None:
    """A total over the priced lines only is an underestimate wearing the
    authority of a total — worse than no total at all."""
    lines = estimate_oligos(PRICED, lengths=[30]) + estimate_oligos(UNPRICED, lengths=[30])
    estimate = total_of(PRICED, lines)
    assert estimate.total is None
    assert estimate.unavailable_reason is not None
    # The lines that do have prices are still returned.
    assert [line.amount for line in estimate.lines].count(None) == 1


def test_no_lines_at_all_uses_the_reason_the_caller_gave() -> None:
    """"Nothing to add up" and "the total is zero" are different statements."""
    estimate = total_of(PRICED, [], no_lines_reason="Nothing orderable yet.")
    assert estimate.total is None
    assert estimate.unavailable_reason == "Nothing orderable yet."


def test_budget_comparison_needs_both_sides() -> None:
    """`over_budget` is None, never False, when either side is unknown. A
    default of False would read as "within budget"."""
    estimate = total_of(PRICED, estimate_oligos(UNPRICED, lengths=[30]), budget_amount=100.0)
    assert estimate.total is None
    assert estimate.over_budget is None
    assert estimate.remaining is None


def test_a_total_over_the_budget_says_so() -> None:
    estimate = total_of(
        PRICED,
        estimate_oligos(PRICED, lengths=[30] * 20),
        budget_amount=50.0,
        budget_currency="USD",
    )
    assert estimate.over_budget is True
    assert estimate.remaining is not None and estimate.remaining < 0


def test_a_total_under_the_budget_reports_what_is_left() -> None:
    estimate = total_of(
        PRICED,
        estimate_oligos(PRICED, lengths=[30]),
        budget_amount=100.0,
        budget_currency="USD",
    )
    assert estimate.over_budget is False
    assert estimate.remaining == pytest.approx(100.0 - (0.15 * 30 + 2.00))


def test_two_currencies_are_not_compared() -> None:
    """This module does not convert. An exchange rate is another number nobody
    stated, and applying yesterday's would misreport the budget."""
    estimate = total_of(
        PRICED,
        estimate_oligos(PRICED, lengths=[30]),
        budget_amount=10.0,
        budget_currency="EUR",
    )
    assert estimate.total is not None
    assert estimate.over_budget is None
    assert estimate.remaining is None


def test_settings_round_trip() -> None:
    restored = CostBasis.from_settings(PRICED.to_settings())
    assert restored == PRICED


def test_absent_settings_produce_an_unpriced_basis_not_zeros() -> None:
    """Zero is a claim that something is free."""
    basis = CostBasis.from_settings({})
    assert basis.oligo_per_base is None
    assert basis.fragment_per_bp is None
