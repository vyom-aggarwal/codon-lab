"""Predicted against measured: how well did a predictor actually do.

Specification §5.9 and §2.3. Pure arithmetic — no database, no session — so
every statistic below is testable without a stack.

ARCHITECTURE.md §13 binds this module more tightly than anything else in the
build, and it is worth restating why. Spearman rho and precision@k are rank
statistics, and rank statistics are invariant to monotonic transforms. **A
predictor offset by a constant +2 kcal/mol scores rho = 1.00 and
precision@10 = 1.0 while being useless for the decision the user is actually
making**, which is absolute: will this variant hold at 65 C. So a scorecard is
required to report, in one view:

===========  ================================  =======================================
Kind         Statistic                         Answers
===========  ================================  =======================================
Rank         Spearman rho, precision@k         Does it put the right variants on top?
**Error**    **MAE, in the metric's unit**     **How far off is it?**
**Bias**     **Mean signed error**             **Is it off in one direction?**
===========  ================================  =======================================

A headline that is a rank statistic alone is a defect, not a simplification.

The hard part is that **error and bias are not always computable**, and this
module refuses to fake them when they are not. Two gates, both of which return a
stated reason rather than a number:

**Units must match.** A predicted ddG in kcal/mol and a measured T50 in degrees
Celsius cannot be subtracted. Specification §7 is explicit that a Tm shift in C
must never be claimed from a ddG prediction, so no conversion is attempted and
no factor is invented — the error row reads unavailable and names both units.

**Sign conventions must match.** If the predictor reports destabilizing-positive
and the upload reports higher-is-better, the same physical outcome has opposite
signs in the two series, and subtracting them would produce a large error that
is an artefact of notation. This module will **not** silently negate one series
to make them agree: it says which convention each side uses and stops. Flipping
a sign on the user's behalf is the class of decision HANDOFF.md §7 records the
owner forbidding in as many words.

Rank statistics survive both gates, because a rank needs an order and not a
unit. They are still never reported alone: when error is unavailable the reason
travels with the scorecard and is rendered beside the rank figure, so a reader
cannot mistake "we could not measure the error" for "the error is small".
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

#: How many bins the calibration curve uses when there is data for them. An
#: interface choice, not a scientific one: it controls how the same numbers are
#: drawn, never which numbers they are. Every bin reports its own count so a
#: reader can see a bin resting on three points and discount it.
DEFAULT_CALIBRATION_BINS = 10


@dataclass(frozen=True, slots=True)
class Paired:
    """One variant with both a prediction and a measurement.

    ``code`` is the canonical mutation code and is for **display only**.
    ``key`` is what identifies the pair, and the two are deliberately separate:
    a pooled scorecard spans several targets, and two different proteins can
    both have an ``A1N``. Using the code as identity silently collapsed them —
    on this machine one card reported 192 pairs while carrying 24 distinct
    codes, so the scatter drew 24 marks under a caption claiming 192 and
    precision@k counted one code eight times. Callers pass the variant id.

    ``predicted`` and ``measured`` are the raw values in each side's own units
    and own sign convention — nothing is normalised on the way in, so what a
    statistic did to them stays visible in this module rather than happening at
    the call site.
    """

    code: str
    predicted: float
    measured: float
    #: Unique per pair. Defaults to the code so existing hermetic tests, which
    #: never pool across targets, stay meaningful without restating it.
    key: str = ""

    @property
    def identity(self) -> str:
        return self.key or self.code


@dataclass(frozen=True, slots=True)
class Convention:
    """What a series of numbers means: its unit and which way is better.

    Neither field has a default. ``unit`` comes from the predictor's own
    ``MetricSpec`` on one side and from the user's column mapping on the other;
    ``higher_is_better`` is a fact about an assay that only the person who ran
    it knows, and is required at import rather than guessed.
    """

    #: The metric's identifier, e.g. ``ddg_kcal_mol`` or ``tm_celsius``.
    metric: str
    #: Written as it is displayed, e.g. ``kcal/mol``. Compared literally.
    unit: str
    higher_is_better: bool

    @property
    def sign_note(self) -> str:
        return (
            "higher is better" if self.higher_is_better else "lower is better"
        )


@dataclass(frozen=True, slots=True)
class Commensurability:
    """Whether two series may be subtracted, and if not, why not."""

    comparable: bool
    #: Empty when comparable. Otherwise the sentence shown wherever an error or
    #: bias figure would have been.
    reason: str


def commensurable(predicted: Convention, measured: Convention) -> Commensurability:
    """Whether an absolute error between these two series would mean anything.

    Unit equality is checked literally rather than through a conversion table.
    A table would be a place to put a factor, and a wrong factor is invisible in
    the output — it produces a plausible error figure rather than a refusal.
    """
    if predicted.unit != measured.unit:
        return Commensurability(
            comparable=False,
            reason=(
                f"Predicted {predicted.metric} is in {predicted.unit} and measured "
                f"{measured.metric} is in {measured.unit}. These are not the same "
                "quantity, so an absolute error between them would not mean "
                "anything. No conversion is applied."
            ),
        )
    if predicted.higher_is_better != measured.higher_is_better:
        return Commensurability(
            comparable=False,
            reason=(
                f"Predicted {predicted.metric} is reported {predicted.sign_note} and "
                f"measured {measured.metric} is reported {measured.sign_note}. The "
                "same outcome carries opposite signs in the two series; negating "
                "one of them is a decision this product does not make on your "
                "behalf. Restate the sign convention on import to compare them."
            ),
        )
    return Commensurability(comparable=True, reason="")


def _ranks(values: Sequence[float], *, higher_is_better: bool) -> list[float]:
    """Ranks with ties averaged, 1 being the best value under the convention.

    Ties take the mean of the positions they span, so a series with repeated
    values does not manufacture an ordering between equal things — the same rule
    ``domain/aggregate.normalised_ranks`` uses, for the same reason.
    """
    order = sorted(range(len(values)), key=lambda i: values[i], reverse=higher_is_better)
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        end = index
        while end + 1 < len(order) and values[order[end + 1]] == values[order[index]]:
            end += 1
        mean_rank = (index + end) / 2 + 1
        for tied in range(index, end + 1):
            ranks[order[tied]] = mean_rank
        index = end + 1
    return ranks


def spearman(
    pairs: Sequence[Paired], predicted: Convention, measured: Convention
) -> float | None:
    """Rank correlation, oriented so +1 always means the two agree about quality.

    Each series is ranked by its own declared direction, so a ddG reported
    destabilizing-positive and a T50 reported higher-is-better both rank the
    genuinely better variant first. That makes the sign readable without holding
    two conventions in your head: +1 is agreement, -1 is systematic inversion.

    Returns None when fewer than two pairs exist, or when either series is
    entirely tied. A correlation over one point, or over a series with no
    variation, is not a small number — it is undefined, and returning 0.0 would
    be a fabricated one.
    """
    if len(pairs) < 2:
        return None

    predicted_values = [pair.predicted for pair in pairs]
    measured_values = [pair.measured for pair in pairs]
    if len(set(predicted_values)) < 2 or len(set(measured_values)) < 2:
        return None

    x = _ranks(predicted_values, higher_is_better=predicted.higher_is_better)
    y = _ranks(measured_values, higher_is_better=measured.higher_is_better)

    n = len(pairs)
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    covariance = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y, strict=True))
    spread_x = math.sqrt(sum((a - mean_x) ** 2 for a in x))
    spread_y = math.sqrt(sum((b - mean_y) ** 2 for b in y))
    if spread_x == 0.0 or spread_y == 0.0:
        return None
    return covariance / (spread_x * spread_y)


@dataclass(frozen=True, slots=True)
class PrecisionAtK:
    k: int
    value: float
    #: The codes the predictor put in its top k that the bench also put there.
    hits: tuple[str, ...]


def precision_at_k(
    pairs: Sequence[Paired],
    predicted: Convention,
    measured: Convention,
    *,
    k: int,
) -> PrecisionAtK | None:
    """Of the k variants the predictor ranked best, how many the bench agreed on.

    Returns None when there are fewer than k pairs. Reporting precision@10 over
    six measurements would divide by a k that does not exist; the honest answer
    is that the question cannot be asked yet, not a number scaled to look like
    it can.

    Ties at the boundary are resolved by the pair's identity so the same data
    always yields the same set, rather than one that depends on sort stability.

    Membership is tested on ``identity``, never on the displayed code. Two
    targets can carry the same mutation code, and matching on the code would
    let one variant's rank credit another variant's measurement — inflating
    precision for exactly the pooled, cross-target card the statistic is most
    often read on.
    """
    if k <= 0 or len(pairs) < k:
        return None

    def best(by: str, higher_is_better: bool) -> list[Paired]:
        ordered = sorted(
            pairs,
            key=lambda pair: (
                -getattr(pair, by) if higher_is_better else getattr(pair, by),
                pair.identity,
            ),
        )
        return ordered[:k]

    top_predicted = best("predicted", predicted.higher_is_better)
    top_measured = {pair.identity for pair in best("measured", measured.higher_is_better)}
    hits = tuple(pair.code for pair in top_predicted if pair.identity in top_measured)
    return PrecisionAtK(k=k, value=len(hits) / k, hits=hits)


@dataclass(frozen=True, slots=True)
class ErrorTerms:
    """Absolute agreement. Only ever built when the two series are commensurable."""

    #: Mean absolute error, in the shared unit.
    mae: float
    #: Mean signed error, in the shared unit, as predicted minus measured.
    #: Positive means the predictor reads high.
    mean_signed_error: float
    unit: str
    #: Spelled out because a bias term whose direction is ambiguous is worse
    #: than none: a reader who guesses wrong corrects in the wrong direction.
    sign_note: str


def error_terms(
    pairs: Sequence[Paired], predicted: Convention, measured: Convention
) -> ErrorTerms | None:
    """MAE and mean signed error, or None when the series cannot be subtracted.

    The caller is expected to have consulted `commensurable` and to be showing
    its reason; returning None here as well means a caller that forgets cannot
    accidentally render a zero.
    """
    if not pairs or not commensurable(predicted, measured).comparable:
        return None
    errors = [pair.predicted - pair.measured for pair in pairs]
    return ErrorTerms(
        mae=sum(abs(error) for error in errors) / len(errors),
        mean_signed_error=sum(errors) / len(errors),
        unit=predicted.unit,
        sign_note=(
            f"Predicted minus measured, in {predicted.unit}. "
            "Positive means the predictor reads high."
        ),
    )


@dataclass(frozen=True, slots=True)
class CalibrationBin:
    #: Mean predicted value in this bin, in the shared unit.
    predicted: float
    #: Mean measured value in this bin, in the shared unit.
    measured: float
    count: int


def calibration(
    pairs: Sequence[Paired],
    predicted: Convention,
    measured: Convention,
    *,
    bins: int = DEFAULT_CALIBRATION_BINS,
) -> tuple[CalibrationBin, ...]:
    """Mean measured against mean predicted, in equal-count bins.

    Read against the identity line: a well-calibrated predictor's bins sit on
    it, and a predictor with a constant offset sits on a line parallel to it —
    which is the failure a rank statistic cannot see and this curve can.

    Empty when the series are not commensurable. A calibration curve is a claim
    about absolute values, so drawing one across two different units would be
    the same error the error terms refuse to make.

    Bins are equal-count rather than equal-width so that a dense cluster of
    predictions does not collapse into one bin while outliers each get their
    own. The bin count falls automatically when there is not enough data to
    fill the requested number with at least two points each.
    """
    if len(pairs) < 2 or not commensurable(predicted, measured).comparable:
        return ()

    usable = min(bins, len(pairs) // 2)
    if usable < 1:
        return ()

    ordered = sorted(pairs, key=lambda pair: (pair.predicted, pair.code))
    out: list[CalibrationBin] = []
    total = len(ordered)
    for index in range(usable):
        start = index * total // usable
        end = (index + 1) * total // usable
        chunk = ordered[start:end]
        if not chunk:
            continue
        out.append(
            CalibrationBin(
                predicted=sum(pair.predicted for pair in chunk) / len(chunk),
                measured=sum(pair.measured for pair in chunk) / len(chunk),
                count=len(chunk),
            )
        )
    return tuple(out)


@dataclass(frozen=True, slots=True)
class Scorecard:
    """One predictor's record against one set of measurements.

    Everything ARCHITECTURE.md §13 requires is a field here rather than
    something a caller may or may not ask for, so a renderer that shows the rank
    figure has the error figure and the bias figure already in its hand — and,
    when they could not be computed, the sentence saying why.
    """

    model_id: str
    predicted: Convention
    measured: Convention
    #: How many variants had both a prediction and a measurement.
    n: int
    #: Oriented so +1 means the predictor and the bench agree about quality.
    spearman: float | None
    precision: PrecisionAtK | None
    #: None exactly when `commensurability.comparable` is false, or n is 0.
    error: ErrorTerms | None
    commensurability: Commensurability
    calibration: tuple[CalibrationBin, ...]
    #: Every number the predictor produced that no measurement matched, and
    #: every measurement no prediction matched, so the reader can see how much
    #: of each side this scorecard actually rests on.
    predicted_without_measurement: int
    measured_without_prediction: int
    #: True when any score behind this card came from a fabricating provider.
    #: A scorecard built on synthetic predictions is not evidence about a model
    #: and says so on its face.
    is_mock: bool

    @property
    def rank_only(self) -> bool:
        """Whether this card carries rank statistics and no error term.

        Callers render the commensurability reason whenever this is true. It is
        a property rather than a caller-side comparison so that the condition
        the interface branches on is defined once, here.
        """
        return self.error is None


def build(
    *,
    model_id: str,
    pairs: Sequence[Paired],
    predicted: Convention,
    measured: Convention,
    k: int,
    predicted_without_measurement: int = 0,
    measured_without_prediction: int = 0,
    is_mock: bool = False,
    bins: int = DEFAULT_CALIBRATION_BINS,
) -> Scorecard:
    """Assemble every statistic for one predictor in one pass.

    There is deliberately no way to ask this module for a rank statistic on its
    own. `build` is the entry point, it always computes the error terms when
    they are computable, and it always carries the reason when they are not.
    """
    return Scorecard(
        model_id=model_id,
        predicted=predicted,
        measured=measured,
        n=len(pairs),
        spearman=spearman(pairs, predicted, measured),
        precision=precision_at_k(pairs, predicted, measured, k=k),
        error=error_terms(pairs, predicted, measured),
        commensurability=commensurable(predicted, measured),
        calibration=calibration(pairs, predicted, measured, bins=bins),
        predicted_without_measurement=predicted_without_measurement,
        measured_without_prediction=measured_without_prediction,
        is_mock=is_mock,
    )


def accumulate(cards: Mapping[str, Sequence[Scorecard]]) -> dict[str, Scorecard]:
    """Deliberately not implemented as an average of scorecards.

    The persistent scorecard in §5.9 accumulates "per predictor per target class
    across the lab's projects". Averaging finished scorecards would weight a card
    resting on 6 measurements equally with one resting on 2,000, and averaging
    two Spearman coefficients is not a Spearman coefficient of anything. The
    accumulation is therefore done by pooling the underlying pairs and building
    one card — see `services/measurements.scorecards`, which does exactly that.

    This function exists to hold the explanation at the place someone would
    reach for the shortcut.
    """
    raise NotImplementedError(
        "Accumulate by pooling Paired values and calling build() once, not by "
        "averaging finished scorecards. See the docstring."
    )
