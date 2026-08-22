"""The design run: build it, execute it, cancel it, re-run it, diff it.

Three things in this module are load-bearing.

**The confirmation gate has a second caller.** `create` starts by calling
`goals.require_confirmed`. That check lives in the service layer and not on a
screen precisely so that this path — and the worker behind it — cannot bypass it.

**A score acquires its provenance here and nowhere else.** Providers return
`ScoreValue`, which has no run and no model version. This module is the only
thing that turns one into a `Score`, and it cannot do so without both.

**Aggregation, filtering and ranking are derived, not stored.** They are
arithmetic over scores that are already persisted, so writing them down would
create a second copy that can disagree with the first. What *is* stored is the
input to each: the scores, and — as an append-only provenance event — the exact
constraint set the filter applied, so that changing a constraint tomorrow does
not silently rewrite what a run did yesterday.

The stage list follows specification §5.5 exactly: retrieve structure, build MSA,
score with each predictor, aggregate, filter by constraints, rank.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from catalyst.domain import aggregate as ranking_math
from catalyst.domain.goal import GoalSpec, spec_from_json
from catalyst.domain.hashing import content_hash, digest_of, short
from catalyst.domain.variants import (
    Enumeration,
    VariantInput,
    enumerate_single_substitutions,
    hgvs_of,
    label_of,
)
from catalyst.features import structure as structure_features
from catalyst.models import (
    ConstraintKind,
    Goal,
    ModelVersion,
    NumberingScheme,
    ProvenanceEvent,
    ProvenanceEventKind,
    Run,
    RunStage,
    Score,
    Structure,
    Target,
    Variant,
)
from catalyst.models.base import utcnow
from catalyst.models.enums import NumberingKind, RunStatus, StageStatus, StructureSource
from catalyst.providers import MetricSpec, Predictor, StructureRef, TargetContext, resolve
from catalyst.services import constraints as constraint_service
from catalyst.services import goals as goal_service
from catalyst.services import projects as project_service
from catalyst.services import providers as provider_service
from catalyst.services.targets import (
    ServiceError,
    canonical_scheme,
    labels_of,
    refetch_structure,
    require_project,
    require_target,
    structures_for,
)
from catalyst.services.targets import schemes_for as service_schemes

#: A run is handed to a queue by a caller-supplied function. Injected rather than
#: imported so the service can be exercised without Redis, and so that the one
#: place that knows about the queue stays the one place that knows about it.
Dispatch = Callable[[uuid.UUID], str]

STAGE_RETRIEVE_STRUCTURE = "retrieve_structure"
STAGE_BUILD_MSA = "build_msa"
STAGE_SCORE = "score"
STAGE_AGGREGATE = "aggregate"
STAGE_FILTER = "filter"
STAGE_RANK = "rank"

#: Config keys a caller may set. Anything else is rejected rather than ignored,
#: so a re-run "with one parameter changed" cannot silently change nothing.
CONFIG_KEYS = frozenset({"predictors", "max_variants", "override_constraints"})


# --------------------------------------------------------------------------- #
# Planning
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class PlannedStage:
    kind: str
    name: str
    predictor: Predictor | None = None


def plan(predictors: Sequence[Predictor]) -> list[PlannedStage]:
    """The pipeline, in the order specification §5.5 states it.

    Rebuilt from the run's config at execution time rather than read back from
    the stage rows, so the stored stages are a record of what happened and the
    plan is the single definition of what should.
    """
    stages = [
        PlannedStage(STAGE_RETRIEVE_STRUCTURE, "retrieve structure"),
        PlannedStage(STAGE_BUILD_MSA, "build MSA"),
    ]
    stages.extend(
        PlannedStage(STAGE_SCORE, f"score with {predictor.name}", predictor)
        for predictor in predictors
    )
    stages.append(PlannedStage(STAGE_AGGREGATE, "aggregate"))
    stages.append(PlannedStage(STAGE_FILTER, "filter by constraints"))
    stages.append(PlannedStage(STAGE_RANK, "rank"))
    return stages


def _normalise_config(patch: Mapping[str, Any] | None, base: dict[str, Any]) -> dict[str, Any]:
    if not patch:
        return base
    unknown = sorted(set(patch) - CONFIG_KEYS)
    if unknown:
        raise ServiceError(
            f"Unknown run parameter(s): {', '.join(unknown)}.",
            f"Settable parameters are {', '.join(sorted(CONFIG_KEYS))}.",
        )
    merged = dict(base)
    merged.update(patch)

    limit = merged.get("max_variants")
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 1):
        raise ServiceError(
            "max_variants must be a whole number of variants, or absent.",
            "Leave it out to rank everything, or set the number you can order.",
        )
    if not isinstance(merged.get("override_constraints"), bool):
        raise ServiceError(
            "override_constraints must be true or false.",
            "Set it to true only to deliberately design at constrained positions.",
        )
    if not merged.get("predictors"):
        raise ServiceError(
            "A run needs at least one predictor.",
            "Leave `predictors` out to use every provider that supports this objective.",
        )
    return merged


def _resolve_configured(config: Mapping[str, Any]) -> list[Predictor]:
    ids = tuple(str(identifier) for identifier in config.get("predictors", ()))
    predictors, unknown = resolve(ids)
    if unknown:
        raise ServiceError(
            f"This run names {len(unknown)} predictor(s) that are not available: "
            f"{', '.join(unknown)}.",
            "The provider set changed since the run was created. Start a new run.",
        )
    return predictors


# --------------------------------------------------------------------------- #
# Creation
# --------------------------------------------------------------------------- #


#: A run in one of these states is doing, or has done, the work. A failed or
#: cancelled run is not — retrying after a genuine failure must start fresh.
ACTIVE_RUN_STATUSES = (RunStatus.PENDING, RunStatus.RUNNING, RunStatus.SUCCEEDED)


def _active_run_with(
    session: Session, *, goal_id: uuid.UUID, input_hash: str
) -> Run | None:
    """An existing run for this goal with byte-identical inputs, if there is one."""
    return session.exec(
        select(Run)
        .where(
            col(Run.goal_id) == goal_id,
            col(Run.input_hash) == input_hash,
            col(Run.status).in_(ACTIVE_RUN_STATUSES),
        )
        .order_by(col(Run.created_at))
    ).first()


def _record(
    session: Session,
    *,
    kind: ProvenanceEventKind,
    run: Run,
    subject_type: str = "run",
    subject_id: uuid.UUID | None = None,
    actor: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    session.add(
        ProvenanceEvent(
            kind=kind,
            project_id=run.project_id,
            run_id=run.id,
            subject_type=subject_type,
            subject_id=subject_id if subject_id is not None else run.id,
            actor=actor,
            payload=payload or {},
        )
    )


def _structure_ref(
    session: Session, target: Target
) -> tuple[StructureRef | None, Structure | None]:
    """The structure this run will use, as a content address.

    The most recently attached one, named in the stage log rather than chosen
    silently. Nothing is re-fetched here: what a prediction depends on is the
    exact bytes, and those are already addressed by the hash recorded when the
    structure was attached.
    """
    attached = structures_for(session, target.id)
    if not attached:
        return None, None
    structure = attached[-1]
    return (
        StructureRef(
            identifier=structure.identifier,
            source=structure.source.value,
            content_hash=structure.content_hash,
            chain=structure.chain,
            is_predicted=structure.source
            in (StructureSource.ALPHAFOLD_DB, StructureSource.ESMFOLD),
        ),
        structure,
    )


def create(
    session: Session,
    *,
    goal_id: uuid.UUID,
    dispatch: Dispatch,
    config_patch: Mapping[str, Any] | None = None,
    parent_run_id: uuid.UUID | None = None,
    actor: str | None = None,
) -> tuple[Run, bool]:
    """Build a run from a confirmed objective and hand it to the queue.

    Returns the run and whether it was created now. **Starting a run is
    idempotent on its content address**: an identical request returns the run
    that already exists rather than a second one.

    That is not a nicety. `POST` is not idempotent by default, so a client that
    retries after a lost response — a dropped connection, a proxy timeout, a
    double-clicked button — would otherwise start the same work twice, and the
    duplicate would be indistinguishable from a deliberate re-run. The run's
    `input_hash` already covers everything that decides the result: the target,
    the sequence, the structure, the goal, the config, the constraints, the
    cutoffs and the model versions. If all of that matches an active run, the
    request *is* that run.

    Failed and cancelled runs are excluded, so a retry after a genuine failure
    starts fresh rather than returning the corpse.
    """
    # The Phase 3 gate. This is the second caller it was written for.
    goal = goal_service.require_confirmed(session, goal_id)
    target = require_target(session, goal.target_id)

    scheme = canonical_scheme(session, target.id)
    if scheme is None:
        raise ServiceError(
            "This target has no canonical numbering scheme.",
            "Reconcile numbering and confirm a scheme — every mutation code this "
            "run produces would otherwise be ambiguous.",
        )

    spec = spec_from_json(goal.parsed_spec)
    provider_service.require_active()
    supporting = provider_service.predictors_for(spec.objective)
    if not supporting:
        objective = spec.objective.value if spec.objective else "not stated"
        raise ServiceError(
            f"No available predictor supports the objective '{objective}'.",
            "Change the objective chip to one a configured provider covers, or "
            "configure a provider that does. Running anyway would return numbers "
            "about something you did not ask for.",
        )

    config = _normalise_config(
        config_patch,
        {
            "predictors": [predictor.id for predictor in supporting],
            # The budget is a number the user wrote down. Absent means absent.
            "max_variants": spec.budget.variants,
            "override_constraints": False,
        },
    )
    predictors = _resolve_configured(config)

    reference, _ = _structure_ref(session, target)
    constrained = constraint_service.constrained_positions(session, target.id)

    # Everything that decides the result of this run, as one address. It is what
    # the cache keys on, and — because it is complete — what makes starting a run
    # idempotent.
    input_hash = content_hash(
        {
            "target": str(target.id),
            "sequence": digest_of(target.sequence),
            "scheme": scheme.label,
            "structure": None if reference is None else reference.content_hash,
            "goal": goal.parsed_spec,
            "config": config,
            "constraints": {str(k): sorted(v) for k, v in constrained.items()},
            # The burial cutoffs change what the region column says without
            # changing a coordinate, so they are part of this run's content.
            "rsa_cutoffs": project_service.cutoffs_for(
                require_project(session, goal.project_id)
            ).as_manifest(),
            "models": [
                {
                    "id": predictor.id,
                    "version": predictor.version,
                    "weights_hash": predictor.weights_hash,
                }
                for predictor in predictors
            ],
        }
    )

    # Idempotency, checked before the write and enforced by a partial unique
    # index underneath (migration 0003), so a concurrent pair cannot both insert.
    existing = _active_run_with(session, goal_id=goal.id, input_hash=input_hash)
    if existing is not None:
        return existing, False

    run = Run(
        project_id=goal.project_id,
        target_id=target.id,
        goal_id=goal.id,
        status=RunStatus.PENDING,
        config=config,
        parent_run_id=parent_run_id,
        input_hash=input_hash,
    )
    session.add(run)
    try:
        session.flush()
    except IntegrityError:
        # Lost a race with a concurrent identical request. The other one won;
        # this is that same request, so return its run rather than failing.
        session.rollback()
        raced = _active_run_with(session, goal_id=goal_id, input_hash=input_hash)
        if raced is None:
            raise
        return raced, False

    for ordinal, planned in enumerate(plan(predictors)):
        model_version_id: uuid.UUID | None = None
        if planned.predictor is not None:
            # Registered at creation, so the run view can show model, version and
            # weights hash before a single number has been produced.
            model_version_id = provider_service.ensure_model_version(
                session, planned.predictor
            ).id
        session.add(
            RunStage(
                run_id=run.id,
                ordinal=ordinal,
                name=planned.name,
                model_version_id=model_version_id,
                status=StageStatus.PENDING,
            )
        )

    _record(
        session,
        kind=ProvenanceEventKind.RUN_STARTED,
        run=run,
        actor=actor,
        payload={
            "config": config,
            "input_hash": run.input_hash,
            "goal_confirmed_at": goal.confirmed_at.isoformat() if goal.confirmed_at else None,
            "parent_run_id": str(parent_run_id) if parent_run_id else None,
        },
    )
    session.commit()
    session.refresh(run)

    try:
        dispatch(run.id)
    except Exception as error:
        # A run that cannot be dispatched is a failed run, not a run that waits
        # forever looking like it is about to start.
        run.status = RunStatus.FAILED
        run.error = str(error)
        run.finished_at = utcnow()
        session.add(run)
        # Nothing ran, so nothing is left pending. A stage list stuck on
        # "pending" under a failed run reads as work still to come.
        _cancel_pending_stages(session, run.id)
        _record(
            session,
            kind=ProvenanceEventKind.RUN_COMPLETED,
            run=run,
            payload={"status": run.status.value, "error": str(error)},
        )
        session.commit()
        session.refresh(run)

    return run, True


def rerun(
    session: Session,
    *,
    run_id: uuid.UUID,
    dispatch: Dispatch,
    config_patch: Mapping[str, Any] | None = None,
    actor: str | None = None,
) -> tuple[Run, bool]:
    """Re-run with one parameter changed, linked to its predecessor.

    The child carries `parent_run_id`, which is what makes the diff exact rather
    than a guess at which earlier run it should be compared against.
    """
    previous = require_run(session, run_id)
    merged = _normalise_config(config_patch, dict(previous.config))
    if merged == previous.config:
        raise ServiceError(
            "That re-run would use exactly the same parameters.",
            "Change a parameter, or open the existing run — an identical re-run "
            "would produce an identical result from cache and nothing to compare.",
        )
    return create(
        session,
        goal_id=previous.goal_id,
        dispatch=dispatch,
        config_patch=merged,
        parent_run_id=previous.id,
        actor=actor,
    )


# --------------------------------------------------------------------------- #
# Execution
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class _Outcome:
    status: StageStatus
    logs: str
    input_hash: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class _State:
    """What one stage hands to the next. Never persisted; rebuilt on every run."""

    target: Target
    goal: Goal
    spec: GoalSpec
    scheme_label: str
    #: The canonical scheme's label per sequence index. Every mutation code this
    #: run writes is written in these, never in the sequence index.
    labels: list[str | None]
    ctx: TargetContext
    candidates: list[VariantInput] = field(default_factory=list)
    enumeration: Enumeration | None = None
    variant_ids: dict[str, uuid.UUID] = field(default_factory=dict)
    #: Geometry, when a reconciled structure made it measurable.
    features: structure_features.FeatureSet | None = None
    #: Why it was not, when it was not. Reaches the cell as a tooltip.
    feature_note: str | None = None
    #: Metric id to the reason no number exists for it. Rendered as an em dash
    #: with this text on hover — never as an imputed value.
    unavailable: dict[str, str] = field(default_factory=dict)
    scored_models: list[tuple[ModelVersion, Predictor]] = field(default_factory=list)
    removed: dict[str, list[str]] = field(default_factory=dict)
    kept: int = 0


def execute(session: Session, run_id: uuid.UUID) -> Run:
    """Run the pipeline. Idempotent: a second call on a claimed run does nothing.

    Callable from a worker and from a test with equal validity — ARCHITECTURE.md
    §3 requires a job to be runnable from either entry point without changes.
    """
    run = require_run(session, run_id)
    if run.status is not RunStatus.PENDING:
        return run

    run.status = RunStatus.RUNNING
    run.started_at = utcnow()
    session.add(run)
    session.commit()

    target = require_target(session, run.target_id)
    goal = goal_service.require_goal(session, run.goal_id)
    scheme = canonical_scheme(session, target.id)
    reference, _ = _structure_ref(session, target)
    spec = spec_from_json(goal.parsed_spec)

    state = _State(
        target=target,
        goal=goal,
        spec=spec,
        scheme_label=scheme.label if scheme else "",
        labels=labels_of(scheme) if scheme else [],
        ctx=TargetContext(
            target_id=target.id,
            sequence=target.sequence,
            scheme_label=scheme.label if scheme else "",
            objective=spec.objective,
            structure=reference,
            msa=None,
        ),
    )

    predictors = _resolve_configured(run.config)
    planned = plan(predictors)
    stages = _stages_of(session, run.id)
    if len(stages) != len(planned):
        raise ServiceError(
            "This run's stored stages do not match its configuration.",
            "Start a new run — the provider set changed after this one was created.",
        )

    for step, stage in zip(planned, stages, strict=True):
        session.refresh(run)
        if run.status is RunStatus.CANCELLED:
            _cancel_pending_stages(session, run.id)
            session.commit()
            return run
        try:
            _execute_stage(session, run, stage, step, state)
        except Exception as error:
            _fail(session, run, stage, error)
            return run

    session.refresh(run)
    if run.status is RunStatus.RUNNING:
        run.status = RunStatus.SUCCEEDED
        run.finished_at = utcnow()
        session.add(run)
        _record(
            session,
            kind=ProvenanceEventKind.RUN_COMPLETED,
            run=run,
            payload={
                "status": run.status.value,
                "variants_scored": len(state.variant_ids),
                "variants_kept": state.kept,
                "variants_filtered": len(state.removed),
                "models": [version.model_id for version, _ in state.scored_models],
            },
        )
        session.commit()
        session.refresh(run)
    return run


def _fail(session: Session, run: Run, stage: RunStage, error: Exception) -> None:
    stage.status = StageStatus.FAILED
    stage.error = str(error)
    session.add(stage)
    run.status = RunStatus.FAILED
    run.error = f"{stage.name}: {error}"
    run.finished_at = utcnow()
    session.add(run)
    _cancel_pending_stages(session, run.id)
    _record(
        session,
        kind=ProvenanceEventKind.RUN_COMPLETED,
        run=run,
        payload={"status": run.status.value, "failed_stage": stage.name, "error": str(error)},
    )
    session.commit()


def _cancel_pending_stages(session: Session, run_id: uuid.UUID) -> None:
    for stage in _stages_of(session, run_id):
        if stage.status is StageStatus.PENDING:
            stage.status = StageStatus.CANCELLED
            session.add(stage)


def _execute_stage(
    session: Session, run: Run, stage: RunStage, step: PlannedStage, state: _State
) -> None:
    stage.status = StageStatus.RUNNING
    session.add(stage)
    session.commit()

    started = time.perf_counter()
    outcome = _IMPLEMENTATIONS[step.kind](session, run, step, state)
    stage.runtime_ms = int((time.perf_counter() - started) * 1000)
    stage.status = outcome.status
    stage.logs = outcome.logs
    stage.input_hash = outcome.input_hash
    session.add(stage)

    _record(
        session,
        kind=ProvenanceEventKind.RUN_STAGE_COMPLETED,
        run=run,
        subject_type="runstage",
        subject_id=stage.id,
        payload={
            "stage": stage.name,
            "status": outcome.status.value,
            "runtime_ms": stage.runtime_ms,
            "input_hash": outcome.input_hash,
            **outcome.payload,
        },
    )
    session.commit()


# --------------------------------------------------------------------------- #
# Stage implementations
# --------------------------------------------------------------------------- #


def _author_scheme(
    session: Session, target_id: uuid.UUID, structure: Structure
) -> NumberingScheme | None:
    """The reconciled PDB-author scheme for this structure, if the user saved one.

    Features are computed only when it exists. Deriving the sequence-to-structure
    mapping here instead would be exactly the silent inference ARCHITECTURE.md §9
    forbids — and an off-by-one in it would misreport which residues are buried.
    """
    schemes = [
        scheme
        for scheme in service_schemes(session, target_id)
        if scheme.kind is NumberingKind.PDB_AUTHOR
    ]
    exact = f"{structure.identifier} chain {structure.chain}, author numbering"
    for scheme in schemes:
        if scheme.label == exact:
            return scheme
    for scheme in schemes:
        if structure.identifier and scheme.label.startswith(str(structure.identifier)):
            return scheme
    return None


def _active_site_positions(session: Session, target_id: uuid.UUID) -> list[int]:
    """The residues the user marked as catalytic or ligand-contacting.

    Nothing is inferred. No pocket detection, no database lookup, no heuristic:
    the active site is exactly what was annotated on the constraints screen, and
    an empty set means the distance column reads as unavailable.
    """
    positions: set[int] = set()
    for constraint in constraint_service.constraints_for(session, target_id):
        if constraint.kind in (ConstraintKind.CATALYTIC, ConstraintKind.LIGAND_CONTACT):
            positions.update(int(position) for position in constraint.positions)
    return sorted(positions)


def _stage_retrieve_structure(
    session: Session, run: Run, step: PlannedStage, state: _State
) -> _Outcome:
    reference = state.ctx.structure
    if reference is None:
        state.feature_note = (
            "No structure is attached to this target, so no geometry could be measured."
        )
        return _Outcome(
            status=StageStatus.SKIPPED,
            logs=(
                "No structure is attached to this target.\n"
                "Predictors that require one are skipped below with that reason, "
                "and their column reads as unavailable rather than as a number.\n"
                "Solvent accessibility, burial class and distance to the active "
                "site are unavailable for the same reason."
            ),
        )

    kind = "predicted model" if reference.is_predicted else "experimental structure"
    lines = [
        f"Using {reference.source} {reference.identifier or '(uploaded)'} "
        f"chain {reference.chain or '?'} — a {kind}.",
        f"Content address {reference.content_hash}.",
        "Structures are addressed by content, so a file that changed since it "
        "was attached would produce a different address and a different result "
        "rather than a stale one.",
    ]
    payload: dict[str, Any] = {
        "structure": reference.content_hash,
        "source": reference.source,
    }

    lines.extend(_measure_geometry(session, run, state))
    if state.features is not None:
        payload["features"] = len(state.features.residues)

    return _Outcome(
        status=StageStatus.SUCCEEDED,
        logs="\n".join(lines),
        input_hash=reference.content_hash,
        payload=payload,
    )


def _measure_geometry(session: Session, run: Run, state: _State) -> list[str]:
    """Compute solvent accessibility and active-site distance, or say why not.

    Everything that could make these numbers mean something different — the
    reference table, the radii set, the probe radius, the cutoffs in force, the
    coordinate set, how ligands were handled — is written to an append-only
    provenance event. Specification §2.2 applies to a derived feature exactly as
    it applies to a model score.
    """
    target = state.target
    structures = structures_for(session, target.id)
    if not structures:
        return []
    structure = structures[-1]

    scheme = _author_scheme(session, target.id, structure)
    if scheme is None:
        state.feature_note = (
            "This structure's numbering has not been reconciled to the sequence, so "
            "no residue could be identified in it without guessing."
        )
        return [
            "Geometry not measured: " + state.feature_note,
            "Reconcile this structure on the target page, then re-run.",
        ]

    try:
        fetched = refetch_structure(structure)
    except ServiceError as error:
        # A content-hash mismatch is different and is allowed to fail the run:
        # it means the file changed underneath this target.
        if "has changed since it was attached" in str(error):
            raise
        state.feature_note = str(error)
        return [f"Geometry not measured: {error}"]

    cutoffs = project_service.cutoffs_for(require_project(session, run.project_id))
    active = _active_site_positions(session, target.id)

    try:
        features = structure_features.compute(
            structure_text=fetched.text,
            chain_id=structure.chain or "A",
            sequence=target.sequence,
            author_labels=labels_of(scheme),
            active_site_positions=active,
            cutoffs=cutoffs,
            coordinate_source=(
                f"{structure.source.value} {structure.identifier} as downloaded, "
                f"content {short(structure.content_hash)}"
            ),
        )
    except structure_features.StructureFeatureError as error:
        state.feature_note = str(error)
        return [f"Geometry not measured: {error}"]

    state.features = features
    _record(
        session,
        kind=ProvenanceEventKind.FEATURES_COMPUTED,
        run=run,
        subject_type="run_features",
        payload=features.to_json(),
    )

    manifest = features.manifest
    lines = [
        f"Measured solvent accessibility for {len(features.residues):,} residues "
        f"of chain {manifest['chain_measured']}.",
        f"Coordinates: {manifest['assembly']}.",
        f"Normalised by {manifest['reference_set']} (doi:{manifest['reference_doi']}).",
        f"Shrake-Rupley, probe {manifest['sasa']['probe_radius_angstrom']} A, "
        f"{manifest['sasa']['point_number']} points, {manifest['sasa']['vdw_radii']}, "
        f"{manifest['sasa']['atoms']}.",
        f"Burial: core RSA < {cutoffs.core_max}, surface RSA > {cutoffs.surface_min}.",
        f"Ligands: {manifest['ligand_handling']}.",
    ]
    if active:
        lines.append(
            f"Distance measured to {len(active)} annotated active-site residue(s), "
            "minimum non-hydrogen atom separation."
        )
    lines.extend(features.notes)
    return lines


def _stage_build_msa(session: Session, run: Run, step: PlannedStage, state: _State) -> _Outcome:
    predictors = _resolve_configured(run.config)
    needing = [p.name for p in predictors if p.requires.needs_msa]
    detail = (
        f"{len(needing)} predictor(s) in this run require one: {', '.join(needing)}. "
        "They are skipped below."
        if needing
        else "No predictor in this run requires one."
    )
    return _Outcome(
        status=StageStatus.SKIPPED,
        logs=(
            f"No MSA provider is configured in this build, so no alignment was built.\n{detail}\n"
            "Conservation and consensus features — including the >90% conservation "
            "high-risk flag — arrive with the MSA provider and are absent until then."
        ),
        payload={"predictors_requiring_msa": needing},
    )


def _ensure_candidates(session: Session, state: _State) -> None:
    """Enumerate the candidate space once and give every candidate a row.

    Rows are reused across runs on the same target: a variant is the same variant
    whoever proposed it, and its measured values in Phase 8 must join to one row
    rather than to one row per run.
    """
    if state.candidates:
        return

    state.enumeration = enumerate_single_substitutions(state.target.sequence, state.labels)
    state.candidates = list(state.enumeration.candidates)
    existing = {
        code: identifier
        for code, identifier in session.exec(
            select(col(Variant.code), col(Variant.id)).where(
                col(Variant.target_id) == state.target.id
            )
        ).all()
    }

    missing = [candidate for candidate in state.candidates if candidate.code not in existing]
    if missing:
        rows: list[dict[str, Any]] = [
            {
                "id": uuid.uuid4(),
                "created_at": utcnow(),
                "target_id": state.target.id,
                "mutations": list(candidate.mutations),
                "code": candidate.code,
                # The 1-based index into the target sequence, which is what
                # constraints and structures join on. The canonical scheme's
                # name for it lives in `code`. See ARCHITECTURE.md §9.
                "position": candidate.sequence_position,
                # Region needs relative-solvent-accessibility cutoffs, which are
                # an open decision with the domain owner. Null, not guessed.
                "region": None,
                "features": {},
            }
            for candidate in missing
        ]
        for chunk in _chunked(rows, 1000):
            session.execute(pg_insert(Variant).values(chunk))
        session.flush()
        existing.update({str(row["code"]): uuid.UUID(str(row["id"])) for row in rows})

    state.variant_ids = existing


def _enumeration_note(state: _State) -> str:
    """What was enumerated, and what was left out of the candidate set and why."""
    enumeration = state.enumeration
    if enumeration is None:
        return "No candidates were enumerated."

    lines = [
        f"Enumerated {len(enumeration.candidates):,} single substitutions across "
        f"{len(state.target.sequence):,} residues, in {state.scheme_label}."
    ]
    if enumeration.uncovered:
        lines.append(
            f"{len(enumeration.uncovered):,} residues are outside the canonical scheme "
            "and produced no candidates: there is no unambiguous way to name them."
        )
    if enumeration.non_standard:
        lines.append(
            f"{len(enumeration.non_standard):,} residues are not one of the standard "
            "twenty and produced no candidates."
        )
    if enumeration.unwritable:
        lines.append(
            f"{len(enumeration.unwritable):,} residues carry a scheme label that no "
            "mutation code can express — a mature-protein scheme numbers the signal "
            "peptide it excludes at zero and below — and produced no candidates."
        )
    return "\n".join(lines)


def _stage_score(session: Session, run: Run, step: PlannedStage, state: _State) -> _Outcome:
    predictor = step.predictor
    assert predictor is not None  # only score stages carry one, by construction
    version = provider_service.ensure_model_version(session, predictor)

    unmet = predictor.requires.unmet(state.ctx)
    if unmet is not None:
        for metric in predictor.metrics:
            state.unavailable[metric.id] = f"{predictor.name}: {unmet}"
        return _Outcome(
            status=StageStatus.SKIPPED,
            logs=(
                f"{predictor.name} {predictor.version} did not run.\n{unmet}\n"
                "Its column reads as unavailable with this reason. No value was "
                "imputed and no placeholder was written."
            ),
            payload={"skipped_reason": unmet, "model": predictor.id},
        )

    _ensure_candidates(session, state)
    codes = sorted(candidate.code for candidate in state.candidates)
    input_hash = content_hash(
        {
            "model": {
                "id": predictor.id,
                "version": predictor.version,
                "weights_hash": predictor.weights_hash,
            },
            "target": str(state.target.id),
            "context": state.ctx.cache_key(),
            "variants": digest_of(",".join(codes)),
        }
    )

    reused = _reuse_scores(session, run=run, version=version, input_hash=input_hash)
    state.scored_models.append((version, predictor))

    if reused is not None:
        count, source_run = reused
        return _Outcome(
            status=StageStatus.SUCCEEDED,
            logs=(
                f"Reused {count:,} scores from run {source_run}.\n"
                f"Identical input hash {short(input_hash)} — same weights, same "
                "sequence, same structure, same candidate set — so re-executing "
                "could only produce the same numbers."
            ),
            input_hash=input_hash,
            payload={"model": predictor.id, "cached": True, "scores": count},
        )

    values = predictor.score(state.candidates, state.ctx)
    written = _write_scores(session, run=run, version=version, values=values, state=state)

    _record(
        session,
        kind=ProvenanceEventKind.SCORES_WRITTEN,
        run=run,
        subject_type="modelversion",
        subject_id=version.id,
        payload={
            "model": predictor.id,
            "version": predictor.version,
            "weights_hash": predictor.weights_hash,
            "is_mock": predictor.is_mock,
            "metrics": [metric.id for metric in predictor.metrics],
            "count": written,
            "input_hash": input_hash,
        },
    )

    synthetic = (
        "\nEvery number from this predictor is synthetic and badged as such."
        if predictor.is_mock
        else ""
    )
    return _Outcome(
        status=StageStatus.SUCCEEDED,
        logs=(
            f"{_enumeration_note(state)}\n"
            f"{predictor.name} {predictor.version}, weights {short(predictor.weights_hash)}.\n"
            f"Wrote {written:,} scores for "
            f"{', '.join(metric.id for metric in predictor.metrics)}.{synthetic}"
        ),
        input_hash=input_hash,
        payload={"model": predictor.id, "cached": False, "scores": written},
    )


def _reuse_scores(
    session: Session, *, run: Run, version: ModelVersion, input_hash: str
) -> tuple[int, uuid.UUID] | None:
    """Copy an earlier run's scores when the inputs are byte-for-byte identical.

    This is what makes a re-run with one parameter changed re-execute only what
    that parameter affects, and what makes the diff against the previous run
    exact rather than inferred. The copy carries this run's id, so the new rows
    are traceable to this run and to the same model version.
    """
    prior = session.exec(
        select(RunStage)
        .where(
            col(RunStage.input_hash) == input_hash,
            col(RunStage.model_version_id) == version.id,
            col(RunStage.status) == StageStatus.SUCCEEDED,
            col(RunStage.run_id) != run.id,
        )
        .order_by(col(RunStage.created_at).desc())
    ).first()
    if prior is None:
        return None

    source = session.exec(
        select(Score).where(
            col(Score.run_id) == prior.run_id,
            col(Score.model_version_id) == version.id,
        )
    ).all()
    if not source:
        return None

    rows = [
        {
            "id": uuid.uuid4(),
            "created_at": utcnow(),
            "variant_id": score.variant_id,
            "model_version_id": version.id,
            "run_id": run.id,
            "metric": score.metric,
            "value": score.value,
            "uncertainty": score.uncertainty,
            "ci_low": score.ci_low,
            "ci_high": score.ci_high,
        }
        for score in source
    ]
    for chunk in _chunked(rows, 1000):
        session.execute(pg_insert(Score).values(chunk).on_conflict_do_nothing(constraint="uq_score"))
    session.flush()
    return len(rows), prior.run_id


def _write_scores(
    session: Session,
    *,
    run: Run,
    version: ModelVersion,
    values: Sequence[Any],
    state: _State,
) -> int:
    """Turn provider output into `Score` rows, each with its full provenance.

    `ON CONFLICT DO NOTHING` against `uq_score` is what makes the job idempotent:
    a worker that is killed after writing and before committing its stage can be
    replayed without producing a second set of numbers for the same cell.
    """
    rows: list[dict[str, Any]] = []
    for value in values:
        variant_id = state.variant_ids.get(value.variant_code)
        if variant_id is None:
            # A provider returned a code that was not in the candidate set. Not
            # written: a score whose variant is unknown is a number with nothing
            # to attach it to.
            continue
        rows.append(
            {
                "id": uuid.uuid4(),
                "created_at": utcnow(),
                "variant_id": variant_id,
                "model_version_id": version.id,
                "run_id": run.id,
                "metric": value.metric,
                "value": value.value,
                "uncertainty": value.uncertainty,
                "ci_low": value.ci_low,
                "ci_high": value.ci_high,
            }
        )

    for chunk in _chunked(rows, 1000):
        session.execute(pg_insert(Score).values(chunk).on_conflict_do_nothing(constraint="uq_score"))
    session.flush()
    return len(rows)


def _stage_aggregate(session: Session, run: Run, step: PlannedStage, state: _State) -> _Outcome:
    result = _aggregate_run(session, run)
    if not result.rows:
        return _Outcome(
            status=StageStatus.SKIPPED,
            logs=(
                "No predictor produced a score in this run, so there is nothing to "
                "aggregate.\nThe reasons are on the scoring stages above."
            ),
        )

    both = [row for row in result.rows if row.sources_scored > 1]
    spreads = sorted(row.disagreement for row in both if row.disagreement is not None)
    if spreads:
        median = spreads[len(spreads) // 2]
        widest = spreads[-1]
        disagreement = (
            f"Median disagreement {median:.2f}, widest {widest:.2f} "
            "(spread between the predictors' normalised ranks, 0 identical, 1 opposite)."
        )
    else:
        disagreement = (
            "Only one predictor produced values, so there is no disagreement to report. "
            "The consensus column is that predictor's own ranking."
        )

    return _Outcome(
        status=StageStatus.SUCCEEDED,
        logs=(
            f"Combined {len(result.sources)} predictor(s) over {len(result.rows):,} variants.\n"
            "Values are converted to ranks within each predictor before combining — a "
            "ΔΔG in kcal/mol and a log-likelihood ratio are not on the same scale, and "
            "averaging them would produce a number that sorts but means nothing.\n"
            f"{disagreement}\n"
            f"{len(both):,} variants carry more than one opinion; "
            f"{len(result.rows) - len(both):,} carry one."
        ),
        payload={
            "sources": list(result.sources),
            "variants": len(result.rows),
            "multi_source": len(both),
        },
    )


def _stage_filter(session: Session, run: Run, step: PlannedStage, state: _State) -> _Outcome:
    constrained = constraint_service.constrained_positions(session, run.target_id)
    result = _aggregate_run(session, run)
    codes = {row.code for row in result.rows}

    positions = _positions_of(session, run.target_id, codes)
    removed: dict[str, list[str]] = {}
    for code in sorted(codes):
        position = positions.get(code)
        if position is not None and position in constrained:
            removed[code] = sorted(constrained[position])

    override = bool(run.config.get("override_constraints"))
    state.removed = {} if override else removed
    state.kept = len(codes) - len(state.removed)

    if override and removed:
        # Specification §7: never propose mutations at constrained positions
        # without an explicit override, and log the override.
        _record(
            session,
            kind=ProvenanceEventKind.CONSTRAINT_OVERRIDDEN,
            run=run,
            payload={
                "reason": "run configured with override_constraints",
                "positions": {str(k): sorted(v) for k, v in constrained.items()},
                "variants_kept_despite_constraint": sorted(removed),
            },
        )

    # Persisted as an event rather than recomputed on read: editing a constraint
    # tomorrow must not rewrite what this run filtered today.
    _record(
        session,
        kind=ProvenanceEventKind.RUN_STAGE_COMPLETED,
        run=run,
        subject_type="run_filter",
        payload={
            "stage": "filter by constraints",
            "override": override,
            "constrained_positions": {str(k): sorted(v) for k, v in constrained.items()},
            "removed": removed,
            "kept": state.kept,
        },
    )

    if not constrained:
        detail = "No constraints are set on this target, so nothing was filtered."
    elif override:
        detail = (
            f"{len(removed):,} variants sit at constrained positions and were KEPT: this "
            "run was configured to override the constraints. The override is recorded "
            "in the provenance trail."
        )
    else:
        detail = (
            f"Removed {len(removed):,} variants at {len(constrained):,} constrained "
            "positions. Each is retrievable with the constraint that removed it."
        )

    return _Outcome(
        status=StageStatus.SUCCEEDED,
        logs=f"{detail}\n{state.kept:,} variants continue to ranking.",
        payload={"removed": len(removed), "kept": state.kept, "override": override},
    )


def _stage_rank(session: Session, run: Run, step: PlannedStage, state: _State) -> _Outcome:
    limit = run.config.get("max_variants")
    total = state.kept
    if limit is None:
        budget = (
            "No budget was stated, so nothing is truncated — the whole ranking is kept."
        )
    else:
        budget = (
            f"The stated budget of {limit:,} selects the top {min(int(limit), total):,}. "
            "The rest stay ranked and retrievable."
        )
    return _Outcome(
        status=StageStatus.SUCCEEDED,
        logs=(
            f"Ranked {total:,} variants by consensus rank across the predictors that "
            "scored them.\n"
            "Consensus is a mean of normalised ranks, not a physical quantity, and it "
            "is shown beside the per-predictor values rather than in place of them.\n"
            f"{budget}"
        ),
        payload={"ranked": total, "budget": limit},
    )


_IMPLEMENTATIONS: dict[str, Callable[[Session, Run, PlannedStage, _State], _Outcome]] = {
    STAGE_RETRIEVE_STRUCTURE: _stage_retrieve_structure,
    STAGE_BUILD_MSA: _stage_build_msa,
    STAGE_SCORE: _stage_score,
    STAGE_AGGREGATE: _stage_aggregate,
    STAGE_FILTER: _stage_filter,
    STAGE_RANK: _stage_rank,
}


# --------------------------------------------------------------------------- #
# Reading a run back
# --------------------------------------------------------------------------- #


def require_run(session: Session, run_id: uuid.UUID) -> Run:
    run = session.get(Run, run_id)
    if run is None:
        raise ServiceError("That run does not exist.", "Open it from the target page.")
    return run


def _stages_of(session: Session, run_id: uuid.UUID) -> list[RunStage]:
    return list(
        session.exec(
            select(RunStage)
            .where(col(RunStage.run_id) == run_id)
            .order_by(col(RunStage.ordinal))
        ).all()
    )


def stages_of(session: Session, run_id: uuid.UUID) -> list[RunStage]:
    return _stages_of(session, run_id)


def runs_for_target(session: Session, target_id: uuid.UUID) -> list[Run]:
    return list(
        session.exec(
            select(Run)
            .where(col(Run.target_id) == target_id)
            .order_by(col(Run.created_at).desc())
        ).all()
    )


def model_versions_of(session: Session, run_id: uuid.UUID) -> dict[uuid.UUID, ModelVersion]:
    versions = session.exec(
        select(ModelVersion)
        .join(RunStage, col(RunStage.model_version_id) == col(ModelVersion.id))
        .where(col(RunStage.run_id) == run_id)
    ).all()
    return {version.id: version for version in versions}


def cancel(session: Session, *, run_id: uuid.UUID, actor: str | None = None) -> Run:
    """Stop a run. Takes effect at the next stage boundary.

    A stage already executing is allowed to finish and record what it did: it
    happened, and a provenance trail that omits it would be a lie of omission.
    """
    run = require_run(session, run_id)
    if run.status in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED):
        raise ServiceError(
            f"This run has already finished ({run.status.value}).",
            "Start a new run instead.",
        )

    run.status = RunStatus.CANCELLED
    run.finished_at = utcnow()
    session.add(run)
    _cancel_pending_stages(session, run.id)
    _record(
        session,
        kind=ProvenanceEventKind.RUN_CANCELLED,
        run=run,
        actor=actor,
        payload={"cancelled_at": run.finished_at.isoformat() if run.finished_at else None},
    )
    session.commit()
    session.refresh(run)
    return run


# --------------------------------------------------------------------------- #
# Derived results: aggregate, filter, rank
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ScoreCell:
    metric: str
    value: float
    uncertainty: float | None
    ci_low: float | None
    ci_high: float | None
    model_version_id: uuid.UUID
    model_id: str
    is_mock: bool


@dataclass(frozen=True, slots=True)
class AggregateResult:
    sources: tuple[str, ...]
    rows: tuple[ranking_math.Aggregate, ...]
    cells: Mapping[str, tuple[ScoreCell, ...]]
    metrics: tuple[MetricSpec, ...]


def _aggregate_run(session: Session, run: Run) -> AggregateResult:
    """Rebuild the aggregate from this run's stored scores.

    Derived on every read rather than written down. The inputs are persisted and
    the arithmetic is deterministic, so a stored copy could only ever be a second
    answer capable of disagreeing with the first.
    """
    predictors = {predictor.id: predictor for predictor in _resolve_configured(run.config)}
    versions = {
        version.id: version
        for version in session.exec(
            select(ModelVersion)
            .join(Score, col(Score.model_version_id) == col(ModelVersion.id))
            .where(col(Score.run_id) == run.id)
            .distinct()
        ).all()
    }

    codes = dict(
        session.exec(
            select(col(Variant.id), col(Variant.code)).where(
                col(Variant.target_id) == run.target_id
            )
        ).all()
    )

    cells: dict[str, list[ScoreCell]] = {}
    series: dict[str, dict[str, float]] = {}
    for score in session.exec(select(Score).where(col(Score.run_id) == run.id)).all():
        version = versions.get(score.model_version_id)
        code = codes.get(score.variant_id)
        if version is None or code is None:
            continue
        cells.setdefault(code, []).append(
            ScoreCell(
                metric=score.metric,
                value=score.value,
                uncertainty=score.uncertainty,
                ci_low=score.ci_low,
                ci_high=score.ci_high,
                model_version_id=version.id,
                model_id=version.model_id,
                is_mock=version.is_mock,
            )
        )
        series.setdefault(version.model_id, {})[code] = score.value

    metrics: list[MetricSpec] = []
    sources: dict[str, ranking_math.Series] = {}
    for model_id, values in series.items():
        predictor = predictors.get(model_id)
        if predictor is None:
            continue
        metrics.extend(predictor.metrics)
        sources[model_id] = ranking_math.Series(
            values=values, higher_is_better=predictor.metrics[0].higher_is_better
        )

    return AggregateResult(
        sources=tuple(sorted(sources)),
        rows=tuple(ranking_math.aggregate(sources)),
        cells={code: tuple(found) for code, found in cells.items()},
        metrics=tuple(metrics),
    )


def _positions_of(
    session: Session, target_id: uuid.UUID, codes: Iterable[str]
) -> dict[str, int | None]:
    wanted = set(codes)
    if not wanted:
        return {}
    rows = session.exec(
        select(col(Variant.code), col(Variant.position)).where(
            col(Variant.target_id) == target_id, col(Variant.code).in_(wanted)
        )
    ).all()
    return {code: position for code, position in rows}


def filter_record(session: Session, run: Run) -> dict[str, Any]:
    """The constraint filter exactly as this run applied it.

    Read from the provenance event the filter stage wrote, not recomputed from
    today's constraints — a run is a record of what happened, and constraints
    change.
    """
    event = session.exec(
        select(ProvenanceEvent)
        .where(
            col(ProvenanceEvent.run_id) == run.id,
            col(ProvenanceEvent.subject_type) == "run_filter",
        )
        .order_by(col(ProvenanceEvent.created_at).desc())
    ).first()
    if event is None:
        return {"removed": {}, "constrained_positions": {}, "override": False, "kept": 0}
    return dict(event.payload)


@dataclass(frozen=True, slots=True)
class RankedVariant:
    rank: int
    #: Written in the canonical scheme, e.g. `S77A`, never in sequence index.
    code: str
    hgvs: str
    #: The position as the canonical scheme names it.
    label: str
    #: The 1-based sequence index the code resolves to. Present for the structure
    #: viewer and for joins; the interface shows the code, not this.
    sequence_position: int | None
    consensus: float
    disagreement: float | None
    sources_scored: int
    cells: tuple[ScoreCell, ...]
    #: Geometry for this residue, or an empty mapping when it was not measured.
    features: Mapping[str, Any] = field(default_factory=dict)
    #: The constraint kinds that removed this variant, when it was removed.
    #: Empty for everything that survived. Specification §5.3 requires a filtered
    #: variant to stay retrievable with its reason, so it can be asked for here
    #: rather than living only in a separate list.
    filtered_by: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Ranking:
    run_id: uuid.UUID
    scheme_label: str
    metrics: tuple[MetricSpec, ...]
    #: Metric id to the reason it has no values in this run.
    unavailable: Mapping[str, str]
    total_scored: int
    total_filtered: int
    total_ranked: int
    budget: int | None
    is_demo: bool
    rows: tuple[RankedVariant, ...]
    #: Every parameter that produced the geometry columns. Empty when they were
    #: not computed, in which case `features_note` says why.
    features_manifest: Mapping[str, Any] = field(default_factory=dict)
    features_note: str | None = None


def feature_record(session: Session, run: Run) -> dict[str, Any]:
    """This run's derived features, as the run recorded them.

    Read from the append-only event rather than recomputed, so changing a
    project's cutoffs tomorrow cannot restate what a run said today.
    """
    event = session.exec(
        select(ProvenanceEvent)
        .where(
            col(ProvenanceEvent.run_id) == run.id,
            col(ProvenanceEvent.kind) == ProvenanceEventKind.FEATURES_COMPUTED,
        )
        .order_by(col(ProvenanceEvent.created_at).desc())
    ).first()
    if event is None:
        return {}
    return dict(event.payload)


def ranking(
    session: Session,
    *,
    run_id: uuid.UUID,
    limit: int | None = None,
    include_filtered: bool = False,
) -> Ranking:
    """The ranked result of a run: aggregate, filter, rank, in that order.

    `include_filtered` puts the variants a constraint removed back into the
    ranking, each carrying the constraint that removed it. They are never
    included by default — a hard filter that quietly returns its own output is
    not a filter — but they stay retrievable, which the specification requires.
    """
    run = require_run(session, run_id)
    target = require_target(session, run.target_id)
    scheme = canonical_scheme(session, target.id)
    result = _aggregate_run(session, run)
    record = filter_record(session, run)
    removed_by: dict[str, list[str]] = dict(record.get("removed", {}))
    removed = set(removed_by)

    surviving = (
        list(result.rows)
        if include_filtered
        else [row for row in result.rows if row.code not in removed]
    )
    budget = run.config.get("max_variants")
    presented = ranking_math.top(surviving, limit if limit is not None else budget)

    positions = _positions_of(session, target.id, [row.code for row in presented])
    versions = model_versions_of(session, run.id)
    unavailable = _unavailable_metrics(session, run)

    measured = feature_record(session, run)
    by_position: dict[str, dict[str, Any]] = measured.get("positions", {})

    rows = tuple(
        RankedVariant(
            rank=index + 1,
            code=row.code,
            hgvs=hgvs_of(row.code),
            label=label_of(row.code),
            sequence_position=positions.get(row.code),
            consensus=round(row.consensus, 4),
            disagreement=None if row.disagreement is None else round(row.disagreement, 4),
            sources_scored=row.sources_scored,
            cells=result.cells.get(row.code, ()),
            features=by_position.get(str(positions.get(row.code)), {}),
            filtered_by=tuple(removed_by.get(row.code, ())),
        )
        for index, row in enumerate(presented)
    )

    return Ranking(
        run_id=run.id,
        scheme_label=scheme.label if scheme else "",
        metrics=result.metrics,
        unavailable=unavailable,
        total_scored=len(result.rows),
        total_filtered=len(removed),
        total_ranked=len(surviving),
        budget=budget if isinstance(budget, int) else None,
        is_demo=any(version.is_mock for version in versions.values()),
        rows=rows,
        features_manifest=measured.get("manifest", {}),
        features_note=_features_note(session, run, measured),
    )


def _features_note(session: Session, run: Run, measured: Mapping[str, Any]) -> str | None:
    """Why the geometry columns are empty, when they are.

    Taken from the stage that tried, so the explanation on the cell is the same
    sentence the run view shows — not a second one written for the table.
    """
    if measured:
        notes = measured.get("notes") or []
        return "; ".join(str(note) for note in notes) or None

    for stage in _stages_of(session, run.id):
        if stage.name == "retrieve structure":
            for line in (stage.logs or "").splitlines():
                if line.startswith("Geometry not measured:"):
                    return line.removeprefix("Geometry not measured:").strip()
            if stage.status is StageStatus.SKIPPED:
                return (
                    "No structure is attached to this target, so no geometry could "
                    "be measured."
                )
    return None


def _unavailable_metrics(session: Session, run: Run) -> dict[str, str]:
    """Why a column has no numbers, taken from the stage that did not run.

    A cell with no value reads as an em dash carrying this text. It is never an
    imputed number and never a blank that could pass for zero.
    """
    reasons: dict[str, str] = {}
    stages = {stage.model_version_id: stage for stage in _stages_of(session, run.id)}
    for predictor in _resolve_configured(run.config):
        version = session.exec(
            select(ModelVersion).where(
                col(ModelVersion.model_id) == predictor.id,
                col(ModelVersion.version) == predictor.version,
                col(ModelVersion.weights_hash) == predictor.weights_hash,
            )
        ).first()
        stage = stages.get(version.id) if version is not None else None
        if stage is None or stage.status is StageStatus.SUCCEEDED:
            continue
        detail = (stage.logs or "").strip() or f"{predictor.name} did not run."
        for metric in predictor.metrics:
            reasons[metric.id] = detail
    return reasons


# --------------------------------------------------------------------------- #
# Diff against the previous run
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class RunDiff:
    run_id: uuid.UUID
    parent_run_id: uuid.UUID
    config_changes: tuple[dict[str, Any], ...]
    stages: tuple[dict[str, Any], ...]
    scores: dict[str, int]
    entered: tuple[str, ...]
    left: tuple[str, ...]
    moved: tuple[dict[str, Any], ...]


def diff(session: Session, *, run_id: uuid.UUID) -> RunDiff:
    """Compare a run against the run it was derived from.

    Exact rather than inferred: the child records its parent, both runs' scores
    are stored, and the ranking is a deterministic function of them. Nothing here
    is reconstructed from timestamps or from names.
    """
    run = require_run(session, run_id)
    if run.parent_run_id is None:
        raise ServiceError(
            "This run was not derived from another one, so there is nothing to diff.",
            "Use Re-run with a changed parameter to produce a comparable pair.",
        )
    parent = require_run(session, run.parent_run_id)

    changes = [
        {"key": key, "before": parent.config.get(key), "after": run.config.get(key)}
        for key in sorted(set(parent.config) | set(run.config))
        if parent.config.get(key) != run.config.get(key)
    ]

    before_stages = {stage.name: stage for stage in _stages_of(session, parent.id)}
    stage_rows: list[dict[str, Any]] = []
    for stage in _stages_of(session, run.id):
        earlier = before_stages.get(stage.name)
        stage_rows.append(
            {
                "name": stage.name,
                "status_before": earlier.status.value if earlier else None,
                "status_after": stage.status.value,
                "runtime_ms_before": earlier.runtime_ms if earlier else None,
                "runtime_ms_after": stage.runtime_ms,
                # The same input hash means the stage did not need to re-execute.
                "reused": bool(
                    earlier is not None
                    and earlier.input_hash is not None
                    and earlier.input_hash == stage.input_hash
                ),
            }
        )

    before_values = _values_by_cell(session, parent.id)
    after_values = _values_by_cell(session, run.id)
    shared = set(before_values) & set(after_values)
    scores = {
        "unchanged": sum(1 for key in shared if before_values[key] == after_values[key]),
        "changed": sum(1 for key in shared if before_values[key] != after_values[key]),
        "added": len(set(after_values) - set(before_values)),
        "removed": len(set(before_values) - set(after_values)),
    }

    before_rank = {row.code: row.rank for row in ranking(session, run_id=parent.id).rows}
    after_rank = {row.code: row.rank for row in ranking(session, run_id=run.id).rows}
    entered = tuple(sorted(set(after_rank) - set(before_rank)))
    left = tuple(sorted(set(before_rank) - set(after_rank)))
    moved = tuple(
        {"code": code, "before": before_rank[code], "after": after_rank[code]}
        for code in sorted(set(before_rank) & set(after_rank))
        if before_rank[code] != after_rank[code]
    )

    return RunDiff(
        run_id=run.id,
        parent_run_id=parent.id,
        config_changes=tuple(changes),
        stages=tuple(stage_rows),
        scores=scores,
        entered=entered,
        left=left,
        moved=moved,
    )


def _values_by_cell(session: Session, run_id: uuid.UUID) -> dict[tuple[uuid.UUID, str, str], float]:
    versions = {
        version.id: version.model_id
        for version in session.exec(
            select(ModelVersion)
            .join(Score, col(Score.model_version_id) == col(ModelVersion.id))
            .where(col(Score.run_id) == run_id)
            .distinct()
        ).all()
    }
    values: dict[tuple[uuid.UUID, str, str], float] = {}
    for score in session.exec(select(Score).where(col(Score.run_id) == run_id)).all():
        model_id = versions.get(score.model_version_id)
        if model_id is None:
            continue
        values[(score.variant_id, model_id, score.metric)] = score.value
    return values


def _chunked(rows: Sequence[dict[str, Any]], size: int) -> Iterable[Sequence[dict[str, Any]]]:
    for start in range(0, len(rows), size):
        yield rows[start : start + size]
