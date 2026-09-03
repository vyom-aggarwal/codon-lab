"""Target setup and numbering reconciliation over HTTP.

No business logic here — every handler validates its input, calls a service, and
shapes the response. See ARCHITECTURE.md §3.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlmodel import Session

from codonlab.db import get_session
from codonlab.models import NumberingScheme, Structure, Target
from codonlab.models.enums import StructureSource
from codonlab.ownership import OWNERSHIP
from codonlab.services import targets as service
from codonlab.sources.fasta import FastaError
from codonlab.sources.pdb import StructureParseError
from codonlab.sources.uniprot import SourceError

# Ownership is enforced for the whole router rather than per handler: a
# route added later cannot forget to opt in. See codonlab/ownership.py.
router = APIRouter(tags=["targets"], dependencies=[OWNERSHIP])


def _fail(error: Exception, status: int = 400) -> HTTPException:
    """Surface a failure with the remedy attached, never a bare message."""
    remedy = getattr(error, "remedy", None)
    return HTTPException(
        status_code=status,
        detail={"message": str(error), "remedy": remedy or "Check the input and try again."},
    )


Handled = (service.ServiceError, SourceError, FastaError, StructureParseError)


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #


class NumberingSchemeOut(BaseModel):
    id: uuid.UUID
    kind: str
    label: str
    is_canonical: bool
    note: str | None
    #: First and last labels, so the UI can show each scheme's range without
    #: shipping every label for every scheme.
    first_label: str | None
    last_label: str | None
    covered: int

    @classmethod
    def of(cls, scheme: NumberingScheme) -> NumberingSchemeOut:
        labels = [label for label in scheme.offsets.get("labels", []) if label is not None]
        return cls(
            id=scheme.id,
            kind=scheme.kind.value,
            label=scheme.label,
            is_canonical=scheme.is_canonical,
            note=scheme.offsets.get("note"),
            first_label=str(labels[0]) if labels else None,
            last_label=str(labels[-1]) if labels else None,
            covered=len(labels),
        )


class StructureOut(BaseModel):
    id: uuid.UUID
    source: str
    identifier: str | None
    chain: str | None
    content_hash: str
    is_predicted: bool

    @classmethod
    def of(cls, structure: Structure) -> StructureOut:
        return cls(
            id=structure.id,
            source=structure.source.value,
            identifier=structure.identifier,
            chain=structure.chain,
            content_hash=structure.content_hash,
            is_predicted=structure.source
            in (StructureSource.ALPHAFOLD_DB, StructureSource.ESMFOLD),
        )


class TargetOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    organism: str | None
    uniprot_accession: str | None
    sequence: str
    length: int
    numbering_schemes: list[NumberingSchemeOut]
    structures: list[StructureOut]
    canonical_scheme_label: str | None
    #: False until a canonical scheme is confirmed. Every downstream screen
    #: keys off this: no mutation code can be rendered unambiguously without it.
    is_designable: bool


class CreateTargetIn(BaseModel):
    source: Literal["uniprot", "sequence"]
    accession: str | None = None
    name: str | None = None
    organism: str | None = None
    text: str | None = None


class AttachStructureIn(BaseModel):
    source: Literal["pdb", "alphafold_db", "uploaded_pdb"]
    identifier: str | None = None
    text: str | None = None


class MismatchOut(BaseModel):
    sequence_position: int
    sequence_residue: str
    structure_label: str
    structure_residue: str


class ReconciliationOut(BaseModel):
    outcome: str
    method: str | None
    chain_id: str
    structure_id: uuid.UUID
    coverage: float
    identity: float
    covered: int
    total: int
    mismatches: list[MismatchOut]
    candidate_offsets: list[int]
    parameters: dict[str, float] | None
    note: str
    #: Per-position labels, so the sequence track can render the mapping.
    labels: list[str | None]


class ReconcileIn(BaseModel):
    structure_id: uuid.UUID
    chain_id: str | None = None
    use_alignment: bool = Field(
        default=False,
        description="Only ever set from an explicit user action. Alignment is "
        "never reached by the server deciding to try harder.",
    )


class ConfirmCanonicalIn(BaseModel):
    scheme_id: uuid.UUID
    actor: str | None = None


# --------------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------------- #

SessionDep = Annotated[Session, Depends(get_session)]


def _target_out(session: Session, target: Target) -> TargetOut:
    schemes = service.schemes_for(session, target.id)
    canonical = next((scheme for scheme in schemes if scheme.is_canonical), None)
    return TargetOut(
        id=target.id,
        project_id=target.project_id,
        name=target.name,
        organism=target.organism,
        uniprot_accession=target.uniprot_accession,
        sequence=target.sequence,
        length=len(target.sequence),
        numbering_schemes=[NumberingSchemeOut.of(scheme) for scheme in schemes],
        structures=[StructureOut.of(s) for s in service.structures_for(session, target.id)],
        canonical_scheme_label=canonical.label if canonical else None,
        is_designable=canonical is not None,
    )


@router.post("/projects/{project_id}/targets", response_model=TargetOut, status_code=201)
def create_target(project_id: uuid.UUID, body: CreateTargetIn, session: SessionDep) -> TargetOut:
    try:
        if body.source == "uniprot":
            target = service.create_target_from_uniprot(
                session, project_id=project_id, accession=body.accession or ""
            )
        else:
            target = service.create_target_from_sequence(
                session,
                project_id=project_id,
                name=body.name or "",
                text=body.text or "",
                organism=body.organism,
            )
    except Handled as error:
        raise _fail(error) from error
    return _target_out(session, target)


@router.get("/targets/{target_id}", response_model=TargetOut)
def get_target(target_id: uuid.UUID, session: SessionDep) -> TargetOut:
    try:
        target = service.require_target(session, target_id)
    except Handled as error:
        raise _fail(error, status=404) from error
    return _target_out(session, target)


@router.post("/targets/{target_id}/structures", response_model=TargetOut, status_code=201)
def attach_structure(
    target_id: uuid.UUID, body: AttachStructureIn, session: SessionDep
) -> TargetOut:
    try:
        service.attach_structure(
            session,
            target_id=target_id,
            source=StructureSource(body.source),
            identifier=body.identifier,
            text=body.text,
        )
        target = service.require_target(session, target_id)
    except Handled as error:
        raise _fail(error) from error
    return _target_out(session, target)


def _reconciliation_out(preview: service.ReconciliationPreview) -> ReconciliationOut:
    result = preview.result
    return ReconciliationOut(
        outcome=result.outcome.value,
        method=result.method.value if result.method else None,
        chain_id=preview.chain_id,
        structure_id=preview.structure_id,
        coverage=round(result.coverage, 4),
        identity=round(result.identity, 4),
        covered=result.covered,
        total=len(result.mapping),
        mismatches=[
            MismatchOut(
                sequence_position=mismatch.canonical_position,
                sequence_residue=mismatch.canonical_residue,
                structure_label=mismatch.observed_slot.label,
                structure_residue=mismatch.observed_residue,
            )
            for mismatch in result.mismatches
        ],
        candidate_offsets=list(result.candidate_offsets),
        parameters=result.parameters,
        note=result.note,
        labels=[None if slot is None else slot.label for slot in result.mapping],
    )


@router.post("/targets/{target_id}/reconcile", response_model=ReconciliationOut)
def preview_reconciliation(
    target_id: uuid.UUID, body: ReconcileIn, session: SessionDep
) -> ReconciliationOut:
    """Compute a mapping and return it without saving anything."""
    try:
        preview = service.preview_reconciliation(
            session,
            target_id=target_id,
            structure_id=body.structure_id,
            chain_id=body.chain_id,
            use_alignment=body.use_alignment,
        )
    except Handled as error:
        raise _fail(error) from error
    return _reconciliation_out(preview)


@router.post("/targets/{target_id}/reconcile/accept", response_model=TargetOut, status_code=201)
def accept_reconciliation(
    target_id: uuid.UUID, body: ReconcileIn, session: SessionDep
) -> TargetOut:
    try:
        service.accept_reconciliation(
            session,
            target_id=target_id,
            structure_id=body.structure_id,
            chain_id=body.chain_id,
            use_alignment=body.use_alignment,
        )
        target = service.require_target(session, target_id)
    except Handled as error:
        raise _fail(error) from error
    return _target_out(session, target)


@router.post("/targets/{target_id}/numbering/confirm", response_model=TargetOut)
def confirm_canonical(
    target_id: uuid.UUID, body: ConfirmCanonicalIn, session: SessionDep
) -> TargetOut:
    """Mark one scheme canonical, unlocking the rest of the project."""
    try:
        service.confirm_canonical(
            session, target_id=target_id, scheme_id=body.scheme_id, actor=body.actor
        )
        target = service.require_target(session, target_id)
    except Handled as error:
        raise _fail(error) from error
    return _target_out(session, target)


class MutationRenderOut(BaseModel):
    short: str
    hgvs: str
    scheme_label: str
    rendered: str


@router.get("/targets/{target_id}/mutation/{code}", response_model=MutationRenderOut)
def render_mutation(target_id: uuid.UUID, code: str, session: SessionDep) -> MutationRenderOut:
    """Render a mutation code in the target's canonical scheme.

    Refuses while no scheme is canonical. That refusal is the point: a code
    rendered against an unconfirmed scheme is exactly the ambiguity Phase 2
    exists to remove.
    """
    from codonlab.domain.mutation import MutationParseError, parse_mutation

    try:
        target = service.require_target(session, target_id)
    except Handled as error:
        raise _fail(error, status=404) from error

    scheme = service.canonical_scheme(session, target.id)
    if scheme is None:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "This target has no canonical numbering scheme.",
                "remedy": "Reconcile numbering and confirm a scheme first.",
            },
        )

    try:
        mutation = parse_mutation(code)
    except MutationParseError as error:
        raise _fail(error) from error

    return MutationRenderOut(
        short=mutation.short(),
        hgvs=mutation.hgvs(),
        scheme_label=scheme.label,
        rendered=mutation.render(scheme.label),
    )


@router.get("/targets/{target_id}/structure", response_class=PlainTextResponse)
def structure_coordinates(target_id: uuid.UUID, session: SessionDep) -> str:
    """The coordinates this target's structure viewer renders.

    Served through the API rather than pointed at RCSB from the browser, for two
    reasons: the content hash recorded at attach time is verified on the way
    through, so the viewer cannot show a file that has changed underneath the
    target; and the viewer does not need to know which of several sources a
    structure came from.
    """
    try:
        target = service.require_target(session, target_id)
    except Handled as error:
        raise _fail(error, status=404) from error

    attached = service.structures_for(session, target.id)
    if not attached:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "No structure is attached to this target.",
                "remedy": "Attach a PDB entry or an AlphaFold model on the target page.",
            },
        )

    try:
        fetched = service.refetch_structure(attached[-1])
    except Handled as error:
        raise _fail(error) from error
    return fetched.text


class TrackResidue(BaseModel):
    index: int
    residue: str
    label: str | None


class SequenceTrackOut(BaseModel):
    target_id: uuid.UUID
    scheme_label: str | None
    residues: list[TrackResidue]
    schemes: list[dict[str, Any]]


@router.get("/targets/{target_id}/track", response_model=SequenceTrackOut)
def sequence_track(target_id: uuid.UUID, session: SessionDep) -> SequenceTrackOut:
    """Per-residue view for the linear sequence track."""
    try:
        target = service.require_target(session, target_id)
    except Handled as error:
        raise _fail(error, status=404) from error

    schemes = service.schemes_for(session, target.id)
    canonical = next((scheme for scheme in schemes if scheme.is_canonical), None)

    return SequenceTrackOut(
        target_id=target.id,
        scheme_label=canonical.label if canonical else None,
        residues=[
            TrackResidue(
                index=index + 1,
                residue=residue,
                label=(service.label_at(canonical, index + 1) if canonical else None),
            )
            for index, residue in enumerate(target.sequence)
        ],
        schemes=[
            {
                "id": str(scheme.id),
                "label": scheme.label,
                "kind": scheme.kind.value,
                "is_canonical": scheme.is_canonical,
                "labels": scheme.offsets.get("labels", []),
            }
            for scheme in schemes
        ],
    )
