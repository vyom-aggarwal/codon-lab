"""Goal composer and constraints over HTTP. No business logic here."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from codonlab.db import get_session
from codonlab.domain.goal import EXPECTATIONS, restate, spec_from_json
from codonlab.models import Constraint, ConstraintKind, Goal
from codonlab.ownership import OWNERSHIP
from codonlab.services import constraints as constraint_service
from codonlab.services import goals as service
from codonlab.services.targets import ServiceError
from codonlab.sources.uniprot import SourceError

# Ownership is enforced for the whole router rather than per handler: a
# route added later cannot forget to opt in. See codonlab/ownership.py.
router = APIRouter(tags=["goals"], dependencies=[OWNERSHIP])
SessionDep = Annotated[Session, Depends(get_session)]
Handled = (ServiceError, SourceError)


def _fail(error: Exception, status: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={
            "message": str(error),
            "remedy": getattr(error, "remedy", "Check the input and try again."),
        },
    )


class GoalOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    target_id: uuid.UUID
    raw_text: str
    spec: dict[str, Any]
    restatement: str
    method: str
    note: str
    #: Fields a run cannot proceed without. Empty means the parse is complete.
    missing_required: list[str]
    #: The Phase 3 gate, surfaced so the UI never has to infer it.
    is_confirmed: bool
    confirmed_at: datetime | None
    expectations: dict[str, list[str]]

    @classmethod
    def of(cls, goal: Goal) -> GoalOut:
        stored = dict(goal.parsed_spec)
        spec = spec_from_json(stored)
        return cls(
            id=goal.id,
            project_id=goal.project_id,
            target_id=goal.target_id,
            raw_text=goal.raw_text,
            spec=stored,
            restatement=stored.get("restatement") or restate(spec),
            method=stored.get("method", "rules"),
            note=stored.get("note", ""),
            missing_required=list(spec.missing_required),
            is_confirmed=goal.confirmed_at is not None,
            confirmed_at=goal.confirmed_at,
            expectations=EXPECTATIONS,
        )


class CreateGoalIn(BaseModel):
    text: str


class UpdateGoalIn(BaseModel):
    """The edited chips, as the same shape the parse produced."""

    spec: dict[str, Any]


@router.post("/targets/{target_id}/goals", response_model=GoalOut, status_code=201)
def create_goal(target_id: uuid.UUID, body: CreateGoalIn, session: SessionDep) -> GoalOut:
    try:
        goal = service.create(session, target_id=target_id, text=body.text)
    except Handled as error:
        raise _fail(error) from error
    return GoalOut.of(goal)


@router.get("/targets/{target_id}/goals", response_model=list[GoalOut])
def list_goals(target_id: uuid.UUID, session: SessionDep) -> list[GoalOut]:
    return [GoalOut.of(goal) for goal in service.goals_for(session, target_id)]


@router.get("/goals/{goal_id}", response_model=GoalOut)
def get_goal(goal_id: uuid.UUID, session: SessionDep) -> GoalOut:
    try:
        goal = service.require_goal(session, goal_id)
    except Handled as error:
        raise _fail(error, status=404) from error
    return GoalOut.of(goal)


@router.post("/goals/{goal_id}", response_model=GoalOut)
def update_goal(goal_id: uuid.UUID, body: UpdateGoalIn, session: SessionDep) -> GoalOut:
    """Replace the parse with edited chips. Clears any confirmation."""
    try:
        goal = service.update_spec(session, goal_id=goal_id, spec=spec_from_json(body.spec))
    except Handled as error:
        raise _fail(error) from error
    return GoalOut.of(goal)


@router.post("/goals/{goal_id}/confirm", response_model=GoalOut)
def confirm_goal(goal_id: uuid.UUID, session: SessionDep) -> GoalOut:
    try:
        goal = service.confirm(session, goal_id=goal_id)
    except Handled as error:
        raise _fail(error) from error
    return GoalOut.of(goal)


class RunPreflightOut(BaseModel):
    """What the run pipeline will be allowed to do — the gate, queryable.

    Phase 4 calls `goals.require_confirmed` directly; this endpoint exists so
    the UI can disable the run button for the same reason the API would refuse,
    rather than for a reason it invented.
    """

    can_start: bool
    reason: str | None
    remedy: str | None


@router.get("/goals/{goal_id}/preflight", response_model=RunPreflightOut)
def preflight(goal_id: uuid.UUID, session: SessionDep) -> RunPreflightOut:
    try:
        service.require_confirmed(session, goal_id)
    except ServiceError as error:
        return RunPreflightOut(can_start=False, reason=str(error), remedy=error.remedy)
    return RunPreflightOut(can_start=True, reason=None, remedy=None)


# --------------------------------------------------------------------------- #
# Constraints
# --------------------------------------------------------------------------- #


class ConstraintOut(BaseModel):
    id: uuid.UUID
    kind: str
    positions: list[int]
    labels: list[str]
    note: str | None


class SuggestionOut(BaseModel):
    kind: str
    positions: list[int]
    labels: list[str]
    residues: list[str]
    source: str
    note: str


class AcceptConstraintIn(BaseModel):
    kind: str
    positions: list[int]
    note: str | None = None


def _constraint_out(session: Session, constraint: Constraint) -> ConstraintOut:
    from codonlab.services.targets import canonical_scheme, label_at

    scheme = canonical_scheme(session, constraint.target_id)
    labels = [
        (label_at(scheme, position) if scheme else None) or str(position)
        for position in constraint.positions
    ]
    return ConstraintOut(
        id=constraint.id,
        kind=constraint.kind.value,
        positions=[int(position) for position in constraint.positions],
        labels=labels,
        note=constraint.note,
    )


@router.get("/targets/{target_id}/constraints", response_model=list[ConstraintOut])
def list_constraints(target_id: uuid.UUID, session: SessionDep) -> list[ConstraintOut]:
    return [
        _constraint_out(session, constraint)
        for constraint in constraint_service.constraints_for(session, target_id)
    ]


@router.get("/targets/{target_id}/constraints/suggestions", response_model=list[SuggestionOut])
def suggest_constraints(target_id: uuid.UUID, session: SessionDep) -> list[SuggestionOut]:
    """Proposals read from UniProt. Writes nothing."""
    try:
        suggestions = constraint_service.suggest_from_uniprot(session, target_id=target_id)
    except Handled as error:
        raise _fail(error) from error
    return [SuggestionOut(**suggestion.to_json()) for suggestion in suggestions]


@router.post("/targets/{target_id}/constraints", response_model=ConstraintOut, status_code=201)
def add_constraint(
    target_id: uuid.UUID, body: AcceptConstraintIn, session: SessionDep
) -> ConstraintOut:
    try:
        constraint = constraint_service.accept(
            session,
            target_id=target_id,
            kind=ConstraintKind(body.kind),
            positions=body.positions,
            note=body.note,
        )
    except ValueError as error:
        raise _fail(error) from error
    except Handled as error:
        raise _fail(error) from error
    return _constraint_out(session, constraint)


@router.delete("/constraints/{constraint_id}", status_code=204)
def delete_constraint(constraint_id: uuid.UUID, session: SessionDep) -> None:
    try:
        constraint_service.remove(session, constraint_id=constraint_id)
    except Handled as error:
        raise _fail(error, status=404) from error
