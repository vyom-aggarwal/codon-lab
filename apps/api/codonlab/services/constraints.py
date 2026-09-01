"""Constraints: annotate a target before designing against it.

Constraints are hard filters. Two rules follow from that:

* Nothing is applied without the user accepting it. UniProt annotations are
  imported as *suggestions*, each carrying its source, and an unaccepted
  suggestion constrains nothing.
* Every position is translated out of UniProt's numbering and into the
  target's canonical scheme before it is shown. On TEM-1 the catalytic residue
  is annotated at 68 and called Ser70 at the bench — importing the raw number
  would misplace the single most important residue on the protein.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlmodel import Session, col, select

from codonlab.domain.aminoacid import one_to_three
from codonlab.models import Constraint, ConstraintKind, ProvenanceEvent, ProvenanceEventKind
from codonlab.services.targets import ServiceError, canonical_scheme, label_at, require_target
from codonlab.sources import uniprot

#: UniProt feature type to the constraint it implies.
_KIND_BY_FEATURE: dict[str, ConstraintKind] = {
    "Active site": ConstraintKind.CATALYTIC,
    "Binding site": ConstraintKind.LIGAND_CONTACT,
    "Metal binding": ConstraintKind.COFACTOR_CONTACT,
    "Site": ConstraintKind.LIGAND_CONTACT,
    "Disulfide bond": ConstraintKind.DISULFIDE,
    "Signal": ConstraintKind.SIGNAL_PEPTIDE,
}


@dataclass(frozen=True, slots=True)
class Suggestion:
    """A proposed constraint, not yet applied."""

    kind: ConstraintKind
    #: 1-based positions in the target's canonical sequence.
    positions: tuple[int, ...]
    #: The same positions as the canonical scheme labels them, for display.
    labels: tuple[str, ...]
    residues: tuple[str, ...]
    source: str
    note: str

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "positions": list(self.positions),
            "labels": list(self.labels),
            "residues": list(self.residues),
            "source": self.source,
            "note": self.note,
        }


def suggest_from_uniprot(session: Session, *, target_id: uuid.UUID) -> list[Suggestion]:
    """Read UniProt's annotations for this target and propose constraints.

    Returns proposals only. Nothing is written, and nothing constrains the
    design until `accept` is called.
    """
    target = require_target(session, target_id)
    if not target.uniprot_accession:
        raise ServiceError(
            "This target has no UniProt accession.",
            "Annotations are read from the UniProt record. Add constraints by hand instead.",
        )

    scheme = canonical_scheme(session, target.id)
    if scheme is None:
        raise ServiceError(
            "This target has no canonical numbering scheme.",
            "Reconcile numbering first — otherwise every imported position would be ambiguous.",
        )

    record = uniprot.fetch(target.uniprot_accession)
    suggestions: list[Suggestion] = []

    for feature in record.features:
        kind = _KIND_BY_FEATURE.get(feature.kind)
        if kind is None:
            continue

        # A disulfide bond annotates two bonded cysteines, not the span
        # between them. Expanding it into a range would constrain the whole
        # intervening loop, which is not what the annotation says.
        positions: tuple[int, ...]
        if kind is ConstraintKind.DISULFIDE:
            positions = (feature.start, feature.end)
        else:
            positions = tuple(range(feature.start, feature.end + 1))

        inside = tuple(p for p in positions if 1 <= p <= len(target.sequence))
        if not inside:
            continue

        labels = tuple(label_at(scheme, position) or "—" for position in inside)
        residues = tuple(target.sequence[position - 1] for position in inside)

        rendered = ", ".join(
            f"{one_to_three(residue)}{label}"
            for residue, label in zip(residues, labels, strict=True)
        )
        translated = (
            f" (UniProt {feature.start}"
            f"{f'-{feature.end}' if feature.end != feature.start else ''}"
            f" → {', '.join(labels)} in {scheme.label})"
        )

        suggestions.append(
            Suggestion(
                kind=kind,
                positions=inside,
                labels=labels,
                residues=residues,
                source=f"UniProt {record.accession}",
                note=(feature.description or feature.kind) + f": {rendered}{translated}",
            )
        )

    return suggestions


def accept(
    session: Session,
    *,
    target_id: uuid.UUID,
    kind: ConstraintKind,
    positions: list[int],
    note: str | None = None,
    created_by: str | None = None,
) -> Constraint:
    """Apply a constraint. Positions are in the canonical numbering scheme."""
    target = require_target(session, target_id)
    if canonical_scheme(session, target.id) is None:
        raise ServiceError(
            "This target has no canonical numbering scheme.",
            "Reconcile numbering before adding constraints.",
        )

    clean = sorted({int(position) for position in positions})
    if not clean:
        raise ServiceError("No positions given.", "Select at least one residue.")

    out_of_range = [p for p in clean if not 1 <= p <= len(target.sequence)]
    if out_of_range:
        raise ServiceError(
            f"Positions outside the sequence: {out_of_range}.",
            f"This target is {len(target.sequence)} residues long.",
        )

    constraint = Constraint(
        target_id=target.id,
        kind=kind,
        positions=clean,
        note=note,
        created_by=created_by,
    )
    session.add(constraint)
    session.flush()

    session.add(
        ProvenanceEvent(
            kind=ProvenanceEventKind.CONSTRAINT_ADDED,
            project_id=target.project_id,
            subject_type="constraint",
            subject_id=constraint.id,
            actor=created_by,
            payload={"kind": kind.value, "positions": clean, "note": note},
        )
    )
    session.commit()
    session.refresh(constraint)
    return constraint


def remove(session: Session, *, constraint_id: uuid.UUID) -> None:
    constraint = session.get(Constraint, constraint_id)
    if constraint is None:
        raise ServiceError("That constraint does not exist.", "Reload the page.")
    session.delete(constraint)
    session.commit()


def constraints_for(session: Session, target_id: uuid.UUID) -> list[Constraint]:
    return list(
        session.exec(
            select(Constraint)
            .where(col(Constraint.target_id) == target_id)
            .order_by(col(Constraint.created_at))
        ).all()
    )


def constrained_positions(session: Session, target_id: uuid.UUID) -> dict[int, list[str]]:
    """Every constrained position, mapped to the constraint kinds covering it.

    This is what the design pipeline filters against, and what makes a
    filtered-out variant explainable: the reason is the kind, not a bare flag.
    """
    covered: dict[int, list[str]] = {}
    for constraint in constraints_for(session, target_id):
        for position in constraint.positions:
            covered.setdefault(int(position), []).append(constraint.kind.value)
    return covered
