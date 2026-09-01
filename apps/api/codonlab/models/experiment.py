"""Design sets and the bench side of the loop: experiments and measurements.

This is the half of the schema that closes the loop. Predictions are cheap; the
lab's own measured values are what eventually decide which predictor this lab
trusts for its chemistry.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from codonlab.models.base import TimestampedModel
from codonlab.models.enums import AssayKind


class DesignSet(TimestampedModel, table=True):
    """A set of variants selected for ordering, derived from one run.

    `run_id` is NOT NULL on purpose. The builder shows an additive total across
    stacked mutations, and that total is arithmetic over scores; assembling it
    from two different runs would produce a number whose components are each
    traceable and whose sum is not. See migration 0004.
    """

    project_id: uuid.UUID = Field(foreign_key="project.id", index=True, nullable=False)
    run_id: uuid.UUID = Field(foreign_key="run.id", index=True, nullable=False)
    name: str
    note: str | None = Field(default=None)
    budget_currency: str | None = Field(default=None)
    budget_amount: float | None = Field(default=None)


class DesignSetMember(TimestampedModel, table=True):
    __table_args__ = (UniqueConstraint("design_set_id", "variant_id", name="uq_design_set_member"),)

    design_set_id: uuid.UUID = Field(foreign_key="designset.id", index=True, nullable=False)
    variant_id: uuid.UUID = Field(foreign_key="variant.id", index=True, nullable=False)
    included_via_override: bool = Field(
        default=False,
        description="True when the variant sits at a constrained position and the user "
        "explicitly overrode the constraint. Every override is logged as a "
        "ProvenanceEvent as well.",
    )
    override_reason: str | None = Field(default=None)


class Experiment(TimestampedModel, table=True):
    project_id: uuid.UUID = Field(foreign_key="project.id", index=True, nullable=False)
    design_set_id: uuid.UUID | None = Field(default=None, foreign_key="designset.id", index=True)
    assay: AssayKind = Field(index=True)
    protocol: str | None = Field(default=None)
    performed_on: date | None = Field(default=None)
    operator: str | None = Field(default=None)


class Measurement(TimestampedModel, table=True):
    """A value from the bench.

    Never produced by a model, never imputed. `variant_id` is nullable so that rows
    which failed to join to a known variant survive import and can be resolved by
    hand in the join UI, rather than being silently dropped.
    """

    experiment_id: uuid.UUID = Field(foreign_key="experiment.id", index=True, nullable=False)
    variant_id: uuid.UUID | None = Field(default=None, foreign_key="variant.id", index=True)
    raw_label: str | None = Field(
        default=None, description="The mutation code exactly as it appeared in the upload."
    )
    metric: str = Field(index=True, description="e.g. 'tm_celsius', 'kcat_km', 'yield_mg_per_l'.")
    unit: str
    value: float
    sd: float | None = Field(default=None)
    replicate: int | None = Field(default=None)
    extra: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB, nullable=False)
