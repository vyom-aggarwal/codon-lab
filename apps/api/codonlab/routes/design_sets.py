"""Design sets over HTTP. No business logic here — see ARCHITECTURE.md §3.

Every pair flag this module returns carries its own proximity state, and
`unknown` is one of the three. A client cannot receive a pair with no flag and
conclude the residues are far apart, because there is no such shape in the
response: a pair is `within`, `beyond`, or `unknown` with the reason attached.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlmodel import Session

from codonlab.db import get_session
from codonlab.ownership import OWNERSHIP
from codonlab.services import design_sets as service
from codonlab.services import exports as export_service
from codonlab.services.targets import ServiceError

# Ownership is enforced for the whole router rather than per handler: a
# route added later cannot forget to opt in. See codonlab/ownership.py.
router = APIRouter(tags=["design-sets"], dependencies=[OWNERSHIP])
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


class PairFlagOut(BaseModel):
    a_code: str
    b_code: str
    a_position: int
    b_position: int
    #: `within` | `beyond` | `unknown`. Three states on purpose — see the module
    #: docstring and `domain/epistasis.Proximity`.
    proximity: str
    separation_angstrom: float | None
    #: Why the separation is unknown. Null unless `proximity` is `unknown`.
    reason: str | None


class AdditiveOut(BaseModel):
    metric: str
    label: str
    unit: str | None
    sign_convention: str
    #: Null whenever any component lacks a value. Never a partial sum.
    total: float | None
    contributions: list[dict[str, Any]]
    missing: list[str]
    #: The additivity statement. Always present, never empty.
    assumption: str
    interval_note: str


class MemberOut(BaseModel):
    variant_id: uuid.UUID
    code: str
    hgvs: str
    mutations: list[str]
    sequence_positions: list[int]
    is_stacked: bool
    included_via_override: bool
    override_reason: str | None
    pairs: list[PairFlagOut]
    additive: list[AdditiveOut]


class CostLineOut(BaseModel):
    description: str
    quantity: int
    length: int
    unit: str
    amount: float | None
    unpriced_reason: str | None


class CostOut(BaseModel):
    currency: str | None
    #: Null when anything is unpriced. The application never invents a price.
    total: float | None
    lines: list[CostLineOut]
    unavailable_reason: str | None
    budget_amount: float | None
    budget_currency: str | None
    over_budget: bool | None
    remaining: float | None


class WarningOut(BaseModel):
    """The epistasis warning, as data rather than copy.

    Specification §5.7 requires it to be unmissable. It is returned with the set
    rather than assembled by a component, so a second screen cannot render a
    stacked design without it.
    """

    stacked_designs: int
    assumption: str
    cutoff_angstrom: float
    distance_convention: str
    pairs_total: int
    pairs_within_cutoff: int
    pairs_unknown: int


class DesignSetOut(BaseModel):
    design_set_id: uuid.UUID
    project_id: uuid.UUID
    run_id: uuid.UUID
    name: str
    note: str | None
    #: Rendered beside every mutation code, for the life of the project.
    scheme_label: str
    members: list[MemberOut]
    warning: WarningOut
    cost: CostOut
    geometry_manifest: dict[str, Any]
    geometry_note: str | None
    is_demo: bool


class DesignSetSummaryOut(BaseModel):
    design_set_id: uuid.UUID
    project_id: uuid.UUID
    run_id: uuid.UUID
    name: str
    note: str | None
    budget_amount: float | None
    budget_currency: str | None


class CreateDesignSetIn(BaseModel):
    name: str
    note: str | None = None
    budget_amount: float | None = None
    budget_currency: str | None = None


class AddMembersIn(BaseModel):
    codes: list[str] = Field(min_length=1)
    #: Specification §7: a constrained position needs an explicit override, and
    #: the override is logged with the reason.
    override: bool = False
    override_reason: str | None = None


class StackIn(BaseModel):
    codes: list[str] = Field(min_length=2)
    size: int = Field(ge=2)
    limit: int = Field(default=service.DEFAULT_STACK_LIMIT, ge=1, le=5000)


class StackOut(BaseModel):
    design_set_id: uuid.UUID
    #: What was left out and why. Never empty when anything was skipped.
    notes: list[str]


def _view_out(view: service.DesignSetView) -> DesignSetOut:
    return DesignSetOut(
        design_set_id=view.design_set_id,
        project_id=view.project_id,
        run_id=view.run_id,
        name=view.name,
        note=view.note,
        scheme_label=view.scheme_label,
        members=[
            MemberOut(
                variant_id=member.variant_id,
                code=member.code,
                hgvs=member.hgvs,
                mutations=list(member.mutations),
                sequence_positions=list(member.sequence_positions),
                is_stacked=member.is_stacked,
                included_via_override=member.included_via_override,
                override_reason=member.override_reason,
                pairs=[PairFlagOut(**flag.to_json()) for flag in member.pairs],
                additive=[AdditiveOut(**estimate.to_json()) for estimate in member.additive],
            )
            for member in view.members
        ],
        warning=WarningOut(
            stacked_designs=int(view.warning["stacked_designs"]),
            assumption=str(view.warning["assumption"]),
            cutoff_angstrom=float(view.warning["cutoff_angstrom"]),
            distance_convention=str(view.warning["distance_convention"]),
            pairs_total=int(view.warning["pairs_total"]),
            pairs_within_cutoff=int(view.warning["pairs_within_cutoff"]),
            pairs_unknown=int(view.warning["pairs_unknown"]),
        ),
        cost=CostOut(**view.cost.to_json()),
        geometry_manifest=dict(view.geometry_manifest),
        geometry_note=view.geometry_note,
        is_demo=view.is_demo,
    )


# --------------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------------- #


@router.post("/runs/{run_id}/design-sets", response_model=DesignSetSummaryOut, status_code=201)
def create_design_set(
    run_id: uuid.UUID, body: CreateDesignSetIn, session: SessionDep
) -> DesignSetSummaryOut:
    """Start a design set from a run's ranking."""
    try:
        design_set = service.create(
            session,
            run_id=run_id,
            name=body.name,
            note=body.note,
            budget_amount=body.budget_amount,
            budget_currency=body.budget_currency,
        )
    except ServiceError as error:
        raise _fail(error) from error
    return DesignSetSummaryOut(
        design_set_id=design_set.id,
        project_id=design_set.project_id,
        run_id=design_set.run_id,
        name=design_set.name,
        note=design_set.note,
        budget_amount=design_set.budget_amount,
        budget_currency=design_set.budget_currency,
    )


@router.get("/runs/{run_id}/design-sets", response_model=list[DesignSetSummaryOut])
def list_design_sets(run_id: uuid.UUID, session: SessionDep) -> list[DesignSetSummaryOut]:
    return [
        DesignSetSummaryOut(
            design_set_id=design_set.id,
            project_id=design_set.project_id,
            run_id=design_set.run_id,
            name=design_set.name,
            note=design_set.note,
            budget_amount=design_set.budget_amount,
            budget_currency=design_set.budget_currency,
        )
        for design_set in service.for_run(session, run_id)
    ]


@router.get("/design-sets/{design_set_id}", response_model=DesignSetOut)
def get_design_set(design_set_id: uuid.UUID, session: SessionDep) -> DesignSetOut:
    try:
        view = service.view(session, design_set_id=design_set_id)
    except ServiceError as error:
        raise _fail(error, status=404) from error
    return _view_out(view)


@router.post("/design-sets/{design_set_id}/members", response_model=DesignSetOut)
def add_members(
    design_set_id: uuid.UUID, body: AddMembersIn, session: SessionDep
) -> DesignSetOut:
    """Add designs to a set.

    Refuses a constrained position without an explicit override and a stated
    reason, and records every override as a `ProvenanceEvent`.
    """
    try:
        service.add_members(
            session,
            design_set_id=design_set_id,
            codes=body.codes,
            override=body.override,
            override_reason=body.override_reason,
        )
        view = service.view(session, design_set_id=design_set_id)
    except ServiceError as error:
        raise _fail(error) from error
    return _view_out(view)


@router.delete("/design-sets/{design_set_id}/members/{variant_id}", status_code=204)
def remove_member(
    design_set_id: uuid.UUID, variant_id: uuid.UUID, session: SessionDep
) -> Response:
    try:
        service.remove_member(
            session, design_set_id=design_set_id, variant_id=variant_id
        )
    except ServiceError as error:
        raise _fail(error, status=404) from error
    return Response(status_code=204)


@router.post("/design-sets/{design_set_id}/stack", response_model=StackOut)
def stack(design_set_id: uuid.UUID, body: StackIn, session: SessionDep) -> StackOut:
    """Build every combination of `size` mutations from the given codes."""
    try:
        design_set, notes = service.stack_members(
            session,
            design_set_id=design_set_id,
            codes=body.codes,
            size=body.size,
            limit=body.limit,
        )
    except ServiceError as error:
        raise _fail(error) from error
    return StackOut(design_set_id=design_set.id, notes=list(notes))


# --------------------------------------------------------------------------- #
# Exports — specification §6's refusal, built before the export path
# --------------------------------------------------------------------------- #


class RefusalOut(BaseModel):
    what: str
    reason: str
    remedy: str


class PreflightOut(BaseModel):
    """What the wet-lab handoff will and will not emit, asked before it tries.

    `refused` is never silently empty-because-unimplemented: a format missing
    from `available` always appears here with the reason it is missing.
    """

    design_set_id: uuid.UUID
    is_demo: bool
    #: Present whenever any provider in the run fabricates. Every export carries it.
    watermark: str | None
    available: list[str]
    refused: list[RefusalOut]


@router.get("/design-sets/{design_set_id}/exports", response_model=PreflightOut)
def export_preflight(design_set_id: uuid.UUID, session: SessionDep) -> PreflightOut:
    try:
        result = export_service.preflight(session, design_set_id=design_set_id)
    except ServiceError as error:
        raise _fail(error, status=404) from error
    return PreflightOut(
        design_set_id=result.design_set_id,
        is_demo=result.is_demo,
        watermark=result.watermark,
        available=list(result.available),
        refused=[RefusalOut(**refusal.to_json()) for refusal in result.refused],
    )


@router.get("/design-sets/{design_set_id}/exports/design-set.csv")
def export_design_set_csv(design_set_id: uuid.UUID, session: SessionDep) -> Response:
    """The set as a table. Carries no primer sequences, watermarked when synthetic."""
    try:
        body = export_service.design_set_csv(session, design_set_id=design_set_id)
    except ServiceError as error:
        raise _fail(error, status=404) from error
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="design-set-{design_set_id}.csv"'
        },
    )


@router.get("/design-sets/{design_set_id}/exports/primers.csv")
def export_primers_csv(design_set_id: uuid.UUID, session: SessionDep) -> Response:
    """Refuses, with every applicable reason. See `services/exports`.

    A 409 rather than a 404 or a 501: the resource is understood and the request
    is well-formed, but the current state of the run and the target make emitting
    it dishonest. The body carries what would change that.
    """
    try:
        body = export_service.primers_csv(session, design_set_id=design_set_id)
    except ServiceError as error:
        raise _fail(error, status=409) from error
    return Response(content=body, media_type="text/csv; charset=utf-8")
