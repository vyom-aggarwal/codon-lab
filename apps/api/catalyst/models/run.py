"""Runs, model versions, variants, and scores.

The central integrity rule of the product lives in this file: a Score cannot exist
without both a ModelVersion and a Run. It is enforced by NOT NULL foreign keys, not
by application convention, because it is what allows any number in the interface to
be traced to the model and run that produced it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from catalyst.models.base import TimestampedModel, utc_timestamp
from catalyst.models.enums import Modality, Region, RunStatus, StageStatus


class ModelVersion(TimestampedModel, table=True):
    """An exact, citable identity for something that produced numbers."""

    __table_args__ = (
        UniqueConstraint("model_id", "version", "weights_hash", name="uq_model_version"),
    )

    model_id: str = Field(index=True, description="Stable provider id, e.g. 'esm2_650m'.")
    name: str
    version: str
    weights_hash: str = Field(description="Hash of the exact weights used.")
    modality: Modality = Field(index=True)
    citation: str
    is_mock: bool = Field(
        default=False,
        index=True,
        description="True for MockProvider output. Drives the persistent demo banner, "
        "the per-number badge, export watermarking, and the refusal to emit primers. "
        "No scientific number is ever fabricated outside a provider marked here.",
    )


class Run(TimestampedModel, table=True):
    """A design run.

    A partial unique index on (goal_id, input_hash), restricted to the statuses
    that mean the work is happening or has happened, makes starting a run
    idempotent on its content address. Declared in migration 0003 rather than
    here because SQLModel cannot express the `WHERE` clause, and the restriction
    is the point: a failed run leaves the index so a retry after a genuine
    failure starts fresh.
    """

    project_id: uuid.UUID = Field(foreign_key="project.id", index=True, nullable=False)
    target_id: uuid.UUID = Field(foreign_key="target.id", index=True, nullable=False)
    goal_id: uuid.UUID = Field(foreign_key="goal.id", index=True, nullable=False)
    status: RunStatus = Field(default=RunStatus.PENDING, index=True)
    config: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB, nullable=False)
    input_hash: str = Field(
        index=True,
        description="Content address over model versions + inputs. Results are cached "
        "on this, which is what makes a re-run with one changed parameter both cheap "
        "and exactly diffable against its predecessor.",
    )
    parent_run_id: uuid.UUID | None = Field(default=None, foreign_key="run.id")
    started_at: datetime | None = utc_timestamp(nullable=True)
    finished_at: datetime | None = utc_timestamp(nullable=True)
    error: str | None = Field(default=None)


class RunStage(TimestampedModel, table=True):
    """One row per pipeline stage, shown as the vertical stage list in the run view."""

    run_id: uuid.UUID = Field(foreign_key="run.id", index=True, nullable=False)
    ordinal: int
    name: str = Field(description="e.g. 'retrieve structure', 'build MSA', 'aggregate'.")
    model_version_id: uuid.UUID | None = Field(default=None, foreign_key="modelversion.id")
    status: StageStatus = Field(default=StageStatus.PENDING, index=True)
    input_hash: str | None = Field(default=None)
    runtime_ms: int | None = Field(default=None)
    logs: str | None = Field(default=None)
    error: str | None = Field(default=None)


class Variant(TimestampedModel, table=True):
    """A candidate, identified by its mutation list in the target's canonical scheme."""

    target_id: uuid.UUID = Field(foreign_key="target.id", index=True, nullable=False)
    mutations: list[str] = Field(
        default_factory=list,
        sa_type=JSONB,
        nullable=False,
        description="Mutation codes such as ['A123V'], in the canonical numbering "
        "scheme recorded on the target. Rendered alongside p.Ala123Val and always "
        "with the scheme label.",
    )
    code: str = Field(
        index=True,
        description="Canonical joined form, e.g. 'A123V/L45M'. Used for the fuzzy join "
        "against uploaded bench measurements.",
    )
    position: int | None = Field(
        default=None, index=True, description="Set for single-point variants only."
    )
    region: Region | None = Field(default=None, index=True)
    features: dict[str, Any] = Field(
        default_factory=dict,
        sa_type=JSONB,
        nullable=False,
        description="Derived features (RSA, conservation, distance to active site, ...). "
        "The rationale shown in the inspector is composed from these actual values, "
        "never from a language model guessing.",
    )


class Score(TimestampedModel, table=True):
    """A number produced by a specific model version during a specific run.

    Both foreign keys are NOT NULL by design. See ARCHITECTURE.md §5 — this is the
    constraint that makes provenance real, and no later migration may relax it.
    """

    __table_args__ = (
        UniqueConstraint("variant_id", "model_version_id", "run_id", "metric", name="uq_score"),
    )

    variant_id: uuid.UUID = Field(foreign_key="variant.id", index=True, nullable=False)
    # No ON DELETE clause: Postgres defaults to NO ACTION, which already refuses to
    # delete a ModelVersion or Run that still has scores hanging off it. That refusal
    # is the desired behaviour — provenance is not allowed to become dangling.
    model_version_id: uuid.UUID = Field(foreign_key="modelversion.id", index=True, nullable=False)
    run_id: uuid.UUID = Field(foreign_key="run.id", index=True, nullable=False)
    metric: str = Field(
        index=True,
        description="e.g. 'ddg_kcal_per_mol', 'esm_llr'. Sign conventions are stated in "
        "the column header and never change.",
    )
    value: float
    uncertainty: float | None = Field(
        default=None,
        description="Standard deviation or half-width of the interval. A bare point "
        "estimate is not acceptable output for a stability prediction.",
    )
    ci_low: float | None = Field(default=None)
    ci_high: float | None = Field(default=None)
