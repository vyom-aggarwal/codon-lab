"""Projects list — the data behind screen §5.1."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, true
from sqlmodel import Session, col

from codonlab.auth import CurrentUser
from codonlab.config import get_settings
from codonlab.db import get_session
from codonlab.models import Experiment, Measurement, Project, Run, Target, User
from codonlab.ownership import OWNERSHIP
from codonlab.services import projects as project_service
from codonlab.services import targets as service

# Ownership is enforced for the whole router rather than per handler: a
# route added later cannot forget to opt in. See codonlab/ownership.py.
router = APIRouter(prefix="/projects", tags=["projects"], dependencies=[OWNERSHIP])


class ProjectRow(BaseModel):
    id: uuid.UUID
    name: str
    organism: str | None
    objective: str | None
    target_name: str | None
    target_count: int
    run_count: int
    measured_variant_count: int
    last_activity_at: datetime | None
    created_at: datetime


def _visible_to(user: User) -> Any:
    """The projects this caller may see.

    Under `CODONLAB_AUTH=jwt` that is exactly the ones they own. Unowned
    projects — rows written before authentication existed — belong to nobody and
    are excluded, because assigning them to whoever happens to log in first
    would be inventing a claim about authorship. See migration 0006_ownership.

    Running unauthenticated, every project is visible: that is a single-user
    local instance, and `config` refuses to start in that mode once CORS names a
    non-local origin.
    """
    if not get_settings().auth_required:
        return true()
    return col(Project.owner_id) == user.id


@router.get("", response_model=list[ProjectRow])
def list_projects(
    user: CurrentUser,
    session: Session = Depends(get_session),
) -> list[ProjectRow]:
    """One row per project, with the counts the table shows.

    Counts are computed as correlated scalar subqueries rather than joins, so a
    project with many targets does not multiply its own run count.

    Model attributes are wrapped in ``col()`` throughout: SQLModel declares fields
    with their Python type, so ``Run.project_id == Project.id`` reads to a type
    checker as a bool comparison rather than a SQL expression.
    """
    run_count = (
        select(func.count(col(Run.id)))
        .where(col(Run.project_id) == col(Project.id))
        .scalar_subquery()
    )
    target_count = (
        select(func.count(col(Target.id)))
        .where(col(Target.project_id) == col(Project.id))
        .scalar_subquery()
    )
    # A measured variant is one this lab has actually put on the bench and recorded a
    # value for. Rows that failed to join to a known variant are excluded — they are
    # unresolved imports, not measurements of anything yet.
    measured_variant_count = (
        select(func.count(func.distinct(col(Measurement.variant_id))))
        .select_from(Measurement)
        .join(Experiment, col(Experiment.id) == col(Measurement.experiment_id))
        .where(
            col(Experiment.project_id) == col(Project.id),
            col(Measurement.variant_id).is_not(None),
        )
        .scalar_subquery()
    )
    first_target_name = (
        select(col(Target.name))
        .where(col(Target.project_id) == col(Project.id))
        .order_by(col(Target.created_at))
        .limit(1)
        .scalar_subquery()
    )

    statement = select(
        col(Project.id),
        col(Project.name),
        col(Project.organism),
        col(Project.objective),
        first_target_name.label("target_name"),
        target_count.label("target_count"),
        run_count.label("run_count"),
        measured_variant_count.label("measured_variant_count"),
        col(Project.last_activity_at),
        col(Project.created_at),
    ).where(
        # The list is the one endpoint the router-level ownership dependency
        # cannot cover: there is no id in the path to check, so the filter has
        # to be in the query. Getting this wrong would not raise — it would
        # quietly show every project in the database to everybody, which is the
        # exact failure this whole change exists to prevent.
        _visible_to(user)
    ).order_by(
        # Projects with recent bench activity first; brand-new projects fall back to
        # their creation time rather than sorting to the bottom.
        func.coalesce(col(Project.last_activity_at), col(Project.created_at)).desc()
    )

    rows = session.execute(statement).all()
    return [ProjectRow.model_validate(row, from_attributes=True) for row in rows]


class CreateProjectIn(BaseModel):
    name: str
    organism: str | None = None
    objective: str | None = None


class TargetSummary(BaseModel):
    id: uuid.UUID
    name: str
    organism: str | None
    uniprot_accession: str | None
    length: int
    #: False until a canonical numbering scheme is confirmed. The project page
    #: shows this prominently: an unreconciled target cannot be designed against.
    is_designable: bool
    canonical_scheme_label: str | None


class RsaCutoffs(BaseModel):
    """Where core stops and surface starts.

    A scientific decision, so it is visible and editable rather than compiled in,
    and whatever is in force when a run executes is copied into that run's
    feature provenance record.
    """

    core_max: float = Field(ge=0.0, le=1.0)
    surface_min: float = Field(ge=0.0, le=1.0)


class ProjectDetail(BaseModel):
    id: uuid.UUID
    name: str
    organism: str | None
    objective: str | None
    created_at: datetime
    targets: list[TargetSummary]
    rsa_cutoffs: RsaCutoffs


@router.post("", response_model=ProjectDetail, status_code=201)
def create_project(
    body: CreateProjectIn,
    user: CurrentUser,
    session: Session = Depends(get_session),
) -> ProjectDetail:
    try:
        project = service.create_project(
            session,
            name=body.name,
            organism=body.organism,
            objective=body.objective,
            owner_id=user.id,
        )
    except service.ServiceError as error:
        raise HTTPException(
            status_code=400,
            detail={"message": str(error), "remedy": error.remedy},
        ) from error
    return _detail(session, project)


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(project_id: uuid.UUID, session: Session = Depends(get_session)) -> ProjectDetail:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "That project does not exist.",
                "remedy": "Open one from the projects table.",
            },
        )
    return _detail(session, project)


def _detail(session: Session, project: Project) -> ProjectDetail:
    # session.execute rather than session.exec: `select` here is SQLAlchemy's,
    # imported for the aggregate query above, and exec() is typed for SQLModel's.
    targets = (
        session.execute(
            select(Target)
            .where(col(Target.project_id) == project.id)
            .order_by(col(Target.created_at))
        )
        .scalars()
        .all()
    )

    summaries: list[TargetSummary] = []
    for target in targets:
        canonical = service.canonical_scheme(session, target.id)
        summaries.append(
            TargetSummary(
                id=target.id,
                name=target.name,
                organism=target.organism,
                uniprot_accession=target.uniprot_accession,
                length=len(target.sequence),
                is_designable=canonical is not None,
                canonical_scheme_label=canonical.label if canonical else None,
            )
        )

    cutoffs = project_service.cutoffs_for(project)
    return ProjectDetail(
        id=project.id,
        name=project.name,
        organism=project.organism,
        objective=project.objective,
        created_at=project.created_at,
        targets=summaries,
        rsa_cutoffs=RsaCutoffs(core_max=cutoffs.core_max, surface_min=cutoffs.surface_min),
    )


@router.post("/{project_id}/settings/rsa-cutoffs", response_model=ProjectDetail)
def set_rsa_cutoffs(
    project_id: uuid.UUID, body: RsaCutoffs, session: Session = Depends(get_session)
) -> ProjectDetail:
    """Change the burial cutoffs for this project.

    Earlier runs are untouched: each one recorded the values that were in force
    when it executed, so a run remains a record of what happened rather than a
    view through today's settings.
    """
    try:
        project = project_service.update_cutoffs(
            session,
            project_id=project_id,
            core_max=body.core_max,
            surface_min=body.surface_min,
        )
    except service.ServiceError as error:
        raise HTTPException(
            status_code=400,
            detail={"message": str(error), "remedy": error.remedy},
        ) from error
    return _detail(session, project)
