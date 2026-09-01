"""Target setup and numbering reconciliation.

Domain rules from the specification live here; routes below this are an HTTP
surface only. Two rules shape every function:

* A target is not designable until some numbering scheme on it is canonical.
  Nothing here picks one — `confirm_canonical` is only ever reached by an
  explicit user action, and it writes a ProvenanceEvent when it is.
* Reconciliation previews are computed, shown, and only persisted once the user
  accepts them. `preview_reconciliation` writes nothing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlmodel import Session, col, select

from codonlab.domain.numbering import (
    ReconcileOutcome,
    Reconciliation,
    ResidueSlot,
    align,
    reconcile,
)
from codonlab.models import (
    NumberingScheme,
    Project,
    ProvenanceEvent,
    ProvenanceEventKind,
    Structure,
    Target,
)
from codonlab.models.base import utcnow
from codonlab.models.enums import NumberingKind, StructureSource
from codonlab.sources import fasta, structures, uniprot
from codonlab.sources.pdb import Chain, parse_pdb


class ServiceError(RuntimeError):
    """A failure with an explanation and a way forward."""

    def __init__(self, message: str, remedy: str) -> None:
        super().__init__(message)
        self.remedy = remedy


# --------------------------------------------------------------------------- #
# Numbering scheme storage
# --------------------------------------------------------------------------- #
#
# `NumberingScheme.offsets` holds one label per canonical sequence position,
# null where the scheme does not cover it. Storing labels rather than a single
# integer offset is deliberate: real schemes are not constant offsets. Ambler
# numbering skips residues, crystal structures leave gaps, and insertion codes
# are not integers at all. A stored offset would be a lie for all three.


def _labels(scheme: NumberingScheme) -> list[str | None]:
    raw = scheme.offsets.get("labels", [])
    return [None if item is None else str(item) for item in raw]


def _sequential_labels(length: int, offset: int = 0) -> list[str | None]:
    return [str(index + 1 + offset) for index in range(length)]


def _labels_from_mapping(mapping: tuple[ResidueSlot | None, ...]) -> list[str | None]:
    return [None if slot is None else slot.label for slot in mapping]


def label_at(scheme: NumberingScheme, position: int) -> str | None:
    """The label this scheme gives to 1-based canonical position `position`."""
    labels = _labels(scheme)
    if not 1 <= position <= len(labels):
        return None
    return labels[position - 1]


def labels_of(scheme: NumberingScheme) -> list[str | None]:
    """Every label in this scheme, by sequence index.

    Public because writing a mutation code is an explicit conversion out of
    sequence index and into the canonical scheme — ARCHITECTURE.md §9 — and a
    caller doing it one position at a time through `label_at` would rebuild the
    list on every residue.
    """
    return _labels(scheme)


# --------------------------------------------------------------------------- #
# Projects
# --------------------------------------------------------------------------- #


def create_project(
    session: Session, *, name: str, organism: str | None, objective: str | None
) -> Project:
    name = name.strip()
    if not name:
        raise ServiceError("A project needs a name.", "Enter a name and try again.")

    project = Project(
        name=name,
        organism=(organism or "").strip() or None,
        objective=(objective or "").strip() or None,
        last_activity_at=utcnow(),
    )
    session.add(project)
    session.flush()
    _record(
        session,
        kind=ProvenanceEventKind.PROJECT_CREATED,
        project_id=project.id,
        subject_type="project",
        subject_id=project.id,
        payload={"name": project.name},
    )
    session.commit()
    session.refresh(project)
    return project


# --------------------------------------------------------------------------- #
# Targets
# --------------------------------------------------------------------------- #


def require_project(session: Session, project_id: uuid.UUID) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise ServiceError("That project does not exist.", "Open it from the projects table.")
    return project


def _add_scheme(
    session: Session,
    target: Target,
    *,
    kind: NumberingKind,
    label: str,
    labels: list[str | None],
    note: str | None = None,
) -> NumberingScheme:
    scheme = NumberingScheme(
        target_id=target.id,
        kind=kind,
        label=label,
        offsets={"labels": labels, **({"note": note} if note else {})},
    )
    session.add(scheme)
    session.flush()
    return scheme


def create_target_from_uniprot(
    session: Session, *, project_id: uuid.UUID, accession: str
) -> Target:
    """Load a target from UniProt, with its candidate numbering schemes.

    Two schemes are offered when the record declares a signal peptide: the
    full-length record, and the mature protein. Neither is marked canonical.
    """
    project = require_project(session, project_id)
    record = uniprot.fetch(accession)

    target = Target(
        project_id=project.id,
        name=record.name,
        organism=record.organism,
        uniprot_accession=record.accession,
        sequence=record.sequence,
    )
    session.add(target)
    session.flush()

    _add_scheme(
        session,
        target,
        kind=NumberingKind.SEQUENCE,
        label=f"UniProt {record.accession}, full length",
        labels=_sequential_labels(record.length),
    )

    if record.signal_peptide is not None:
        offset = record.mature_offset or 0
        _add_scheme(
            session,
            target,
            kind=NumberingKind.CONSTRUCT,
            label="Mature protein, signal peptide removed",
            labels=_sequential_labels(record.length, offset),
            note=(
                f"Signal peptide is residues {record.signal_peptide.start}-"
                f"{record.signal_peptide.end} of the full-length record, so mature "
                f"numbering runs {offset:+d} against it."
            ),
        )

    project.last_activity_at = utcnow()
    _record(
        session,
        kind=ProvenanceEventKind.TARGET_ADDED,
        project_id=project.id,
        subject_type="target",
        subject_id=target.id,
        payload={
            "source": "uniprot",
            "accession": record.accession,
            "length": record.length,
            "signal_peptide": (
                None
                if record.signal_peptide is None
                else [record.signal_peptide.start, record.signal_peptide.end]
            ),
        },
    )
    session.commit()
    session.refresh(target)
    return target


def create_target_from_sequence(
    session: Session, *, project_id: uuid.UUID, name: str, text: str, organism: str | None
) -> Target:
    """Load a target from pasted FASTA or a bare sequence."""
    project = require_project(session, project_id)
    parsed = fasta.parse_fasta(text)

    if parsed.looks_like_nucleotides:
        raise ServiceError(
            "That looks like a nucleotide sequence, not a protein.",
            "Translate it first. Residue numbering derived from a gene would be "
            "wrong in a way that is hard to notice later.",
        )

    target = Target(
        project_id=project.id,
        name=(name.strip() or parsed.header or "Untitled target"),
        organism=(organism or "").strip() or None,
        sequence=parsed.sequence,
    )
    session.add(target)
    session.flush()

    _add_scheme(
        session,
        target,
        kind=NumberingKind.SEQUENCE,
        label="Pasted sequence, numbered from 1",
        labels=_sequential_labels(parsed.length),
    )

    project.last_activity_at = utcnow()
    _record(
        session,
        kind=ProvenanceEventKind.TARGET_ADDED,
        project_id=project.id,
        subject_type="target",
        subject_id=target.id,
        payload={"source": "pasted", "length": parsed.length, "header": parsed.header},
    )
    session.commit()
    session.refresh(target)
    return target


def require_target(session: Session, target_id: uuid.UUID) -> Target:
    target = session.get(Target, target_id)
    if target is None:
        raise ServiceError("That target does not exist.", "Open it from the project page.")
    return target


# --------------------------------------------------------------------------- #
# Structures
# --------------------------------------------------------------------------- #


def attach_structure(
    session: Session,
    *,
    target_id: uuid.UUID,
    source: StructureSource,
    identifier: str | None = None,
    text: str | None = None,
) -> tuple[Structure, list[Chain]]:
    """Fetch or accept a structure and record it against the target."""
    target = require_target(session, target_id)

    if source is StructureSource.PDB:
        if not identifier:
            raise ServiceError("No PDB id given.", "Enter a four-character id such as 1BTL.")
        fetched = structures.fetch_rcsb(identifier)
    elif source is StructureSource.ALPHAFOLD_DB:
        accession = identifier or target.uniprot_accession
        if not accession:
            raise ServiceError(
                "This target has no UniProt accession.",
                "AlphaFold DB is keyed by accession. Upload a structure instead.",
            )
        fetched = structures.fetch_alphafold(accession)
    elif source is StructureSource.UPLOADED_PDB:
        if not text:
            raise ServiceError("No file contents received.", "Choose a .pdb file and retry.")
        fetched = structures.FetchedStructure(
            source=StructureSource.UPLOADED_PDB,
            identifier=identifier or "uploaded",
            text=text,
            content_hash=structures.content_hash(text),
            note="Uploaded structure.",
        )
    else:
        raise ServiceError(
            f"{source.value} structures cannot be attached yet.",
            "Fetch from RCSB or AlphaFold DB, or upload a PDB file.",
        )

    parsed = parse_pdb(fetched.text)
    chains = parsed.protein_chains
    if not chains:
        raise ServiceError(
            "No protein chain of usable length was found in that structure.",
            "Check the file, or try a different entry.",
        )

    structure = Structure(
        target_id=target.id,
        source=fetched.source,
        identifier=fetched.identifier,
        content_hash=fetched.content_hash,
        chain=chains[0].chain_id,
        file_path=None,
    )
    session.add(structure)
    session.flush()

    _record(
        session,
        kind=ProvenanceEventKind.TARGET_ADDED,
        project_id=target.project_id,
        subject_type="structure",
        subject_id=structure.id,
        payload={
            "source": fetched.source.value,
            "identifier": fetched.identifier,
            "content_hash": fetched.content_hash,
            "note": fetched.note,
            "chains": {chain.chain_id: chain.length for chain in chains},
        },
    )
    session.commit()
    session.refresh(structure)
    # The parsed chains are returned rather than stored: re-parsing on demand
    # keeps the structure file the single source of truth.
    return structure, chains


@dataclass(frozen=True, slots=True)
class ReconciliationPreview:
    structure_id: uuid.UUID
    chain_id: str
    against: str
    result: Reconciliation


def _chain_for(session: Session, structure: Structure, chain_id: str | None) -> Chain:
    fetched = refetch_structure(structure)
    parsed = parse_pdb(fetched.text)
    chains = parsed.protein_chains
    if chain_id:
        for chain in chains:
            if chain.chain_id == chain_id:
                return chain
        raise ServiceError(
            f"Chain {chain_id} is not in that structure.",
            f"Available chains: {', '.join(chain.chain_id for chain in chains)}.",
        )
    return chains[0]


def refetch_structure(structure: Structure) -> structures.FetchedStructure:
    """Re-retrieve a structure by its recorded identity.

    Phase 2 does not store structure files, so they are fetched again on demand.
    The content hash recorded at attach time is checked, so a file that has
    changed underneath a target is detected rather than silently used.
    """
    if structure.source is StructureSource.PDB:
        fetched = structures.fetch_rcsb(structure.identifier or "")
    elif structure.source is StructureSource.ALPHAFOLD_DB:
        fetched = structures.fetch_alphafold(structure.identifier or "")
    else:
        raise ServiceError(
            "Uploaded structures are not retained yet.",
            "Re-upload the file, or fetch the structure from RCSB or AlphaFold DB.",
        )

    if fetched.content_hash != structure.content_hash:
        raise ServiceError(
            "The structure file has changed since it was attached to this target.",
            "Re-attach it so the change is recorded, rather than applied silently.",
        )
    return fetched


def preview_reconciliation(
    session: Session,
    *,
    target_id: uuid.UUID,
    structure_id: uuid.UUID,
    chain_id: str | None = None,
    use_alignment: bool = False,
) -> ReconciliationPreview:
    """Compute a mapping and return it. Writes nothing."""
    target = require_target(session, target_id)
    structure = session.get(Structure, structure_id)
    if structure is None or structure.target_id != target.id:
        raise ServiceError(
            "That structure is not attached to this target.",
            "Attach it first.",
        )

    chain = _chain_for(session, structure, chain_id)
    result = (
        align(target.sequence, chain.residues)
        if use_alignment
        else reconcile(target.sequence, chain.residues)
    )
    return ReconciliationPreview(
        structure_id=structure.id,
        chain_id=chain.chain_id,
        against=target.uniprot_accession or target.name,
        result=result,
    )


def accept_reconciliation(
    session: Session,
    *,
    target_id: uuid.UUID,
    structure_id: uuid.UUID,
    chain_id: str | None = None,
    use_alignment: bool = False,
    actor: str | None = None,
) -> NumberingScheme:
    """Persist a reconciled mapping as a numbering scheme on the target.

    Creating the scheme does not make it canonical. That remains a separate,
    explicit act.
    """
    preview = preview_reconciliation(
        session,
        target_id=target_id,
        structure_id=structure_id,
        chain_id=chain_id,
        use_alignment=use_alignment,
    )
    if preview.result.outcome is not ReconcileOutcome.RECONCILED:
        raise ServiceError(
            "That mapping is not resolved, so it cannot be saved.",
            preview.result.note,
        )

    target = require_target(session, target_id)
    structure = session.get(Structure, structure_id)
    assert structure is not None  # preview_reconciliation already validated it

    label = f"{structure.identifier} chain {preview.chain_id}, author numbering"
    existing = session.exec(
        select(NumberingScheme).where(
            col(NumberingScheme.target_id) == target.id,
            col(NumberingScheme.label) == label,
        )
    ).first()
    if existing is not None:
        session.delete(existing)
        session.flush()

    scheme = _add_scheme(
        session,
        target,
        kind=NumberingKind.PDB_AUTHOR,
        label=label,
        labels=_labels_from_mapping(preview.result.mapping),
        note=preview.result.note,
    )

    _record(
        session,
        kind=ProvenanceEventKind.NUMBERING_RECONCILED,
        project_id=target.project_id,
        subject_type="numberingscheme",
        subject_id=scheme.id,
        actor=actor,
        payload={
            "structure": structure.identifier,
            "structure_hash": structure.content_hash,
            "chain": preview.chain_id,
            "method": preview.result.method.value if preview.result.method else None,
            "parameters": preview.result.parameters,
            "coverage": round(preview.result.coverage, 4),
            "identity": round(preview.result.identity, 4),
            "mismatches": [
                {
                    "sequence_position": mismatch.canonical_position,
                    "sequence_residue": mismatch.canonical_residue,
                    "structure_label": mismatch.observed_slot.label,
                    "structure_residue": mismatch.observed_residue,
                }
                for mismatch in preview.result.mismatches
            ],
        },
    )
    session.commit()
    session.refresh(scheme)
    return scheme


# --------------------------------------------------------------------------- #
# Canonical scheme
# --------------------------------------------------------------------------- #


def confirm_canonical(
    session: Session, *, target_id: uuid.UUID, scheme_id: uuid.UUID, actor: str | None = None
) -> NumberingScheme:
    """Mark one scheme canonical. Reached only by explicit user action."""
    target = require_target(session, target_id)
    scheme = session.get(NumberingScheme, scheme_id)
    if scheme is None or scheme.target_id != target.id:
        raise ServiceError(
            "That numbering scheme does not belong to this target.",
            "Choose one of the schemes listed for this target.",
        )

    previous = session.exec(
        select(NumberingScheme).where(
            col(NumberingScheme.target_id) == target.id,
            col(NumberingScheme.is_canonical).is_(True),
        )
    ).all()
    for existing in previous:
        existing.is_canonical = False
        session.add(existing)
    # Flush the clears before setting the new one, so the partial unique index
    # never sees two canonical schemes on this target mid-transaction.
    session.flush()

    scheme.is_canonical = True
    session.add(scheme)

    _record(
        session,
        kind=ProvenanceEventKind.NUMBERING_RECONCILED,
        project_id=target.project_id,
        subject_type="target",
        subject_id=target.id,
        actor=actor,
        payload={
            "canonical_scheme": scheme.label,
            "scheme_id": str(scheme.id),
            "replaced": [existing.label for existing in previous],
        },
    )
    session.commit()
    session.refresh(scheme)
    return scheme


def canonical_scheme(session: Session, target_id: uuid.UUID) -> NumberingScheme | None:
    return session.exec(
        select(NumberingScheme).where(
            col(NumberingScheme.target_id) == target_id,
            col(NumberingScheme.is_canonical).is_(True),
        )
    ).first()


def schemes_for(session: Session, target_id: uuid.UUID) -> list[NumberingScheme]:
    return list(
        session.exec(
            select(NumberingScheme)
            .where(col(NumberingScheme.target_id) == target_id)
            .order_by(col(NumberingScheme.created_at))
        ).all()
    )


def structures_for(session: Session, target_id: uuid.UUID) -> list[Structure]:
    return list(
        session.exec(
            select(Structure)
            .where(col(Structure.target_id) == target_id)
            .order_by(col(Structure.created_at))
        ).all()
    )


def _record(
    session: Session,
    *,
    kind: ProvenanceEventKind,
    subject_type: str,
    subject_id: uuid.UUID | None,
    project_id: uuid.UUID | None = None,
    actor: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    session.add(
        ProvenanceEvent(
            kind=kind,
            project_id=project_id,
            subject_type=subject_type,
            subject_id=subject_id,
            actor=actor,
            payload=payload or {},
        )
    )


def touch(session: Session, project_id: uuid.UUID, when: datetime | None = None) -> None:
    project = session.get(Project, project_id)
    if project is not None:
        project.last_activity_at = when or utcnow()
        session.add(project)
