"""Results intake and the scorecard: the half of the product that keeps it honest.

Specification §5.9 and §2.3 — "the validation loop… no competitor does this. It
is the entire moat." This service is the orchestration; the two rules that
matter are pure and live in `domain/joining` and `domain/scorecard`, so both are
testable without a database.

Four things here are load-bearing.

**Every uploaded row is written, joined or not.** `Measurement.variant_id` is
nullable for exactly this reason. A row that could not be matched to a variant
is stored with its `raw_label` intact and shown in the join review, because a
row silently dropped at import is a measurement the lab paid for and the product
threw away.

**The import is previewed before it is committed.** Same shape as the goal
composer's confirmation gate: the parse is shown back, the user confirms, and
only then does anything get written. A column mapping is a guess about someone
else's spreadsheet, and guessing wrong writes a column of replicate numbers into
a column of measured values.

**Predictions and measurements are paired per variant, not per row.** A variant
measured three times contributes one point, at the mean of its replicates, so a
well-replicated variant does not outvote the rest of the plate in the MAE. The
replicate count travels with the pair.

**A scorecard is keyed on a model *version*, never on a model id.** Two weight
hashes are two different predictors as far as a provenance trail is concerned,
and a card pooling them would be a card about neither.
"""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

from sqlmodel import Session, col, select

from codonlab.domain import joining
from codonlab.domain import scorecard as scorecard_math
from codonlab.domain.mutation import MutationParseError, parse_mutation_set
from codonlab.domain.variants import hgvs_of
from codonlab.models import (
    Experiment,
    Measurement,
    ModelVersion,
    NumberingScheme,
    ProvenanceEvent,
    ProvenanceEventKind,
    Run,
    Score,
    Target,
    Variant,
)
from codonlab.models.enums import AssayKind
from codonlab.providers import REGISTRY, MetricSpec
from codonlab.services.targets import (
    ServiceError,
    canonical_scheme,
    labels_of,
    require_project,
    require_target,
)

#: How many mapped rows the preview renders. An interface bound, not a
#: scientific one — the join and the offset proposal are always computed over
#: the whole file, because a proposal derived from the first twenty rows would
#: be a claim about the file that the file had not made.
PREVIEW_ROWS = 25

#: The default k for precision@k, from specification §5.9 ("precision@10").
#: Named rather than inlined so the one place it is chosen is greppable.
DEFAULT_PRECISION_K = 10


# --------------------------------------------------------------------------- #
# Reading the file
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Table:
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    #: The delimiter that was detected, named so the preview can show it. A
    #: file split on the wrong character produces one enormous column, and
    #: saying which character was used makes that diagnosable at a glance.
    delimiter: str


def parse_table(text: str) -> Table:
    """Read pasted or uploaded text into headers and rows.

    Handles comma and tab separation, which covers a CSV export and a paste
    straight out of a plate reader or a spreadsheet. The delimiter is sniffed
    from the header line and reported, never assumed silently.

    Ragged rows are padded rather than rejected: a trailing empty cell is the
    single most common thing wrong with a real export, and refusing the whole
    file over it would send the user back to Excel for no reason. A row with
    *more* cells than the header is kept whole so nothing is lost, and the
    mapping simply cannot reach the extra cells.
    """
    stripped = text.strip()
    if not stripped:
        raise ServiceError(
            "That file has no rows.",
            "Paste the measured values, or choose a file with a header row.",
        )

    first = stripped.splitlines()[0]
    delimiter = "\t" if first.count("\t") > first.count(",") else ","

    reader = csv.reader(io.StringIO(stripped), delimiter=delimiter)
    records = [row for row in reader if any(cell.strip() for cell in row)]
    if not records:
        raise ServiceError(
            "That file has no rows.",
            "Paste the measured values, or choose a file with a header row.",
        )

    headers = tuple(cell.strip() for cell in records[0])
    if len(headers) < 2:
        raise ServiceError(
            f"Only one column was found, splitting on {'tab' if delimiter else 'comma'}.",
            "Check the file is comma- or tab-separated and has a header row.",
        )

    width = len(headers)
    body = tuple(
        tuple(row) + ("",) * (width - len(row)) if len(row) < width else tuple(row)
        for row in records[1:]
    )
    return Table(headers=headers, rows=body, delimiter=delimiter)


@dataclass(frozen=True, slots=True)
class ColumnMapping:
    """Which column holds what. Every field is a header name from the file.

    ``label`` and ``value`` are required; a measurement with no variant to
    attach to and no number is not a measurement.
    """

    label: str
    value: str
    sd: str | None = None
    replicate: str | None = None


#: Header names that commonly hold a mutation code or a measured value. Used
#: only to pre-select the dropdowns in the mapping UI, which the user then
#: confirms — the same "parse, then confirm" shape as the goal composer. A
#: wrong suggestion costs one click; it can never be committed unseen.
_LABEL_HINTS = ("mutant", "mutation", "variant", "substitution", "code", "aa_change")
_VALUE_HINTS = ("value", "score", "dms_score", "measured", "tm", "t50", "activity", "yield")
_SD_HINTS = ("sd", "stdev", "std", "error", "sem", "deviation")
_REPLICATE_HINTS = ("replicate", "rep", "well", "trial")


def _suggest(headers: Sequence[str], hints: Sequence[str]) -> str | None:
    lowered = {header: header.strip().lower() for header in headers}
    for hint in hints:
        for header, name in lowered.items():
            if name == hint:
                return header
    for hint in hints:
        for header, name in lowered.items():
            if hint in name:
                return header
    return None


def suggest_mapping(table: Table) -> ColumnMapping | None:
    """A starting point for the mapping UI, or None when nothing looks right.

    Returning None rather than a guess at column 0 and column 1 is deliberate:
    an arbitrary pre-selection that happens to be wrong is harder to notice than
    an empty dropdown that asks.
    """
    label = _suggest(table.headers, _LABEL_HINTS)
    value = _suggest(table.headers, _VALUE_HINTS)
    if label is None or value is None:
        return None
    sd = _suggest(table.headers, _SD_HINTS)
    replicate = _suggest(table.headers, _REPLICATE_HINTS)
    return ColumnMapping(
        label=label,
        value=value,
        sd=sd if sd not in (label, value) else None,
        replicate=replicate if replicate not in (label, value, sd) else None,
    )


@dataclass(frozen=True, slots=True)
class RowProblem:
    index: int
    detail: str


def apply_mapping(
    table: Table, mapping: ColumnMapping
) -> tuple[list[joining.UploadedRow], list[RowProblem]]:
    """Turn the raw grid into rows the join can read.

    A row whose value cell is not a number is **not** silently skipped and not
    coerced to zero — it is returned as a problem, counted in the preview, and
    reported at import. `NaN` and `inf` are refused for the same reason
    `domain/hashing` refuses them: they propagate through arithmetic and produce
    a scorecard that is quietly meaningless.
    """
    positions = {header: index for index, header in enumerate(table.headers)}
    for name in (mapping.label, mapping.value):
        if name not in positions:
            raise ServiceError(
                f"This file has no column called {name!r}.",
                "Choose one of the file's own columns for every mapped field.",
            )

    label_at = positions[mapping.label]
    value_at = positions[mapping.value]
    sd_at = positions.get(mapping.sd) if mapping.sd else None
    replicate_at = positions.get(mapping.replicate) if mapping.replicate else None

    rows: list[joining.UploadedRow] = []
    problems: list[RowProblem] = []

    for number, record in enumerate(table.rows, start=1):

        def cell(index: int | None, row: tuple[str, ...] = record) -> str:
            return row[index].strip() if index is not None and index < len(row) else ""

        raw_label = cell(label_at)
        raw_value = cell(value_at)
        if not raw_label and not raw_value:
            continue
        if not raw_label:
            problems.append(RowProblem(index=number, detail="No mutation code in this row."))
            continue

        try:
            value = float(raw_value)
        except ValueError:
            problems.append(
                RowProblem(
                    index=number,
                    detail=f"{raw_value!r} in {mapping.value!r} is not a number.",
                )
            )
            continue
        if value != value or value in (float("inf"), float("-inf")):
            problems.append(
                RowProblem(index=number, detail=f"{raw_value!r} is not a finite number.")
            )
            continue

        sd: float | None = None
        if sd_at is not None and cell(sd_at):
            try:
                sd = float(cell(sd_at))
            except ValueError:
                problems.append(
                    RowProblem(
                        index=number,
                        detail=f"{cell(sd_at)!r} in {mapping.sd!r} is not a number.",
                    )
                )
                continue

        replicate: int | None = None
        if replicate_at is not None and cell(replicate_at):
            try:
                replicate = int(float(cell(replicate_at)))
            except ValueError:
                replicate = None

        rows.append(
            joining.UploadedRow(
                index=number,
                raw_label=raw_label,
                value=value,
                sd=sd,
                replicate=replicate,
            )
        )

    return rows, problems


# --------------------------------------------------------------------------- #
# Previewing an import
# --------------------------------------------------------------------------- #


def _canonical_residues(target: Target, scheme: NumberingScheme) -> dict[str, str]:
    """The wild-type residue the canonical scheme has at each of its labels."""
    residues: dict[str, str] = {}
    for index, label in enumerate(labels_of(scheme), start=1):
        if label is not None and index <= len(target.sequence):
            residues[label] = target.sequence[index - 1].upper()
    return residues


def _known_variants(
    session: Session, target: Target, canonical: Mapping[str, str]
) -> tuple[list[joining.KnownVariant], int]:
    """Every variant on this target that is written in its *current* canonical scheme.

    Target-scoped rather than run-scoped on purpose: a variant is the same
    variant whoever proposed it (migration 0004), so a lab that measured
    something an earlier run ranked still joins to one row.

    **Variants whose wild-type residue disagrees with the canonical scheme at
    their label are excluded**, and this is the important part. A target that
    was reconciled to a new canonical scheme keeps the variant rows an earlier
    scheme produced — they have scores hanging off them, so nothing deletes
    them — and those rows name residues the current scheme does not agree
    with. On the seeded lipase, `S108A` is such a row: under the confirmed
    mature-protein scheme, label 108 is L, and the substitution that row means
    is called `S77A` today.

    Joining an uploaded `S108A` to that stale row would file a bench
    measurement against a residue 31 positions from the one it was made on —
    the single most expensive error class in this application (HANDOFF.md §8),
    arriving through the join rather than through enumeration. The count of
    excluded rows is returned so the exclusion is reportable rather than
    silent.
    """
    rows = session.exec(select(Variant).where(col(Variant.target_id) == target.id)).all()
    known: list[joining.KnownVariant] = []
    excluded = 0

    for variant in rows:
        try:
            parsed = parse_mutation_set(variant.code)
        except MutationParseError:
            excluded += 1
            continue

        if any(canonical.get(part.label) != part.wild for part in parsed):
            excluded += 1
            continue

        if len(parsed) != 1:
            # A stacked design joins by its whole canonical code, which `code`
            # already holds; a single wild/label/mutant is meaningless for it.
            known.append(
                joining.KnownVariant(
                    code=variant.code,
                    wild="",
                    label="",
                    mutant="",
                    sequence_position=variant.position,
                )
            )
            continue

        only = parsed[0]
        known.append(
            joining.KnownVariant(
                code=variant.code,
                wild=only.wild,
                label=only.label,
                mutant=only.mutant,
                sequence_position=variant.position,
            )
        )
    return known, excluded


@dataclass(frozen=True, slots=True)
class PreviewRow:
    index: int
    raw_label: str
    value: float
    sd: float | None
    replicate: int | None
    outcome: str
    code: str | None
    hgvs: str | None
    detail: str


@dataclass(frozen=True, slots=True)
class Preview:
    scheme_label: str
    delimiter: str
    headers: tuple[str, ...]
    #: The first `PREVIEW_ROWS` mapped rows, with their join outcome.
    rows: tuple[PreviewRow, ...]
    total_rows: int
    joined: int
    unjoined: int
    problems: tuple[RowProblem, ...]
    #: Counts by outcome across the whole file, so the summary describes the
    #: file rather than the twenty-five rows that happen to be on screen.
    outcome_counts: Mapping[str, int]
    offset: Mapping[str, object] | None
    offset_note: str
    #: Variant rows this target still holds that are written in a numbering
    #: scheme it no longer treats as canonical, and which are therefore not
    #: joinable. Reported rather than silently filtered.
    stale_variants: int = 0


def _preview_rows(result: joining.JoinResult) -> tuple[PreviewRow, ...]:
    out: list[PreviewRow] = []
    for entry in result.rows[:PREVIEW_ROWS]:
        out.append(
            PreviewRow(
                index=entry.row.index,
                raw_label=entry.row.raw_label,
                value=entry.row.value,
                sd=entry.row.sd,
                replicate=entry.row.replicate,
                outcome=str(entry.outcome),
                code=entry.code,
                hgvs=hgvs_of(entry.code) if entry.code else None,
                detail=entry.detail,
            )
        )
    return tuple(out)


def _offset_payload(proposal: joining.OffsetProposal | None) -> Mapping[str, object] | None:
    if proposal is None:
        return None
    return {
        "offset": proposal.offset,
        "witnesses": proposal.witnesses,
        "would_join": [
            {"index": row.index, "raw_label": row.raw_label, "code": row.code}
            for row in proposal.would_join
        ],
        "explained_without_variant": [
            {"index": row.index, "raw_label": row.raw_label, "code": row.code}
            for row in proposal.explained_without_variant
        ],
    }


@dataclass(frozen=True, slots=True)
class _Joined:
    result: joining.JoinResult
    scheme_label: str
    known: list[joining.KnownVariant]
    #: Variant rows excluded because they are written in a numbering scheme this
    #: target no longer treats as canonical. See `_known_variants`.
    stale_variants: int


def _join_for(
    session: Session,
    target: Target,
    rows: Sequence[joining.UploadedRow],
    *,
    offset: int | None,
) -> _Joined:
    scheme = canonical_scheme(session, target.id)
    if scheme is None:
        raise ServiceError(
            "This target has no canonical numbering scheme.",
            "Reconcile its numbering first — until then no mutation code on it is "
            "unambiguous, so nothing can be joined to it.",
        )
    canonical = _canonical_residues(target, scheme)
    known, stale = _known_variants(session, target, canonical)
    if not known:
        raise ServiceError(
            "This target has no variants written in its canonical numbering scheme.",
            "Complete a design run first, so there is something to join measurements to.",
        )
    result = joining.join(rows, known, scheme_label=scheme.label)
    if offset is not None:
        result = joining.apply_offset(result, known, offset=offset, scheme_label=scheme.label)
    return _Joined(
        result=result, scheme_label=scheme.label, known=known, stale_variants=stale
    )


def preview(
    session: Session,
    *,
    target_id: uuid.UUID,
    text: str,
    mapping: ColumnMapping,
    offset: int | None = None,
) -> Preview:
    """Show what this import would do, without writing anything."""
    target = require_target(session, target_id)
    table = parse_table(text)
    rows, problems = apply_mapping(table, mapping)
    joined = _join_for(session, target, rows, offset=offset)
    result = joined.result

    counts: dict[str, int] = {}
    for entry in result.rows:
        key = str(entry.outcome)
        counts[key] = counts.get(key, 0) + 1

    return Preview(
        scheme_label=joined.scheme_label,
        delimiter=table.delimiter,
        headers=table.headers,
        rows=_preview_rows(result),
        total_rows=len(result.rows),
        joined=result.joined_count,
        unjoined=result.unjoined_count,
        problems=tuple(problems),
        outcome_counts=counts,
        offset=_offset_payload(result.proposal),
        offset_note=result.proposal_note,
        stale_variants=joined.stale_variants,
    )


# --------------------------------------------------------------------------- #
# Committing an import
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ImportResult:
    experiment_id: uuid.UUID
    written: int
    joined: int
    unjoined: int
    problems: tuple[RowProblem, ...]


def import_measurements(
    session: Session,
    *,
    target_id: uuid.UUID,
    text: str,
    mapping: ColumnMapping,
    assay: AssayKind,
    metric: str,
    unit: str,
    higher_is_better: bool,
    offset: int | None = None,
    overrides: Mapping[int, str | None] | None = None,
    protocol: str | None = None,
    performed_on: date | None = None,
    operator: str | None = None,
    source_note: str | None = None,
) -> ImportResult:
    """Write an experiment and one measurement per uploaded row.

    ``higher_is_better`` is required rather than defaulted. It is a fact about
    the assay that only the person who ran it knows, and every rank statistic on
    the scorecard needs it; inferring it from the metric's name would be
    inventing a sign convention.

    ``overrides`` maps a row index to the canonical code it should be attached
    to, or to None to leave it deliberately unjoined. Specification §5.9
    requires manual override, and an override to a code this target does not
    have is refused rather than written against nothing.
    """
    target = require_target(session, target_id)
    project = require_project(session, target.project_id)

    if not metric.strip():
        raise ServiceError("This import has no metric name.", "Name what was measured, e.g. 'T50'.")
    if not unit.strip():
        raise ServiceError(
            "This import has no unit.",
            "State the unit, e.g. '°C'. The scorecard refuses to compare unlike units, "
            "so it needs to know what this one is.",
        )

    table = parse_table(text)
    rows, problems = apply_mapping(table, mapping)
    joined = _join_for(session, target, rows, offset=offset)
    result = joined.result

    if overrides:
        codes = [variant.code for variant in joined.known]
        for row_index, code in overrides.items():
            try:
                result = joining.resolve_manually(
                    result, row_index=row_index, code=code, known_codes=codes
                )
            except ValueError as error:
                raise ServiceError(
                    str(error),
                    "Override with a mutation code this target actually has.",
                ) from error

    by_code = {
        variant.code: variant.id
        for variant in session.exec(
            select(Variant).where(col(Variant.target_id) == target.id)
        ).all()
    }

    experiment = Experiment(
        project_id=project.id,
        assay=assay,
        protocol=protocol,
        performed_on=performed_on,
        operator=operator,
        higher_is_better=higher_is_better,
        source_note=source_note,
    )
    session.add(experiment)
    session.flush()

    for entry in result.rows:
        session.add(
            Measurement(
                experiment_id=experiment.id,
                # Null when the row did not join. The row is written either way:
                # a measurement the lab paid for is not discarded at the door.
                variant_id=by_code.get(entry.code) if entry.code else None,
                raw_label=entry.row.raw_label,
                metric=metric.strip(),
                unit=unit.strip(),
                value=entry.row.value,
                sd=entry.row.sd,
                replicate=entry.row.replicate,
                extra={"join_outcome": str(entry.outcome)},
            )
        )

    session.add(
        ProvenanceEvent(
            kind=ProvenanceEventKind.MEASUREMENTS_IMPORTED,
            project_id=project.id,
            subject_type="experiment",
            subject_id=experiment.id,
            payload={
                "target_id": str(target.id),
                "metric": metric.strip(),
                "unit": unit.strip(),
                "higher_is_better": higher_is_better,
                "assay": str(assay),
                "scheme_label": joined.scheme_label,
                "source_note": source_note,
                "rows_written": len(result.rows),
                "rows_joined": result.joined_count,
                "rows_unjoined": result.unjoined_count,
                "rows_rejected": len(problems),
                "column_mapping": {
                    "label": mapping.label,
                    "value": mapping.value,
                    "sd": mapping.sd,
                    "replicate": mapping.replicate,
                },
                # The shift, if one was accepted, is part of what happened and is
                # recorded rather than left implicit in the joined codes.
                "numbering_offset": offset,
                "manual_overrides": {str(k): v for k, v in (overrides or {}).items()},
            },
        )
    )
    session.commit()

    return ImportResult(
        experiment_id=experiment.id,
        written=len(result.rows),
        joined=result.joined_count,
        unjoined=result.unjoined_count,
        problems=tuple(problems),
    )


# --------------------------------------------------------------------------- #
# The scorecard
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class PointView:
    """One variant on the predicted-vs-measured scatter.

    ``variant_id`` is here because ``code`` is not unique on a pooled card:
    two targets can both carry an ``A1N``. The renderer keys on the id, so a
    scatter claiming 192 marks draws 192 of them.
    """

    variant_id: uuid.UUID
    code: str
    hgvs: str
    predicted: float
    measured: float
    #: How many measured rows were averaged into this point.
    replicates: int


@dataclass(frozen=True, slots=True)
class ScorecardView:
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
    spearman: float | None
    precision_k: int
    precision: float | None
    precision_note: str
    mae: float | None
    mean_signed_error: float | None
    error_unit: str | None
    bias_note: str
    #: Empty when the error terms were computable. Rendered beside the rank
    #: figure whenever it is not, per ARCHITECTURE.md §13.
    error_unavailable_reason: str
    calibration: tuple[Mapping[str, float], ...]
    points: tuple[PointView, ...]
    measured_without_prediction: int
    targets: tuple[str, ...]
    #: How many distinct target rows this card pools. Larger than `len(targets)`
    #: whenever several targets share a name, which repeated runs make common.
    target_count: int


@dataclass(frozen=True, slots=True)
class ScorecardReport:
    cards: tuple[ScorecardView, ...]
    #: Why there is nothing to show, when there is nothing. Never an empty page
    #: with no explanation.
    note: str
    measured_variants: int = 0
    unjoined_measurements: int = 0
    metrics: tuple[str, ...] = ()
    is_demo: bool = False


def _measurement_pairs(
    session: Session, target_ids: Sequence[uuid.UUID] | None
) -> tuple[dict[tuple[uuid.UUID, str, str], tuple[float, int, bool | None]], int, set[str]]:
    """Mean measured value per (variant, metric, unit), with replicate counts.

    Averaging replicates before pairing is what stops a variant measured eight
    times outvoting the rest of the plate in the MAE. The mean is stated
    wherever the number is shown; it is not a threshold and not a cutoff, but it
    is a choice, so it is written down rather than left implicit.
    """
    statement = select(Measurement, Experiment, Variant).join(
        Experiment, col(Measurement.experiment_id) == col(Experiment.id)
    ).join(Variant, col(Measurement.variant_id) == col(Variant.id))
    if target_ids is not None:
        statement = statement.where(col(Variant.target_id).in_(list(target_ids)))

    totals: dict[tuple[uuid.UUID, str, str], list[float]] = {}
    directions: dict[tuple[uuid.UUID, str, str], bool | None] = {}
    metrics: set[str] = set()
    for measurement, experiment, variant in session.exec(statement).all():
        key = (variant.id, measurement.metric, measurement.unit)
        totals.setdefault(key, []).append(measurement.value)
        # A later import may state a direction where an earlier one did not.
        # Never overwrite a stated direction with an unstated one.
        if directions.get(key) is None:
            directions[key] = experiment.higher_is_better
        metrics.add(measurement.metric)

    unjoined = session.exec(
        select(Measurement).where(col(Measurement.variant_id).is_(None))
    ).all()

    pairs = {
        key: (sum(values) / len(values), len(values), directions.get(key))
        for key, values in totals.items()
    }
    return pairs, len(unjoined), metrics


def _spec_for(model_id: str, metric_id: str) -> MetricSpec | None:
    """The unit and sign convention for one metric, from its own predictor.

    Looked up in the whole registry rather than in the currently active set: a
    score written when `CODONLAB_PROVIDERS` said `real` must still be readable
    when it says `mock`, because the score is a historical fact and the setting
    is not. Keyed on the model as well as the metric, so two predictors sharing
    a metric id cannot borrow each other's convention.
    """
    predictor = REGISTRY.get(model_id)
    if predictor is None:
        return None
    for metric in predictor.metrics:
        if metric.id == metric_id:
            return metric
    return None


def scorecards(
    session: Session,
    *,
    target_id: uuid.UUID | None = None,
    k: int = DEFAULT_PRECISION_K,
) -> ScorecardReport:
    """One card per (model version, measured metric).

    With no ``target_id`` this pools every target the lab has measured, which is
    the "persistent scorecard that accumulates across the lab's projects" from
    specification §5.9. Pooling is done over the *pairs* and the card is built
    once — never by averaging finished cards, which would weight a card resting
    on six points equally with one resting on two thousand
    (`domain/scorecard.accumulate` refuses that in as many words).
    """
    target_ids: list[uuid.UUID] | None = None
    if target_id is not None:
        require_target(session, target_id)
        target_ids = [target_id]

    measured, unjoined, metrics = _measurement_pairs(session, target_ids)
    if not measured:
        return ScorecardReport(
            cards=(),
            note=(
                "No measured values have been joined to a variant yet. Import bench "
                "results to compare them against what each predictor said."
            ),
            unjoined_measurements=unjoined,
        )

    variant_ids = {variant_id for variant_id, _, _ in measured}
    rows = session.exec(
        select(Score, ModelVersion, Variant, Run)
        .join(ModelVersion, col(Score.model_version_id) == col(ModelVersion.id))
        .join(Variant, col(Score.variant_id) == col(Variant.id))
        .join(Run, col(Score.run_id) == col(Run.id))
        .where(col(Score.variant_id).in_(list(variant_ids)))
    ).all()

    #: (model_version_id, score metric, variant_id) -> the score to use. Scores
    #: are content-addressed and reused across runs, so the same key normally
    #: carries one value; taking the most recent makes the choice deterministic
    #: when a re-run has written another row.
    chosen: dict[tuple[uuid.UUID, str, uuid.UUID], tuple[float, Run]] = {}
    versions: dict[uuid.UUID, ModelVersion] = {}
    variant_codes: dict[uuid.UUID, tuple[str, uuid.UUID]] = {}
    for score, version, variant, run in rows:
        key = (version.id, score.metric, score.variant_id)
        current = chosen.get(key)
        if current is None or run.created_at > current[1].created_at:
            chosen[key] = (score.value, run)
        versions[version.id] = version
        variant_codes[variant.id] = (variant.code, variant.target_id)

    target_names = {
        target.id: target.name
        for target in session.exec(select(Target)).all()
    }

    cards: list[ScorecardView] = []
    combinations = {
        (version_id, score_metric, measured_metric, measured_unit)
        for (version_id, score_metric, variant_id) in chosen
        for (mv_id, measured_metric, measured_unit) in measured
        if mv_id == variant_id
    }

    for version_id, score_metric, measured_metric, measured_unit in sorted(
        combinations, key=lambda item: (versions[item[0]].model_id, item[1], item[2])
    ):
        version = versions[version_id]
        spec = _spec_for(version.model_id, score_metric)
        if spec is None:
            # A score written by a predictor this build no longer carries. Its
            # unit and sign convention are not knowable from here, and guessing
            # either is the exact failure this module refuses elsewhere.
            continue

        pairs: list[scorecard_math.Paired] = []
        points: list[PointView] = []
        direction: bool | None = None
        used_targets: set[str] = set()
        # Counted by id, not by name. Repeated gate runs create many target rows
        # that share a name, so a name set collapses eight targets into one and
        # the card then claims a pooled figure rests on a single target.
        used_target_ids: set[uuid.UUID] = set()

        for (variant_id, metric_name, unit_name), (mean, replicates, stated) in measured.items():
            if metric_name != measured_metric or unit_name != measured_unit:
                continue
            found = chosen.get((version_id, score_metric, variant_id))
            if found is None:
                continue
            code, owning_target = variant_codes[variant_id]
            pairs.append(
                scorecard_math.Paired(
                    code=code, predicted=found[0], measured=mean, key=str(variant_id)
                )
            )
            points.append(
                PointView(
                    variant_id=variant_id,
                    code=code,
                    hgvs=hgvs_of(code),
                    predicted=found[0],
                    measured=mean,
                    replicates=replicates,
                )
            )
            if direction is None:
                direction = stated
            used_targets.add(target_names.get(owning_target, "unknown target"))
            used_target_ids.add(owning_target)

        if not pairs:
            continue

        if direction is None:
            # The import never stated which way the assay points. Every rank
            # statistic needs it, so the card says so instead of assuming.
            cards.append(
                _unrankable_card(
                    version=version,
                    spec=spec,
                    measured_metric=measured_metric,
                    measured_unit=measured_unit,
                    n=len(pairs),
                    points=tuple(sorted(points, key=lambda p: (p.code, str(p.variant_id)))),
                    targets=tuple(sorted(used_targets)),
                    target_count=len(used_target_ids),
                    k=k,
                )
            )
            continue

        predicted_convention = scorecard_math.Convention(
            metric=spec.id,
            unit=spec.unit or "unitless",
            higher_is_better=spec.higher_is_better,
        )
        measured_convention = scorecard_math.Convention(
            metric=measured_metric, unit=measured_unit, higher_is_better=direction
        )
        card = scorecard_math.build(
            model_id=version.model_id,
            pairs=pairs,
            predicted=predicted_convention,
            measured=measured_convention,
            k=k,
            measured_without_prediction=0,
            is_mock=version.is_mock,
        )
        cards.append(
            _to_view(
                card,
                version=version,
                spec_sign=spec.sign_convention,
                points=tuple(sorted(points, key=lambda p: (p.code, str(p.variant_id)))),
                targets=tuple(sorted(used_targets)),
                target_count=len(used_target_ids),
                k=k,
            )
        )

    if not cards:
        return ScorecardReport(
            cards=(),
            note=(
                "Measured values are joined to variants, but no active predictor has "
                "scored those variants yet. Run a design run over this target to "
                "compare against."
            ),
            measured_variants=len(measured),
            unjoined_measurements=unjoined,
            metrics=tuple(sorted(metrics)),
        )

    return ScorecardReport(
        cards=tuple(cards),
        note="",
        measured_variants=len(measured),
        unjoined_measurements=unjoined,
        metrics=tuple(sorted(metrics)),
        is_demo=any(card.is_mock for card in cards),
    )


def _unrankable_card(
    *,
    version: ModelVersion,
    spec: MetricSpec,
    measured_metric: str,
    measured_unit: str,
    n: int,
    points: tuple[PointView, ...],
    targets: tuple[str, ...],
    target_count: int,
    k: int,
) -> ScorecardView:
    """A card for measurements whose direction was never stated.

    Every statistic on it is None with the reason attached. Rendering a rank
    figure here would require assuming which way the assay points, which is the
    sign convention this product does not invent.
    """
    reason = (
        f"The import of {measured_metric} never stated whether a higher value is a "
        "better result. Every statistic here needs that to orient itself, so none "
        "is computed. Re-import stating the direction."
    )
    return ScorecardView(
        model_id=version.model_id,
        model_name=version.name,
        model_version=version.version,
        weights_hash=version.weights_hash,
        model_version_id=version.id,
        is_mock=version.is_mock,
        predicted_metric=spec.id,
        predicted_unit=spec.unit or "unitless",
        predicted_sign=spec.sign_convention,
        measured_metric=measured_metric,
        measured_unit=measured_unit,
        measured_sign="not stated",
        n=n,
        spearman=None,
        precision_k=k,
        precision=None,
        precision_note=reason,
        mae=None,
        mean_signed_error=None,
        error_unit=None,
        bias_note="",
        error_unavailable_reason=reason,
        calibration=(),
        points=points,
        measured_without_prediction=0,
        targets=targets,
        target_count=target_count,
    )


def _to_view(
    card: scorecard_math.Scorecard,
    *,
    version: ModelVersion,
    spec_sign: str,
    points: tuple[PointView, ...],
    targets: tuple[str, ...],
    target_count: int,
    k: int,
) -> ScorecardView:
    precision_note = ""
    if card.precision is None:
        precision_note = (
            f"precision@{k} needs at least {k} variants with both a prediction and a "
            f"measurement; there are {card.n}."
        )
    return ScorecardView(
        model_id=card.model_id,
        model_name=version.name,
        model_version=version.version,
        weights_hash=version.weights_hash,
        model_version_id=version.id,
        is_mock=card.is_mock,
        predicted_metric=card.predicted.metric,
        predicted_unit=card.predicted.unit,
        predicted_sign=spec_sign,
        measured_metric=card.measured.metric,
        measured_unit=card.measured.unit,
        measured_sign=card.measured.sign_note,
        n=card.n,
        spearman=card.spearman,
        precision_k=k,
        precision=card.precision.value if card.precision else None,
        precision_note=precision_note,
        mae=card.error.mae if card.error else None,
        mean_signed_error=card.error.mean_signed_error if card.error else None,
        error_unit=card.error.unit if card.error else None,
        bias_note=card.error.sign_note if card.error else "",
        error_unavailable_reason=card.commensurability.reason,
        calibration=tuple(
            {"predicted": entry.predicted, "measured": entry.measured, "count": entry.count}
            for entry in card.calibration
        ),
        points=points,
        measured_without_prediction=card.measured_without_prediction,
        targets=targets,
        target_count=target_count,
    )


# --------------------------------------------------------------------------- #
# Reading back an import
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ExperimentView:
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
    rows: tuple[PreviewRow, ...] = field(default_factory=tuple)


def experiments_for(session: Session, *, project_id: uuid.UUID) -> list[ExperimentView]:
    """Every import in a project, newest first."""
    require_project(session, project_id)
    found = session.exec(
        select(Experiment)
        .where(col(Experiment.project_id) == project_id)
        .order_by(col(Experiment.created_at).desc())
    ).all()

    views: list[ExperimentView] = []
    for experiment in found:
        rows = session.exec(
            select(Measurement).where(col(Measurement.experiment_id) == experiment.id)
        ).all()
        joined = sum(1 for row in rows if row.variant_id is not None)
        views.append(
            ExperimentView(
                id=experiment.id,
                assay=str(experiment.assay),
                metric=rows[0].metric if rows else "",
                unit=rows[0].unit if rows else "",
                higher_is_better=experiment.higher_is_better,
                source_note=experiment.source_note,
                protocol=experiment.protocol,
                operator=experiment.operator,
                performed_on=experiment.performed_on,
                total=len(rows),
                joined=joined,
                unjoined=len(rows) - joined,
            )
        )
    return views


def unjoined_rows(
    session: Session, *, experiment_id: uuid.UUID, limit: int = 200
) -> list[PreviewRow]:
    """The rows of one import that never found a variant.

    This is the working list for the join review screen. They exist as stored
    measurements, not as a rejected-file report, which is the difference between
    a row a user can resolve and a row they have to re-upload.
    """
    rows = session.exec(
        select(Measurement)
        .where(
            col(Measurement.experiment_id) == experiment_id,
            col(Measurement.variant_id).is_(None),
        )
        .limit(limit)
    ).all()
    return [
        PreviewRow(
            index=index,
            raw_label=row.raw_label or "",
            value=row.value,
            sd=row.sd,
            replicate=row.replicate,
            outcome=str(row.extra.get("join_outcome", "unjoined")),
            code=None,
            hgvs=None,
            detail="",
        )
        for index, row in enumerate(rows, start=1)
    ]


def attach_variant(
    session: Session, *, measurement_id: uuid.UUID, code: str | None
) -> Measurement:
    """Point a stored measurement at a variant by hand, or detach it.

    The manual override of specification §5.9, applied after import rather than
    only during it — a row can be resolved days later, when someone works out
    what the label meant.
    """
    measurement = session.get(Measurement, measurement_id)
    if measurement is None:
        raise ServiceError(
            "That measurement does not exist.", "Open it from the import's row list."
        )
    experiment = session.get(Experiment, measurement.experiment_id)
    if experiment is None:  # pragma: no cover - FK guarantees this
        raise ServiceError("That import no longer exists.", "Re-import the file.")

    if code is None:
        measurement.variant_id = None
        measurement.extra = {**measurement.extra, "join_outcome": "unjoined_by_hand"}
    else:
        variant = session.exec(
            select(Variant)
            .join(Target, col(Variant.target_id) == col(Target.id))
            .where(
                col(Target.project_id) == experiment.project_id,
                col(Variant.code) == code,
            )
        ).first()
        if variant is None:
            raise ServiceError(
                f"No variant in this project is called {code}.",
                "Use the canonical mutation code, in this target's confirmed "
                "numbering scheme.",
            )
        measurement.variant_id = variant.id
        measurement.extra = {**measurement.extra, "join_outcome": "joined_by_hand"}

    session.add(measurement)
    session.add(
        ProvenanceEvent(
            kind=ProvenanceEventKind.MEASUREMENTS_IMPORTED,
            project_id=experiment.project_id,
            subject_type="measurement",
            subject_id=measurement.id,
            payload={
                "action": "manual_join",
                "raw_label": measurement.raw_label,
                "code": code,
            },
        )
    )
    session.commit()
    session.refresh(measurement)
    return measurement
