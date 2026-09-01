"""Append-only provenance.

A first-class entity, not a log file. Rows are inserted and never updated or
deleted; corrections are expressed as further events. This is the record a PI reads
to decide whether to sign off on four thousand dollars of ordering budget.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from codonlab.models.base import TimestampedModel
from codonlab.models.enums import ProvenanceEventKind


class ProvenanceEvent(TimestampedModel, table=True):
    kind: ProvenanceEventKind = Field(index=True)
    project_id: uuid.UUID | None = Field(default=None, foreign_key="project.id", index=True)
    run_id: uuid.UUID | None = Field(default=None, foreign_key="run.id", index=True)

    subject_type: str = Field(index=True, description="Entity table name, e.g. 'score'.")
    subject_id: uuid.UUID | None = Field(default=None, index=True)

    actor: str | None = Field(default=None, description="User or system component.")
    payload: dict[str, Any] = Field(
        default_factory=dict,
        sa_type=JSONB,
        nullable=False,
        description="Everything needed to reconstruct what happened: input hashes, "
        "model versions, parameters, and the reason for any override.",
    )
