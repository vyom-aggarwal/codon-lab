"""The model layer: the seam, the registry, and the honesty boundary.

The rule these tests hold in place is that no scientific number is fabricated
outside a provider that declares itself a fabricator, and that a provider which
cannot run says so instead of returning something worthless.
"""

from __future__ import annotations

import uuid

import pytest

from catalyst.domain.goal import Objective
from catalyst.domain.variants import enumerate_single_substitutions
from catalyst.providers import (
    Capabilities,
    Predictor,
    StructureRef,
    TargetContext,
    describe,
    resolve,
)
from catalyst.providers.mock import MOCK_FITNESS, MOCK_STABILITY
from catalyst.providers.registry import REGISTRY

SEQUENCE = "MKFVAILGCDWTYSPNQREH"


def labels(length: int) -> list[str | None]:
    return [str(index + 1) for index in range(length)]


def context(*, structure: bool = True) -> TargetContext:
    return TargetContext(
        target_id=uuid.uuid4(),
        sequence=SEQUENCE,
        scheme_label="Test scheme",
        objective=Objective.THERMOSTABILITY,
        structure=(
            StructureRef(
                identifier="1ABC",
                source="pdb",
                content_hash="sha256:deadbeef",
                chain="A",
            )
            if structure
            else None
        ),
    )


def candidates() -> list:
    return list(enumerate_single_substitutions(SEQUENCE, labels(len(SEQUENCE))).candidates)


# --------------------------------------------------------------------------- #
# The protocol
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("predictor", list(REGISTRY.values()), ids=lambda p: p.id)
def test_every_registered_predictor_satisfies_the_protocol(predictor: Predictor) -> None:
    assert isinstance(predictor, Predictor)


@pytest.mark.parametrize("predictor", list(REGISTRY.values()), ids=lambda p: p.id)
def test_every_predictor_declares_a_sign_convention_per_metric(predictor: Predictor) -> None:
    """Specification §7: stated in the column header and never changed. It
    travels with the metric so a second screen cannot contradict the first."""
    assert predictor.metrics
    for metric in predictor.metrics:
        assert metric.sign_convention.strip()


@pytest.mark.parametrize("predictor", list(REGISTRY.values()), ids=lambda p: p.id)
def test_a_predictor_cannot_produce_a_score_row(predictor: Predictor) -> None:
    """It returns ScoreValue, which carries no run and no model version. The
    integrity rule from ARCHITECTURE.md §5 is enforced by the type, not by
    remembering to attach provenance later.

    A predictor that refuses to run here satisfies the rule trivially and more
    strongly — it produced nothing at all, which is what an unavailable predictor
    must do.
    """
    from catalyst.providers.base import PredictorUnavailableError

    try:
        values = predictor.score(candidates()[:3], context())
    except PredictorUnavailableError:
        return
    for value in values:
        assert not hasattr(value, "run_id")
        assert not hasattr(value, "model_version_id")


def test_describe_exposes_everything_the_interface_varies_by() -> None:
    described = describe(MOCK_STABILITY)
    assert described["is_mock"] is True
    assert described["weights_hash"]
    assert described["objectives"] == ["thermostability"]
    assert described["requires"] == {
        "structure": True,
        "msa": False,
        "max_length": None,
        "gpu": False,
    }


# --------------------------------------------------------------------------- #
# Capabilities
# --------------------------------------------------------------------------- #


def test_a_predictor_needing_a_structure_says_so_when_there_is_none() -> None:
    reason = MOCK_STABILITY.requires.unmet(context(structure=False))
    assert reason is not None
    assert "structure" in reason.lower()
    # The reason is a sentence the user can act on, not a code.
    assert "attach" in reason.lower()


def test_a_sequence_only_predictor_runs_without_a_structure() -> None:
    assert MOCK_FITNESS.requires.unmet(context(structure=False)) is None


def test_an_msa_requirement_is_unmet_because_no_provider_exists() -> None:
    needs_msa = Capabilities(needs_msa=True)
    reason = needs_msa.unmet(context())
    assert reason is not None
    assert "alignment" in reason.lower()


def test_a_length_limit_is_reported_with_both_numbers() -> None:
    reason = Capabilities(max_length=5).unmet(context())
    assert reason is not None
    assert "5" in reason and str(len(SEQUENCE)) in reason


# --------------------------------------------------------------------------- #
# The mock's honesty properties
# --------------------------------------------------------------------------- #


def test_every_mock_number_comes_from_a_provider_that_declares_itself() -> None:
    assert MOCK_STABILITY.is_mock is True
    assert MOCK_FITNESS.is_mock is True


def test_the_mock_cites_nothing_because_there_is_nothing_to_cite() -> None:
    for predictor in (MOCK_STABILITY, MOCK_FITNESS):
        assert "not a model" in predictor.citation.lower()


def test_the_weights_hash_addresses_the_generator_not_invented_weights() -> None:
    assert MOCK_STABILITY.weights_hash.startswith("sha256:")
    assert MOCK_STABILITY.weights_hash != MOCK_FITNESS.weights_hash


def test_output_is_deterministic() -> None:
    ctx = context()
    first = MOCK_STABILITY.score(candidates(), ctx)
    second = MOCK_STABILITY.score(candidates(), ctx)
    assert [(v.variant_code, v.value, v.uncertainty) for v in first] == [
        (v.variant_code, v.value, v.uncertainty) for v in second
    ]


def test_output_depends_on_the_structure_it_was_given() -> None:
    """A structure that changed underneath a target must not silently produce
    the same numbers."""
    other = TargetContext(
        target_id=uuid.uuid4(),
        sequence=SEQUENCE,
        scheme_label="Test scheme",
        structure=StructureRef(
            identifier="1ABC", source="pdb", content_hash="sha256:cafe", chain="A"
        ),
    )
    a = {v.variant_code: v.value for v in MOCK_STABILITY.score(candidates(), context())}
    b = {v.variant_code: v.value for v in MOCK_STABILITY.score(candidates(), other)}
    assert a != b


def test_different_variants_get_different_values() -> None:
    values = [v.value for v in MOCK_STABILITY.score(candidates(), context())]
    assert len(set(values)) > len(values) // 2


def test_a_stability_prediction_always_carries_an_interval() -> None:
    """Specification §7: a bare point estimate is not acceptable output for a
    stability prediction."""
    for value in MOCK_STABILITY.score(candidates(), context()):
        assert value.uncertainty is not None
        assert value.ci_low is not None and value.ci_high is not None
        assert value.ci_low < value.value < value.ci_high


def test_a_point_estimate_metric_reports_no_invented_interval() -> None:
    """A masked-marginal log-odds ratio has no interval. Inventing one would be
    worse than omitting it."""
    assert MOCK_FITNESS.metrics[0].reports_interval is False
    for value in MOCK_FITNESS.score(candidates(), context()):
        assert value.uncertainty is None
        assert value.ci_low is None and value.ci_high is None


def test_the_two_mocks_mostly_agree_and_sometimes_do_not() -> None:
    """A demo where the predictors always disagree misleads exactly as badly as
    one where they never do. Both are checked, because an earlier version of the
    generator was anti-correlated by construction and neither the run nor the
    tests would have noticed."""
    from catalyst.domain.aggregate import Series, aggregate

    ctx = context()
    stability = {v.variant_code: v.value for v in MOCK_STABILITY.score(candidates(), ctx)}
    fitness = {v.variant_code: v.value for v in MOCK_FITNESS.score(candidates(), ctx)}

    rows = aggregate(
        {
            "stability": Series(stability, higher_is_better=False),
            "fitness": Series(fitness, higher_is_better=True),
        }
    )
    spreads = sorted(row.disagreement for row in rows if row.disagreement is not None)
    median = spreads[len(spreads) // 2]

    assert median < 0.3, "the mocks disagree about everything; the column would be noise"
    assert spreads[-1] > 0.05, "the mocks never disagree; the column would never show"


def test_the_mock_range_is_plausibly_shaped() -> None:
    """Most substitutions destabilize, and most are evolutionarily unfavourable.
    Fiction with a badge on it, but fiction shaped like the thing it stands in
    for — a uniform sheet of numbers would not exercise a ranking at all."""
    ctx = context()
    ddg = [v.value for v in MOCK_STABILITY.score(candidates(), ctx)]
    llr = [v.value for v in MOCK_FITNESS.score(candidates(), ctx)]

    assert sum(1 for value in ddg if value > 0) > len(ddg) // 2
    assert sum(1 for value in llr if value < 0) > len(llr) // 2
    assert min(ddg) >= -1.2 and max(ddg) <= 3.2
    assert min(llr) >= -9.0 and max(llr) <= 2.0


# --------------------------------------------------------------------------- #
# The registry
# --------------------------------------------------------------------------- #


def test_the_mock_group_turns_on_the_whole_synthetic_set() -> None:
    predictors, unknown = resolve(("mock",))
    assert {p.id for p in predictors} == {MOCK_STABILITY.id, MOCK_FITNESS.id}
    assert unknown == []


def test_an_unknown_id_is_reported_not_skipped() -> None:
    """A typo that silently disables a predictor produces a run that looks
    complete and is missing a column."""
    predictors, unknown = resolve(("mock", "esm2_650m"))
    assert unknown == ["esm2_650m"]
    assert len(predictors) == 2


def test_duplicates_collapse_and_order_follows_configuration() -> None:
    predictors, _ = resolve(("mock_fitness", "mock", "mock_fitness"))
    assert [p.id for p in predictors] == [MOCK_FITNESS.id, MOCK_STABILITY.id]


def test_no_predictor_claims_an_unnamed_objective() -> None:
    """`other` is the bucket for an objective the parser could not name."""
    for predictor in REGISTRY.values():
        assert Objective.OTHER not in predictor.objectives


def test_only_the_mock_predictors_declare_themselves_synthetic() -> None:
    """The registry now holds real models beside the synthetic ones. `is_mock` is
    what separates them, and it is what every badge in the product keys off."""
    synthetic = {p.id for p in REGISTRY.values() if p.is_mock}
    real = {p.id for p in REGISTRY.values() if not p.is_mock}
    assert synthetic == {"mock_stability", "mock_fitness"}
    assert real, "Phase 6 registers real predictors"
    assert not (synthetic & real)


def test_every_real_predictor_carries_a_citation_that_is_not_a_disclaimer() -> None:
    for predictor in REGISTRY.values():
        if predictor.is_mock:
            continue
        assert "doi.org" in predictor.citation
