"""Project-level scientific settings.

Currently one setting: the RSA cutoffs separating core from boundary from
surface. It lives here rather than as a constant because it is a domain
decision, and domain decisions in this product are visible, editable and
recorded — not compiled in.

Changing the setting does not change what an earlier run reported. The cutoffs
in force are copied into each run's feature provenance record when it executes,
so a run remains a record of what happened under the values that were set at the
time.
"""

from __future__ import annotations

import uuid

from sqlmodel import Session

from codonlab.domain.regions import CutoffError, RegionCutoffs
from codonlab.models import Project, ProvenanceEvent, ProvenanceEventKind
from codonlab.services.targets import ServiceError, require_project


def cutoffs_for(project: Project) -> RegionCutoffs:
    return RegionCutoffs.from_settings(project.settings)


def update_cutoffs(
    session: Session,
    *,
    project_id: uuid.UUID,
    core_max: float,
    surface_min: float,
    actor: str | None = None,
) -> Project:
    """Set the burial cutoffs for this project, recording the change."""
    project = require_project(session, project_id)
    before = cutoffs_for(project)

    try:
        cutoffs = RegionCutoffs(core_max=core_max, surface_min=surface_min)
    except CutoffError as error:
        raise ServiceError(str(error), error.remedy) from error

    project.settings = {**dict(project.settings), **cutoffs.to_settings()}
    session.add(project)

    # A threshold change is an event, not a silent edit: it changes how every
    # future run classifies every residue.
    session.add(
        ProvenanceEvent(
            kind=ProvenanceEventKind.PROJECT_CREATED,
            project_id=project.id,
            subject_type="project_settings",
            subject_id=project.id,
            actor=actor,
            payload={
                "setting": "rsa_cutoffs",
                "before": before.as_manifest(),
                "after": cutoffs.as_manifest(),
            },
        )
    )
    session.commit()
    session.refresh(project)
    return project
