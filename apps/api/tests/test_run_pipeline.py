"""The run pipeline: its shape, its parameters, and the gate in front of it.

Hermetic, like the rest of this suite. Everything here is either pure or stops
before the first database call — the behaviour that genuinely crosses Postgres
is asserted end to end over HTTP in `scripts/verify_gates.py`, which is the
boundary a future caller actually crosses.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from codonlab.models import Goal
from codonlab.models.base import utcnow
from codonlab.providers.mock import MOCK_FITNESS, MOCK_STABILITY
from codonlab.services import runs as service
from codonlab.services.targets import ServiceError

# --------------------------------------------------------------------------- #
# The stage list
# --------------------------------------------------------------------------- #


def test_the_pipeline_is_the_one_the_specification_states() -> None:
    """Specification §5.5, in order: retrieve structure, build MSA, score with
    each predictor, aggregate, filter by constraints, rank."""
    stages = service.plan([MOCK_STABILITY, MOCK_FITNESS])
    assert [stage.kind for stage in stages] == [
        service.STAGE_RETRIEVE_STRUCTURE,
        service.STAGE_BUILD_MSA,
        service.STAGE_SCORE,
        service.STAGE_SCORE,
        service.STAGE_AGGREGATE,
        service.STAGE_FILTER,
        service.STAGE_RANK,
    ]


def test_a_scoring_stage_names_the_predictor_it_belongs_to() -> None:
    stages = service.plan([MOCK_STABILITY])
    scoring = next(stage for stage in stages if stage.kind == service.STAGE_SCORE)
    assert scoring.name == f"score with {MOCK_STABILITY.name}"
    assert scoring.predictor is MOCK_STABILITY


def test_every_stage_has_an_implementation() -> None:
    """A planned stage with no implementation would fail the run at the point it
    was reached, which is the worst moment to discover it."""
    for stage in service.plan([MOCK_STABILITY, MOCK_FITNESS]):
        assert stage.kind in service._IMPLEMENTATIONS


def test_a_run_with_no_predictors_still_has_the_surrounding_stages() -> None:
    assert [stage.kind for stage in service.plan([])] == [
        service.STAGE_RETRIEVE_STRUCTURE,
        service.STAGE_BUILD_MSA,
        service.STAGE_AGGREGATE,
        service.STAGE_FILTER,
        service.STAGE_RANK,
    ]


# --------------------------------------------------------------------------- #
# Run parameters
# --------------------------------------------------------------------------- #


BASE: dict[str, Any] = {
    "predictors": ["mock_stability"],
    "max_variants": None,
    "override_constraints": False,
}


def test_an_absent_patch_leaves_the_defaults_alone() -> None:
    assert service._normalise_config(None, dict(BASE)) == BASE


def test_an_unknown_parameter_is_refused_not_ignored() -> None:
    """A re-run 'with one parameter changed' must not silently change nothing."""
    with pytest.raises(ServiceError) as error:
        service._normalise_config({"temperature": 65}, dict(BASE))
    assert "temperature" in str(error.value)
    assert "max_variants" in error.value.remedy


@pytest.mark.parametrize("value", [0, -1, 1.5, "96", True])
def test_a_budget_that_is_not_a_count_of_variants_is_refused(value: object) -> None:
    with pytest.raises(ServiceError):
        service._normalise_config({"max_variants": value}, dict(BASE))


def test_an_absent_budget_is_allowed_and_means_absent() -> None:
    """No default. An unstated budget truncates nothing."""
    assert service._normalise_config({"max_variants": None}, dict(BASE))["max_variants"] is None


def test_the_override_flag_must_be_a_boolean() -> None:
    with pytest.raises(ServiceError):
        service._normalise_config({"override_constraints": "yes"}, dict(BASE))


def test_a_run_needs_at_least_one_predictor() -> None:
    with pytest.raises(ServiceError):
        service._normalise_config({"predictors": []}, dict(BASE))


def test_a_predictor_that_is_no_longer_available_stops_the_run() -> None:
    """Rather than quietly producing a result with a column missing."""
    with pytest.raises(ServiceError) as error:
        service._resolve_configured({"predictors": ["mock_stability", "esm2_650m"]})
    assert "esm2_650m" in str(error.value)


# --------------------------------------------------------------------------- #
# The confirmation gate — the Phase 3 rule, from its second caller
# --------------------------------------------------------------------------- #


class _SessionStub:
    """Enough of a Session to reach the gate and no further.

    If `create` ever stops calling `require_confirmed` first, it reaches one of
    these methods and the test fails loudly rather than quietly starting a run.
    """

    def __init__(self, goal: Goal | None) -> None:
        self._goal = goal
        self.writes: list[object] = []

    def get(self, model: type, ident: uuid.UUID) -> object | None:
        if model is Goal:
            return self._goal
        raise AssertionError(f"the gate was passed: {model.__name__} was loaded")

    def add(self, entity: object) -> None:  # pragma: no cover - must not be reached
        raise AssertionError("the gate was passed: something was written")

    def exec(self, *args: object, **kwargs: object) -> object:  # pragma: no cover
        raise AssertionError("the gate was passed: the database was queried")


def _goal(*, confirmed: bool) -> Goal:
    return Goal(
        project_id=uuid.uuid4(),
        target_id=uuid.uuid4(),
        raw_text="make it survive 65 C",
        parsed_spec={"objective": "thermostability"},
        confirmed_at=utcnow() if confirmed else None,
    )


def test_no_run_starts_from_an_unconfirmed_parse() -> None:
    """The Phase 3 exit gate, exercised from the caller it was written for.

    The check lives in `services.goals.require_confirmed` rather than on a screen
    precisely because this path exists — and because the worker behind it is a
    third caller that never sees a screen at all.
    """
    goal = _goal(confirmed=False)
    session = _SessionStub(goal)
    dispatched: list[uuid.UUID] = []

    with pytest.raises(ServiceError) as error:
        service.create(
            session,  # type: ignore[arg-type]
            goal_id=goal.id,
            dispatch=lambda run_id: dispatched.append(run_id) or "job",
        )

    assert "not been confirmed" in str(error.value)
    assert error.value.remedy
    # Nothing was queued, so no worker can pick it up later either.
    assert dispatched == []


def test_a_missing_goal_is_refused_with_a_remedy() -> None:
    session = _SessionStub(None)
    with pytest.raises(ServiceError) as error:
        service.create(
            session,  # type: ignore[arg-type]
            goal_id=uuid.uuid4(),
            dispatch=lambda run_id: "job",
        )
    assert "does not exist" in str(error.value)


# --------------------------------------------------------------------------- #
# Content addressing of a scoring stage
# --------------------------------------------------------------------------- #


def test_the_cache_key_covers_the_inputs_a_prediction_depends_on() -> None:
    """ARCHITECTURE.md §6. If the sequence, the structure or the alignment
    changes, the address must change — otherwise a re-run would serve numbers
    computed against something else."""
    import uuid as _uuid

    from codonlab.providers import StructureRef, TargetContext

    def ctx(sequence: str, structure_hash: str | None) -> TargetContext:
        return TargetContext(
            target_id=_uuid.UUID(int=1),
            sequence=sequence,
            scheme_label="scheme",
            structure=(
                None
                if structure_hash is None
                else StructureRef(identifier="1ABC", source="pdb", content_hash=structure_hash)
            ),
        )

    base = ctx("ACDE", "sha256:one").cache_key()
    assert base != ctx("ACDF", "sha256:one").cache_key()
    assert base != ctx("ACDE", "sha256:two").cache_key()
    assert base != ctx("ACDE", None).cache_key()
    assert base == ctx("ACDE", "sha256:one").cache_key()
