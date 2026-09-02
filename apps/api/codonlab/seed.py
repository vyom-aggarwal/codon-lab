"""Idempotent development seed.

Scope note — this seeds *projects*, plus one target that exists to carry real
measured values.

A Target requires an amino acid sequence, and writing a real protein sequence
from memory is exactly the kind of fabricated scientific content this product
exists to refuse. That rule has not been relaxed. The Phase 8 target below takes
its sequence from a **vendored, sourced artefact** —
`data/proteingym/ESTA_BACSU_target.fasta`, verbatim from ProteinGym's reference
file and checked byte-identical against live UniProt P37957 — and the seed
verifies every residue it is about to mutate against that sequence before it
writes anything. Nothing here is remembered; a corrupted data file fails loudly
rather than seeding a target whose numbering is quietly wrong.

The first two projects remain metadata only. Real targets for them arrive
through Phase 2's fetch, whose exit gate is resolving a UniProt accession and a
PDB for real and reconciling their numbering.

**Why the Phase 8 target is seeded with variants but no run.** `BRIEF.md` §7
asks for a deep-mutational-scanning dataset with real measured values "so the
scorecard screen is demoable with true numbers on day one". Measurements join to
`Variant` rows, so the rows have to exist; they are created here through the same
`domain/variants` enumeration a run uses, and migration 0004's
`uq_variant_target_code` means a later run reuses these exact rows rather than
making a second set. What the seed does **not** do is manufacture a `Run` or a
`Score`. A run that did not happen has no provenance, and a score with no run is
the one thing the schema forbids outright (ARCHITECTURE.md §5). Until a real run
is executed the scorecard therefore reports, correctly, that measured values are
present and nothing has predicted them yet.
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import Session, col, select

from codonlab.db import get_engine
from codonlab.domain.mutation import MutationParseError, parse_mutation
from codonlab.domain.variants import enumerate_single_substitutions
from codonlab.models import (
    Experiment,
    Measurement,
    NumberingScheme,
    Project,
    ProvenanceEvent,
    ProvenanceEventKind,
    Target,
    Variant,
)
from codonlab.models.enums import AssayKind, NumberingKind

SEED_PROJECTS: tuple[dict[str, str], ...] = (
    {
        "name": "TEM-1 thermostability",
        "organism": "Escherichia coli",
        "objective": "Raise the melting temperature of TEM-1 beta-lactamase "
        "(UniProt P62593) without losing hydrolytic activity.",
    },
    {
        "name": "Lipase A solvent tolerance",
        "organism": "Bacillus subtilis",
        "objective": "Improve tolerance of lipase A (UniProt P37957) to organic "
        "cosolvent while preserving expression yield.",
    },
)

DATA = Path(__file__).parent / "data" / "proteingym"

#: The validation-loop project. Separate from "Lipase A solvent tolerance" on
#: purpose: that project's objective is solvent tolerance and these measurements
#: are thermostability, and filing a T50 under a solvent-tolerance objective
#: would misdescribe what was measured.
VALIDATION_PROJECT = "Lipase A thermostability, measured"

@dataclass(frozen=True, slots=True)
class SeededAssay:
    """Everything about the vendored assay that has to be stated rather than inferred.

    `higher_is_better` is a field here because ProteinGym's reference file
    records the raw phenotype as T50 with directionality +1 — it is read off a
    source, not assumed, and `Experiment.higher_is_better` has no default
    precisely so that it cannot be assumed elsewhere either.
    """

    measurements: str
    sequence: str
    metric: str
    unit: str
    higher_is_better: bool
    assay: AssayKind
    citation: str


ASSAY = SeededAssay(
    measurements="ESTA_BACSU_Nutschel_2020.csv",
    sequence="ESTA_BACSU_target.fasta",
    metric="t50_celsius",
    unit="°C",
    higher_is_better=True,
    assay=AssayKind.THERMAL_STABILITY,
    citation=(
        "Nutschel et al. 2020, J. Chem. Inf. Model. 60(3), "
        "doi:10.1021/acs.jcim.9b00954, via ProteinGym assay ESTA_BACSU_Nutschel_2020"
    ),
)

EXPECTED_LENGTH = 212


def _read_sequence() -> str:
    """The target sequence, from the vendored FASTA."""
    path = DATA / ASSAY.sequence
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith(">")
    ]
    sequence = "".join(lines).upper()
    if len(sequence) != EXPECTED_LENGTH:
        raise RuntimeError(
            f"{path.name} holds {len(sequence)} residues, expected {EXPECTED_LENGTH}. "
            "Refusing to seed a target whose sequence does not match what the "
            "measurements were made on."
        )
    return sequence


def _read_measurements() -> list[tuple[str, float]]:
    """`(mutation code, T50)` pairs from the vendored DMS file.

    Read with the standard library rather than the import service: the seed
    writes what the file says, and the service's column-mapping and preview
    machinery exists for files whose shape is unknown. This file's shape is
    pinned by its SHA-256 in the data directory's README.
    """
    path = DATA / ASSAY.measurements
    rows: list[tuple[str, float]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for record in csv.DictReader(handle):
            code = (record.get("mutant") or "").strip()
            raw = (record.get("DMS_score") or "").strip()
            if not code or not raw:
                continue
            rows.append((code, float(raw)))
    return rows


def _verify_against_sequence(sequence: str, rows: list[tuple[str, float]]) -> None:
    """Every measured row must name the residue the sequence actually has.

    This is the check that makes the seed safe. Mutation codes in this file are
    written against the full-length precursor numbered from 1, which is the
    numbering the seeded target uses — so a code naming a residue the sequence
    does not carry means the file and the sequence have drifted apart, and
    seeding either of them would attach 2,172 real measurements to the wrong
    residues.
    """
    for code, _ in rows:
        try:
            mutation = parse_mutation(code)
        except MutationParseError as error:  # pragma: no cover - pinned data file
            raise RuntimeError(f"{code!r} in the seeded assay is not a mutation code") from error
        position = mutation.position
        if not 1 <= position <= len(sequence):
            raise RuntimeError(
                f"{code} names position {position}, outside the {len(sequence)}-residue "
                "seeded sequence."
            )
        if sequence[position - 1] != mutation.wild:
            raise RuntimeError(
                f"{code} says position {position} is {mutation.wild}, but the seeded "
                f"sequence has {sequence[position - 1]}. The measurements and the "
                "sequence disagree; refusing to seed."
            )


def _seed_validation_loop(session: Session) -> int:
    """Project, target, numbering, variants and measurements. Idempotent."""
    existing = session.exec(
        select(Project).where(Project.name == VALIDATION_PROJECT)
    ).first()
    if existing is not None:
        return 0

    sequence = _read_sequence()
    rows = _read_measurements()
    _verify_against_sequence(sequence, rows)

    project = Project(
        name=VALIDATION_PROJECT,
        organism="Bacillus subtilis",
        objective=(
            "Compare each predictor against 2,172 measured T50 values for lipase A "
            "(UniProt P37957), so the scorecard reports which one this lab should trust."
        ),
    )
    session.add(project)
    session.flush()

    target = Target(
        project_id=project.id,
        name="Lipase EstA",
        organism="Bacillus subtilis (strain 168)",
        uniprot_accession="P37957",
        sequence=sequence,
    )
    session.add(target)
    session.flush()

    # The measurements are written against the full-length precursor numbered
    # from 1, so that is what this target's canonical scheme is. Stating it
    # explicitly is the whole point: a target whose canonical scheme is implicit
    # is a target every mutation code on it is ambiguous against.
    session.add(
        NumberingScheme(
            target_id=target.id,
            kind=NumberingKind.SEQUENCE,
            label="UniProt P37957, full length",
            offsets={"labels": [str(index) for index in range(1, len(sequence) + 1)]},
            is_canonical=True,
        )
    )

    # Created through the same enumeration a run uses, so a later run reuses
    # these rows rather than writing a second set beside them.
    labels: list[str | None] = [str(index) for index in range(1, len(sequence) + 1)]
    enumeration = enumerate_single_substitutions(sequence, labels)
    by_code: dict[str, Variant] = {}
    for candidate in enumeration.candidates:
        variant = Variant(
            target_id=target.id,
            mutations=[candidate.code],
            code=candidate.code,
            position=candidate.sequence_position,
        )
        by_code[candidate.code] = variant
        session.add(variant)
    session.flush()

    experiment = Experiment(
        project_id=project.id,
        assay=ASSAY.assay,
        protocol="Deep mutational scan, T50 by residual activity after thermal challenge.",
        operator=None,
        higher_is_better=ASSAY.higher_is_better,
        source_note=ASSAY.citation,
    )
    session.add(experiment)
    session.flush()

    joined = 0
    for code, value in rows:
        measured = by_code.get(code)
        if measured is not None:
            joined += 1
        session.add(
            Measurement(
                experiment_id=experiment.id,
                # Null for anything the enumeration does not cover — a
                # non-standard residue, say. The row is still written: a
                # measurement that failed to join is resolved by hand, never
                # dropped.
                variant_id=measured.id if measured is not None else None,
                raw_label=code,
                metric=ASSAY.metric,
                unit=ASSAY.unit,
                value=value,
                extra={"join_outcome": "joined" if measured else "no_such_variant"},
            )
        )

    session.add(
        ProvenanceEvent(
            kind=ProvenanceEventKind.MEASUREMENTS_IMPORTED,
            project_id=project.id,
            subject_type="experiment",
            subject_id=experiment.id,
            payload={
                "source": "seed",
                "target_id": str(target.id),
                "metric": ASSAY.metric,
                "unit": ASSAY.unit,
                "higher_is_better": ASSAY.higher_is_better,
                "citation": ASSAY.citation,
                "scheme_label": "UniProt P37957, full length",
                "rows_written": len(rows),
                "rows_joined": joined,
                "rows_unjoined": len(rows) - joined,
                "variants_created": len(by_code),
            },
        )
    )
    return len(rows)


def seed() -> tuple[int, int]:
    """Insert anything missing. Safe to run on every container start."""
    inserted = 0
    measurements = 0
    with Session(get_engine()) as session:
        for row in SEED_PROJECTS:
            existing = session.exec(select(Project).where(Project.name == row["name"])).first()
            if existing is not None:
                continue
            session.add(Project(**row))
            inserted += 1
        measurements = _seed_validation_loop(session)
        session.commit()
    return inserted, measurements


def measured_target_id(session: Session) -> str | None:
    """The seeded validation-loop target, for gates and tooling."""
    project = session.exec(select(Project).where(Project.name == VALIDATION_PROJECT)).first()
    if project is None:
        return None
    target = session.exec(
        select(Target).where(col(Target.project_id) == project.id)
    ).first()
    return str(target.id) if target else None


def main() -> None:
    inserted, measurements = seed()
    parts = []
    if inserted:
        parts.append(f"inserted {inserted} project(s)")
    if measurements:
        parts.append(f"imported {measurements} measured value(s)")
    summary = ", ".join(parts) if parts else "already present, nothing to do"
    print(f"seed: {summary}", file=sys.stderr)


if __name__ == "__main__":
    main()
