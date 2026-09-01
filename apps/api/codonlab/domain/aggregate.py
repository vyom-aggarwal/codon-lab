"""Consensus across predictors — and the disagreement between them.

Two rules from the specification shape everything here.

**Do not average scores.** A ΔΔG in kcal/mol and a log-likelihood ratio are not
on the same scale, are not in the same units, and are not linearly comparable.
Averaging them produces a number with no meaning that nevertheless sorts, which
is the worst possible failure mode. Each predictor's values are converted to
ranks within its own series first; only ranks are combined.

**Surface disagreement, do not average it away.** When two predictors put the
same variant in opposite halves of their rankings, that is the most useful signal
on the screen. It is computed and returned alongside the consensus, never folded
into it.

Nothing here is a threshold. There is no cutoff separating "agreement" from
"disagreement" — the spread is reported as a number and the reader judges it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Series:
    """One predictor's values across the candidate set.

    ``higher_is_better`` is the predictor's own declaration about its own metric,
    not an interpretation applied from outside. For a ΔΔG reported destabilizing-
    positive it is false; for a fitness log-likelihood ratio it is true.
    """

    values: Mapping[str, float]
    higher_is_better: bool


@dataclass(frozen=True, slots=True)
class Aggregate:
    code: str
    #: Source key to that source's normalised rank, 1.0 best, 0.0 worst.
    ranks: Mapping[str, float]
    #: Mean of the available normalised ranks. Not a physical quantity, and
    #: labelled as such wherever it is displayed.
    consensus: float
    #: Spread between the highest and lowest normalised rank. Null when fewer
    #: than two predictors scored this variant — with one opinion there is
    #: nothing to disagree about, and zero would read as unanimity.
    disagreement: float | None
    sources_scored: int


def normalised_ranks(series: Series) -> dict[str, float]:
    """Values to normalised ranks in [0, 1], 1.0 being the best value.

    Ties take the mean of the ranks they span, so a predictor that returns the
    same value for two variants does not manufacture a difference between them —
    and a run where every value ties comes out flat rather than ordered by
    whatever the dictionary iteration happened to be.
    """
    ordered = sorted(
        series.values.items(), key=lambda item: item[1], reverse=series.higher_is_better
    )
    count = len(ordered)
    if count == 0:
        return {}
    if count == 1:
        return {ordered[0][0]: 1.0}

    ranks: dict[str, float] = {}
    index = 0
    while index < count:
        end = index
        while end + 1 < count and ordered[end + 1][1] == ordered[index][1]:
            end += 1
        # Positions index..end are tied; every one of them takes the mean position.
        mean_position = (index + end) / 2
        for tied in range(index, end + 1):
            ranks[ordered[tied][0]] = 1.0 - mean_position / (count - 1)
        index = end + 1
    return ranks


def aggregate(sources: Mapping[str, Series]) -> list[Aggregate]:
    """Combine several predictors' series into one ranking.

    A variant scored by only some of the predictors is kept and its consensus is
    computed from what exists. It is not imputed to the mean and it is not
    dropped: ``sources_scored`` says how many opinions stand behind the number,
    so a variant ranked by one predictor is never mistaken for one ranked by
    three.
    """
    by_source = {key: normalised_ranks(series) for key, series in sources.items()}

    codes: set[str] = set()
    for ranks in by_source.values():
        codes.update(ranks)

    results: list[Aggregate] = []
    for code in codes:
        ranks = {key: values[code] for key, values in by_source.items() if code in values}
        if not ranks:
            continue
        spread = list(ranks.values())
        results.append(
            Aggregate(
                code=code,
                ranks=ranks,
                consensus=sum(spread) / len(spread),
                disagreement=(max(spread) - min(spread)) if len(spread) > 1 else None,
                sources_scored=len(spread),
            )
        )

    # Consensus descending, then code, so an identical run always produces an
    # identical order rather than one that depends on set iteration.
    results.sort(key=lambda item: (-item.consensus, item.code))
    return results


def top(results: Sequence[Aggregate], limit: int | None) -> list[Aggregate]:
    """The first ``limit`` results, or all of them when no budget was stated.

    ``limit`` comes from a number the user wrote down — a plate count, an
    ordering budget. There is no default: an unstated budget truncates nothing.
    """
    if limit is None or limit <= 0:
        return list(results)
    return list(results[:limit])
