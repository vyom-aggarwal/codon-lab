"""Design runs over HTTP. No business logic here — see ARCHITECTURE.md §3.

Every number this module returns carries the model version that produced it and
the run it came from, and every absence carries the reason it is absent. Those
two properties are what the run view renders; neither is reconstructed on the
client.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from codonlab import queue, quota
from codonlab.auth import CurrentUser
from codonlab.db import get_session
from codonlab.models import ModelVersion, Run, RunStage, User
from codonlab.ownership import OWNERSHIP
from codonlab.services import runs as service
from codonlab.services.targets import ServiceError

# Ownership is enforced for the whole router rather than per handler: a
# route added later cannot forget to opt in. See codonlab/ownership.py.
router = APIRouter(tags=["runs"], dependencies=[OWNERSHIP])
SessionDep = Annotated[Session, Depends(get_session)]


def _fail(error: Exception, status: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={
            "message": str(error),
            "remedy": getattr(error, "remedy", "Check the input and try again."),
        },
    )


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #


class ModelOut(BaseModel):
    """A model version, exactly as the provenance trail records it."""

    # `model_id` is the column's name in the schema and in the provenance trail.
    # Pydantic reserves the `model_` prefix; the field keeps its real name and the
    # reservation is lifted here rather than renaming a column in the API only.
    model_config = ConfigDict(protected_namespaces=())

    id: uuid.UUID
    model_id: str
    name: str
    version: str
    weights_hash: str
    modality: str
    citation: str
    is_mock: bool

    @classmethod
    def of(cls, version: ModelVersion) -> ModelOut:
        return cls(
            id=version.id,
            model_id=version.model_id,
            name=version.name,
            version=version.version,
            weights_hash=version.weights_hash,
            modality=version.modality.value,
            citation=version.citation,
            is_mock=version.is_mock,
        )


class StageOut(BaseModel):
    id: uuid.UUID
    ordinal: int
    name: str
    status: str
    runtime_ms: int | None
    input_hash: str | None
    logs: str | None
    error: str | None
    model: ModelOut | None

    @classmethod
    def of(cls, stage: RunStage, versions: dict[uuid.UUID, ModelVersion]) -> StageOut:
        version = versions.get(stage.model_version_id) if stage.model_version_id else None
        return cls(
            id=stage.id,
            ordinal=stage.ordinal,
            name=stage.name,
            status=stage.status.value,
            runtime_ms=stage.runtime_ms,
            input_hash=stage.input_hash,
            logs=stage.logs,
            error=stage.error,
            model=ModelOut.of(version) if version else None,
        )


class RunOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    target_id: uuid.UUID
    goal_id: uuid.UUID
    status: str
    config: dict[str, Any]
    input_hash: str
    parent_run_id: uuid.UUID | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    #: True when any model version in this run fabricates its numbers. Read from
    #: the stored ModelVersion rows rather than from configuration, so a run
    #: recorded months ago still says truthfully what produced it.
    is_demo: bool
    #: Terminal runs stop the client polling. Derived here so the interface does
    #: not have to keep its own list of which statuses are final.
    is_terminal: bool
    stages: list[StageOut]


class StartRunIn(BaseModel):
    """Optional overrides. Absent means "use what the objective implies"."""

    predictors: list[str] | None = None
    max_variants: int | None = None
    override_constraints: bool | None = None

    def patch(self) -> dict[str, Any] | None:
        given = {
            key: value
            for key, value in (
                ("predictors", self.predictors),
                ("max_variants", self.max_variants),
                ("override_constraints", self.override_constraints),
            )
            if value is not None
        }
        return given or None


TERMINAL = {"succeeded", "failed", "cancelled"}


def _run_out(session: Session, run: Run) -> RunOut:
    stages = service.stages_of(session, run.id)
    versions = service.model_versions_of(session, run.id)
    return RunOut(
        id=run.id,
        project_id=run.project_id,
        target_id=run.target_id,
        goal_id=run.goal_id,
        status=run.status.value,
        config=dict(run.config),
        input_hash=run.input_hash,
        parent_run_id=run.parent_run_id,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error=run.error,
        is_demo=any(version.is_mock for version in versions.values()),
        is_terminal=run.status.value in TERMINAL,
        stages=[StageOut.of(stage, versions) for stage in stages],
    )


# --------------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------------- #


def _assert_capacity(session: Session, user: User) -> None:
    """Refuse a new run when the caller already holds the worker.

    429, because this is a "come back later" rather than a "you may not": the
    same request succeeds once one of their runs finishes.
    """
    try:
        quota.assert_capacity(session, user=user)
    except quota.QuotaError as error:
        raise HTTPException(
            status_code=429,
            detail={"message": str(error), "remedy": error.remedy},
        ) from error


@router.post("/goals/{goal_id}/runs", response_model=RunOut, status_code=201)
def start_run(
    goal_id: uuid.UUID,
    body: StartRunIn,
    session: SessionDep,
    response: Response,
    user: CurrentUser,
) -> RunOut:
    """Start a design run from a confirmed objective.

    The service calls `goals.require_confirmed` before anything else. This
    endpoint does not repeat that check: a check duplicated on the way in is a
    check that can disagree with the one that matters.

    **Idempotent on the run's content address.** An identical request returns the
    run that already exists, with `200` rather than `201`, so a client that
    retries a lost response — or a user who double-clicks — does not start the
    same work twice. The distinction is in the status code because that is the
    one place a caller can read it without comparing ids.
    """
    _assert_capacity(session, user)
    try:
        run, created = service.create(
            session,
            goal_id=goal_id,
            dispatch=queue.enqueue_run,
            config_patch=body.patch(),
        )
    except ServiceError as error:
        raise _fail(error) from error
    if not created:
        response.status_code = 200
    return _run_out(session, run)


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: uuid.UUID, session: SessionDep) -> RunOut:
    try:
        run = service.require_run(session, run_id)
    except ServiceError as error:
        raise _fail(error, status=404) from error
    return _run_out(session, run)


@router.get("/targets/{target_id}/runs", response_model=list[RunOut])
def list_runs(target_id: uuid.UUID, session: SessionDep) -> list[RunOut]:
    return [_run_out(session, run) for run in service.runs_for_target(session, target_id)]


@router.post("/runs/{run_id}/cancel", response_model=RunOut)
def cancel_run(run_id: uuid.UUID, session: SessionDep) -> RunOut:
    try:
        run = service.cancel(session, run_id=run_id)
    except ServiceError as error:
        raise _fail(error) from error
    return _run_out(session, run)


@router.post("/runs/{run_id}/rerun", response_model=RunOut, status_code=201)
def rerun(
    run_id: uuid.UUID,
    body: StartRunIn,
    session: SessionDep,
    response: Response,
    user: CurrentUser,
) -> RunOut:
    """Re-run with one parameter changed, linked to this run for the diff."""
    _assert_capacity(session, user)
    try:
        run, created = service.rerun(
            session,
            run_id=run_id,
            dispatch=queue.enqueue_run,
            config_patch=body.patch(),
        )
    except ServiceError as error:
        raise _fail(error) from error
    if not created:
        response.status_code = 200
    return _run_out(session, run)


class CellOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    metric: str
    value: float
    uncertainty: float | None
    ci_low: float | None
    ci_high: float | None
    model_version_id: uuid.UUID
    model_id: str
    #: Badges this individual number as synthetic. Per specification §6, every
    #: number a fabricating provider produced is marked, not just the screen.
    is_mock: bool


class MetricOut(BaseModel):
    id: str
    label: str
    unit: str | None
    sign_convention: str
    higher_is_better: bool
    reports_interval: bool


class FeaturesOut(BaseModel):
    """Geometry for one residue. Every field may be null, and null means the
    calculation did not produce it — never zero, never a default."""

    #: How the structure file numbers this residue. The viewer addresses
    #: residues in author numbering; the table shows the canonical scheme.
    author_label: str | None = None
    #: Absolute solvent accessible surface area, square angstroms.
    asa: float | None = None
    #: ASA over the published maximum for this residue type.
    rsa: float | None = None
    #: core / boundary / surface under the cutoffs recorded in the manifest.
    region: str | None = None
    #: True when the residue is exposed in the protein alone and buried once
    #: cofactors are included. The reported RSA is the apo value; this says the
    #: apo value is misleading here.
    buried_by_ligand: bool = False
    rsa_with_ligands: float | None = None
    #: Minimum non-hydrogen atom distance to the user-annotated active site.
    distance_to_active_site: float | None = None


class RankedOut(BaseModel):
    rank: int
    #: Written in the canonical numbering scheme named by `scheme_label`, and
    #: rendered with that label beside it for the life of the project.
    code: str
    hgvs: str
    label: str
    #: The sequence index behind the code. For the structure viewer, not display.
    sequence_position: int | None
    features: FeaturesOut = Field(default_factory=FeaturesOut)
    #: The constraint kinds that removed this variant. Empty for survivors.
    filtered_by: list[str] = Field(default_factory=list)
    #: Mean of the predictors' normalised ranks. Not a physical quantity.
    consensus: float
    #: Spread between them. Null when only one predictor scored this variant —
    #: with one opinion there is nothing to disagree about, and zero would read
    #: as unanimity.
    disagreement: float | None
    sources_scored: int
    cells: list[CellOut]


class RankingOut(BaseModel):
    run_id: uuid.UUID
    #: Rendered beside every mutation code, for the whole life of the project.
    scheme_label: str
    metrics: list[MetricOut]
    #: Metric id to the reason it has no values. The cell reads as an em dash
    #: carrying this text; nothing is imputed.
    unavailable: dict[str, str]
    total_scored: int
    total_filtered: int
    total_ranked: int
    budget: int | None
    is_demo: bool
    rows: list[RankedOut]
    #: Every parameter that produced the geometry columns: the reference table
    #: and its DOI, the radii set, the probe radius, the cutoffs in force, the
    #: coordinate set, and how ligands were handled. Empty when nothing was
    #: measured, in which case `features_note` says why.
    features_manifest: dict[str, Any] = Field(default_factory=dict)
    features_note: str | None = None


@router.get("/runs/{run_id}/ranking", response_model=RankingOut)
def get_ranking(
    run_id: uuid.UUID,
    session: SessionDep,
    limit: Annotated[int | None, Query(ge=1, le=100000)] = None,
    include_filtered: bool = False,
) -> RankingOut:
    try:
        result = service.ranking(
            session, run_id=run_id, limit=limit, include_filtered=include_filtered
        )
    except ServiceError as error:
        raise _fail(error, status=404) from error

    return RankingOut(
        run_id=result.run_id,
        scheme_label=result.scheme_label,
        metrics=[
            MetricOut(
                id=metric.id,
                label=metric.label,
                unit=metric.unit,
                sign_convention=metric.sign_convention,
                higher_is_better=metric.higher_is_better,
                reports_interval=metric.reports_interval,
            )
            for metric in result.metrics
        ],
        unavailable=dict(result.unavailable),
        total_scored=result.total_scored,
        total_filtered=result.total_filtered,
        total_ranked=result.total_ranked,
        budget=result.budget,
        is_demo=result.is_demo,
        features_manifest=dict(result.features_manifest),
        features_note=result.features_note,
        rows=[
            RankedOut(
                rank=row.rank,
                code=row.code,
                hgvs=row.hgvs,
                label=row.label,
                sequence_position=row.sequence_position,
                features=FeaturesOut(**dict(row.features)),
                filtered_by=list(row.filtered_by),
                consensus=row.consensus,
                disagreement=row.disagreement,
                sources_scored=row.sources_scored,
                cells=[
                    CellOut(
                        metric=cell.metric,
                        value=cell.value,
                        uncertainty=cell.uncertainty,
                        ci_low=cell.ci_low,
                        ci_high=cell.ci_high,
                        model_version_id=cell.model_version_id,
                        model_id=cell.model_id,
                        is_mock=cell.is_mock,
                    )
                    for cell in row.cells
                ],
            )
            for row in result.rows
        ],
    )


class FilteredOut(BaseModel):
    """Variants a constraint removed, with the constraint that removed them.

    Specification §5.3: every filtered-out variant is retrievable with the reason
    shown. Read from the provenance event the filter stage wrote, so editing a
    constraint today does not rewrite what a run did last week.
    """

    run_id: uuid.UUID
    override: bool
    kept: int
    removed: dict[str, list[str]]
    constrained_positions: dict[str, list[str]]


@router.get("/runs/{run_id}/filtered", response_model=FilteredOut)
def get_filtered(run_id: uuid.UUID, session: SessionDep) -> FilteredOut:
    try:
        run = service.require_run(session, run_id)
    except ServiceError as error:
        raise _fail(error, status=404) from error

    record = service.filter_record(session, run)
    return FilteredOut(
        run_id=run.id,
        override=bool(record.get("override", False)),
        kept=int(record.get("kept", 0)),
        removed=dict(record.get("removed", {})),
        constrained_positions=dict(record.get("constrained_positions", {})),
    )


class ConfigChangeOut(BaseModel):
    key: str
    before: Any = None
    after: Any = None


class StageDiffOut(BaseModel):
    name: str
    status_before: str | None
    status_after: str
    runtime_ms_before: int | None
    runtime_ms_after: int | None
    #: True when the stage's inputs hashed identically, so it did not re-execute.
    reused: bool


class RankMoveOut(BaseModel):
    code: str
    before: int
    after: int


class DiffOut(BaseModel):
    run_id: uuid.UUID
    parent_run_id: uuid.UUID
    config_changes: list[ConfigChangeOut]
    stages: list[StageDiffOut]
    scores: dict[str, int]
    entered: list[str]
    left: list[str]
    moved: list[RankMoveOut]


@router.get("/runs/{run_id}/diff", response_model=DiffOut)
def get_diff(run_id: uuid.UUID, session: SessionDep) -> DiffOut:
    """Compare a run against the run it was derived from."""
    try:
        result = service.diff(session, run_id=run_id)
    except ServiceError as error:
        raise _fail(error) from error

    return DiffOut(
        run_id=result.run_id,
        parent_run_id=result.parent_run_id,
        config_changes=[ConfigChangeOut(**change) for change in result.config_changes],
        stages=[StageDiffOut(**stage) for stage in result.stages],
        scores=result.scores,
        entered=list(result.entered),
        left=list(result.left),
        moved=[RankMoveOut(**move) for move in result.moved],
    )


class QueueOut(BaseModel):
    """Why a run is not moving, when it is not moving.

    A queued run that never starts has exactly two causes and neither is visible
    from the run itself, so the interface reads them from here and says which
    instead of showing a spinner that means nothing.
    """

    connected: bool
    workers: int
    queued: int
    detail: str | None = Field(default=None)


@router.get("/queue", response_model=QueueOut)
def get_queue_status() -> QueueOut:
    status = queue.status()
    return QueueOut(
        connected=status.connected,
        workers=status.workers,
        queued=status.queued,
        detail=status.detail,
    )
