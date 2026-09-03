"""Results intake and the scorecard over HTTP. No business logic — ARCHITECTURE.md §3.

Two shapes in this module are deliberate and worth naming.

**Preview and import are separate endpoints.** A column mapping is a guess about
someone else's spreadsheet; previewing it costs nothing and writes nothing, and
importing without previewing is possible but is the client's explicit choice.
Same confirmation shape as the goal composer.

**A scorecard response can never carry a rank statistic on its own.** `mae` and
`mean_signed_error` are always present as fields, and when they are null
`error_unavailable_reason` is non-empty. There is no response shape in which a
client receives a Spearman coefficient and nothing telling it whether the
absolute error was knowable — ARCHITECTURE.md §13.
"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session

from codonlab.db import get_session
from codonlab.models.enums import AssayKind
from codonlab.services import measurements as service
from codonlab.services.targets import ServiceError

router = APIRouter(tags=["measurements"])
SessionDep = Annotated[Session, Depends(get_session)]


def _flat(record: object) -> dict[str, Any]:
    """A dataclass's own fields, one level deep.

    The service's views are `slots=True` dataclasses and so have no
    `__dict__` for `vars()` to read. `dataclasses.asdict` would work but
    recurses into nested dataclasses and tuples, which this module wants to
    convert deliberately rather than automatically.
    """
    return {field.name: getattr(record, field.name) for field in dataclasses.fields(record)}  # type: ignore[arg-type]


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


class ColumnMappingIn(BaseModel):
    label: str
    value: str
    sd: str | None = None
    replicate: str | None = None

    def to_domain(self) -> service.ColumnMapping:
        return service.ColumnMapping(
            label=self.label, value=self.value, sd=self.sd, replicate=self.replicate
        )


class InspectIn(BaseModel):
    text: str


class ColumnOut(BaseModel):
    name: str
    #: The first few non-empty values, so a header called `col_4` is still
    #: identifiable by what is under it.
    sample: list[str]


class InspectOut(BaseModel):
    headers: list[str]
    #: `,` or `\t`. Shown because a file split on the wrong character produces
    #: one enormous column, which is otherwise puzzling rather than obvious.
    delimiter: str
    row_count: int
    columns: list[ColumnOut]
    #: A pre-selection for the mapping dropdowns, or null when nothing in the
    #: headers looked like a mutation code and a value. Never a blind guess at
    #: the first two columns.
    suggested: ColumnMappingIn | None


class PreviewIn(BaseModel):
    text: str
    mapping: ColumnMappingIn
    #: A numbering shift the user has accepted. Null on the first preview.
    offset: int | None = None


class PreviewRowOut(BaseModel):
    index: int
    raw_label: str
    value: float
    sd: float | None
    replicate: int | None
    outcome: str
    code: str | None
    hgvs: str | None
    detail: str


class ShiftedRowOut(BaseModel):
    index: int
    raw_label: str
    code: str


class OffsetOut(BaseModel):
    offset: int
    witnesses: int
    would_join: list[ShiftedRowOut]
    #: Rows the shift explains but which still have no variant. Present so the
    #: proposal cannot overstate what accepting it repairs.
    explained_without_variant: list[ShiftedRowOut]


class RowProblemOut(BaseModel):
    index: int
    detail: str


class PreviewOut(BaseModel):
    scheme_label: str
    delimiter: str
    headers: list[str]
    rows: list[PreviewRowOut]
    total_rows: int
    joined: int
    unjoined: int
    problems: list[RowProblemOut]
    outcome_counts: dict[str, int]
    offset: OffsetOut | None
    #: Why no shift is offered, when none is. Never blank alongside a null
    #: `offset`: "we found nothing" and "we did not look" are different answers.
    offset_note: str
    #: Variant rows this target holds that are written in a numbering scheme it
    #: no longer treats as canonical, and which are therefore not joinable.
    stale_variants: int


class ImportIn(BaseModel):
    text: str
    mapping: ColumnMappingIn
    assay: AssayKind
    metric: str
    unit: str
    #: Required, with no default. Which direction is a better result is a fact
    #: about the assay that only the person who ran it knows, and every rank
    #: statistic on the scorecard needs it. Defaulting it would be inventing a
    #: sign convention.
    higher_is_better: bool
    offset: int | None = None
    overrides: dict[int, str | None] = Field(default_factory=dict)
    protocol: str | None = None
    performed_on: date | None = None
    operator: str | None = None
    source_note: str | None = None


class ImportOut(BaseModel):
    experiment_id: uuid.UUID
    written: int
    joined: int
    unjoined: int
    problems: list[RowProblemOut]


class PointOut(BaseModel):
    #: Identity. `code` is not unique across a pooled card.
    variant_id: uuid.UUID
    code: str
    hgvs: str
    predicted: float
    measured: float
    replicates: int


class ScorecardOut(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_id: str
    model_name: str
    model_version: str
    weights_hash: str
    model_version_id: uuid.UUID
    is_mock: bool
    predicted_metric: str
    predicted_unit: str
    predicted_sign: str
    measured_metric: str
    measured_unit: str
    measured_sign: str
    n: int
    #: Oriented so +1 means the predictor and the bench agree about quality.
    spearman: float | None
    precision_k: int
    precision: float | None
    precision_note: str
    #: Null exactly when `error_unavailable_reason` is non-empty.
    mae: float | None
    mean_signed_error: float | None
    error_unit: str | None
    bias_note: str
    error_unavailable_reason: str
    calibration: list[dict[str, float]]
    points: list[PointOut]
    targets: list[str]
    #: Distinct target rows behind this card. Exceeds `len(targets)` when
    #: several targets share a name.
    target_count: int


class ScorecardReportOut(BaseModel):
    cards: list[ScorecardOut]
    note: str
    measured_variants: int
    unjoined_measurements: int
    metrics: list[str]
    is_demo: bool


class ExperimentOut(BaseModel):
    id: uuid.UUID
    assay: str
    metric: str
    unit: str
    higher_is_better: bool | None
    source_note: str | None
    protocol: str | None
    operator: str | None
    performed_on: date | None
    total: int
    joined: int
    unjoined: int


class AttachIn(BaseModel):
    #: Null detaches the measurement, leaving it deliberately unjoined.
    code: str | None = None


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #


@router.post("/targets/{target_id}/measurements/inspect", response_model=InspectOut)
def inspect(target_id: uuid.UUID, body: InspectIn) -> InspectOut:
    """Read the headers out of a pasted or uploaded table.

    Writes nothing and does not touch the target; the path is target-scoped so
    the client has one place to send a file.
    """
    try:
        table = service.parse_table(body.text)
    except ServiceError as error:
        raise _fail(error) from error

    columns: list[ColumnOut] = []
    for index, header in enumerate(table.headers):
        sample = [
            row[index].strip()
            for row in table.rows[:5]
            if index < len(row) and row[index].strip()
        ]
        columns.append(ColumnOut(name=header, sample=sample))

    suggested = service.suggest_mapping(table)
    return InspectOut(
        headers=list(table.headers),
        delimiter=table.delimiter,
        row_count=len(table.rows),
        columns=columns,
        suggested=(
            ColumnMappingIn(
                label=suggested.label,
                value=suggested.value,
                sd=suggested.sd,
                replicate=suggested.replicate,
            )
            if suggested
            else None
        ),
    )


@router.post("/targets/{target_id}/measurements/preview", response_model=PreviewOut)
def preview(target_id: uuid.UUID, body: PreviewIn, session: SessionDep) -> PreviewOut:
    """What this import would do. Writes nothing."""
    try:
        result = service.preview(
            session,
            target_id=target_id,
            text=body.text,
            mapping=body.mapping.to_domain(),
            offset=body.offset,
        )
    except ServiceError as error:
        raise _fail(error) from error

    offset: OffsetOut | None = None
    if result.offset is not None:
        payload: dict[str, Any] = dict(result.offset)
        offset = OffsetOut(
            offset=int(payload["offset"]),
            witnesses=int(payload["witnesses"]),
            would_join=[ShiftedRowOut(**row) for row in payload["would_join"]],
            explained_without_variant=[
                ShiftedRowOut(**row) for row in payload["explained_without_variant"]
            ],
        )

    return PreviewOut(
        scheme_label=result.scheme_label,
        delimiter=result.delimiter,
        headers=list(result.headers),
        rows=[PreviewRowOut(**_flat(row)) for row in result.rows],
        total_rows=result.total_rows,
        joined=result.joined,
        unjoined=result.unjoined,
        problems=[RowProblemOut(**_flat(problem)) for problem in result.problems],
        outcome_counts=dict(result.outcome_counts),
        offset=offset,
        offset_note=result.offset_note,
        stale_variants=result.stale_variants,
    )


@router.post("/targets/{target_id}/measurements", response_model=ImportOut, status_code=201)
def create(target_id: uuid.UUID, body: ImportIn, session: SessionDep) -> ImportOut:
    try:
        result = service.import_measurements(
            session,
            target_id=target_id,
            text=body.text,
            mapping=body.mapping.to_domain(),
            assay=body.assay,
            metric=body.metric,
            unit=body.unit,
            higher_is_better=body.higher_is_better,
            offset=body.offset,
            overrides=body.overrides,
            protocol=body.protocol,
            performed_on=body.performed_on,
            operator=body.operator,
            source_note=body.source_note,
        )
    except ServiceError as error:
        raise _fail(error) from error

    return ImportOut(
        experiment_id=result.experiment_id,
        written=result.written,
        joined=result.joined,
        unjoined=result.unjoined,
        problems=[RowProblemOut(**_flat(problem)) for problem in result.problems],
    )


@router.get("/projects/{project_id}/experiments", response_model=list[ExperimentOut])
def experiments(project_id: uuid.UUID, session: SessionDep) -> list[ExperimentOut]:
    try:
        found = service.experiments_for(session, project_id=project_id)
    except ServiceError as error:
        raise _fail(error, status=404) from error
    return [ExperimentOut(**_flat(view)) for view in found]


@router.get("/experiments/{experiment_id}/unjoined", response_model=list[PreviewRowOut])
def unjoined(experiment_id: uuid.UUID, session: SessionDep) -> list[PreviewRowOut]:
    """The rows of one import that never found a variant.

    They exist as stored measurements, not as a rejected-file report — which is
    the difference between a row the user can resolve and one they must
    re-upload.
    """
    rows = service.unjoined_rows(session, experiment_id=experiment_id)
    return [PreviewRowOut(**_flat(row)) for row in rows]


@router.post("/measurements/{measurement_id}/variant", response_model=dict)
def attach(
    measurement_id: uuid.UUID, body: AttachIn, session: SessionDep
) -> dict[str, Any]:
    """Point a stored measurement at a variant by hand, or detach it."""
    try:
        measurement = service.attach_variant(
            session, measurement_id=measurement_id, code=body.code
        )
    except ServiceError as error:
        raise _fail(error) from error
    return {
        "id": str(measurement.id),
        "variant_id": str(measurement.variant_id) if measurement.variant_id else None,
        "raw_label": measurement.raw_label,
    }


@router.get("/targets/{target_id}/scorecard", response_model=ScorecardReportOut)
def target_scorecard(
    target_id: uuid.UUID,
    session: SessionDep,
    k: Annotated[int, Query(ge=1, le=1000)] = service.DEFAULT_PRECISION_K,
) -> ScorecardReportOut:
    try:
        report = service.scorecards(session, target_id=target_id, k=k)
    except ServiceError as error:
        raise _fail(error, status=404) from error
    return _report_out(report)


@router.get("/scorecard", response_model=ScorecardReportOut)
def lab_scorecard(
    session: SessionDep,
    k: Annotated[int, Query(ge=1, le=1000)] = service.DEFAULT_PRECISION_K,
) -> ScorecardReportOut:
    """The persistent scorecard, pooled across every target the lab has measured.

    Specification §5.9's "accumulates across the lab's projects". Pooling is over
    the underlying pairs, not over finished cards — see
    `domain/scorecard.accumulate`, which refuses the averaging shortcut by name.
    """
    return _report_out(service.scorecards(session, target_id=None, k=k))


def _report_out(report: service.ScorecardReport) -> ScorecardReportOut:
    return ScorecardReportOut(
        cards=[
            ScorecardOut(
                **{
                    key: value
                    for key, value in _flat(card).items()
                    if key not in {"calibration", "points", "measured_without_prediction"}
                },
                calibration=[dict(entry) for entry in card.calibration],
                points=[PointOut(**_flat(point)) for point in card.points],
            )
            for card in report.cards
        ],
        note=report.note,
        measured_variants=report.measured_variants,
        unjoined_measurements=report.unjoined_measurements,
        metrics=list(report.metrics),
        is_demo=report.is_demo,
    )
