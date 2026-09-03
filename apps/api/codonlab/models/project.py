"""Project, Target, numbering, structures, constraints, goals."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from codonlab.models.base import TimestampedModel, utc_timestamp
from codonlab.models.enums import ConstraintKind, NumberingKind, StructureSource


class Project(TimestampedModel, table=True):
    name: str = Field(index=True)
    #: Who this project belongs to. Everything else in the schema reaches its
    #: owner through here — a Target has a project_id, a Run has a project_id,
    #: and a Score reaches one through its Run — so this single column is the
    #: whole ownership model and there is no second place to enforce it.
    #:
    #: Nullable, and that is load-bearing rather than laziness. Rows written
    #: before authentication existed have no owner and cannot be assigned one
    #: without inventing a claim about who created them. An unowned project is
    #: visible only when the API is running unauthenticated (local development);
    #: under CODONLAB_AUTH=jwt it belongs to nobody and is served to nobody.
    owner_id: uuid.UUID | None = Field(
        default=None, foreign_key="user.id", index=True, nullable=True
    )
    organism: str | None = Field(default=None)
    objective: str | None = Field(
        default=None,
        description="Short human summary shown in the projects table. The machine-"
        "readable objective lives on Goal.parsed_spec.",
    )
    settings: dict[str, Any] = Field(
        default_factory=dict,
        sa_type=JSONB,
        nullable=False,
        description="Project-level scientific settings, currently the RSA cutoffs "
        "separating core from boundary from surface. Empty means the defaults are "
        "in force. Whatever value is in force when a run executes is copied into "
        "that run's provenance record, so changing it later cannot rewrite what an "
        "earlier run reported.",
    )
    last_activity_at: datetime | None = utc_timestamp(nullable=True)


class Target(TimestampedModel, table=True):
    project_id: uuid.UUID = Field(foreign_key="project.id", index=True, nullable=False)
    name: str
    organism: str | None = Field(default=None)
    uniprot_accession: str | None = Field(default=None, index=True)
    sequence: str = Field(description="One-letter amino acid sequence.")

    # Which scheme is canonical is recorded on NumberingScheme.is_canonical rather
    # than by a column here. A foreign key in this direction would close a cycle
    # with numberingscheme.target_id, leaving the two tables unorderable for
    # creation and every migration touching them needing a deferred constraint.

    @property
    def length(self) -> int:
        return len(self.sequence)


class NumberingScheme(TimestampedModel, table=True):
    """One residue numbering scheme belonging to a target.

    A target normally has several (the UniProt sequence, the PDB author numbering,
    and the numbering of the construct actually on the bench). They disagree, and
    the disagreement is the point: it is reconciled explicitly by the user, never
    inferred. `offsets` maps sequence index to this scheme's label so that
    insertion codes and discontinuous chains survive the round trip.
    """

    __table_args__ = (
        UniqueConstraint("target_id", "kind", "label", name="uq_numbering_target"),
        # At most one canonical scheme per target, enforced by the database. A
        # target with two canonical schemes would make every mutation code on it
        # ambiguous, which is the exact failure this whole subsystem exists to
        # prevent.
        Index(
            "uq_numbering_canonical",
            "target_id",
            unique=True,
            postgresql_where=text("is_canonical"),
        ),
    )

    target_id: uuid.UUID = Field(foreign_key="target.id", index=True, nullable=False)
    kind: NumberingKind = Field(index=True)
    label: str = Field(description="Displayed next to every mutation code, e.g. 'UniProt P62593'.")
    offsets: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB, nullable=False)
    is_canonical: bool = Field(
        default=False,
        description="Set only once numbering reconciliation is complete. Until some "
        "scheme on a target carries this, the target cannot be designed against, "
        "because no mutation code on it would be unambiguous.",
    )


class Structure(TimestampedModel, table=True):
    target_id: uuid.UUID = Field(foreign_key="target.id", index=True, nullable=False)
    source: StructureSource
    identifier: str | None = Field(
        default=None, description="PDB id or AlphaFold DB accession where applicable."
    )
    file_path: str | None = Field(default=None)
    chain: str | None = Field(default=None)
    content_hash: str = Field(index=True, description="Content address of the structure file.")


class Constraint(TimestampedModel, table=True):
    """A hard filter over positions.

    Filtered-out variants are always retrievable with the reason shown, so a
    constraint records enough context to explain itself later.
    """

    target_id: uuid.UUID = Field(foreign_key="target.id", index=True, nullable=False)
    kind: ConstraintKind = Field(index=True)
    positions: list[int] = Field(
        default_factory=list,
        sa_type=JSONB,
        nullable=False,
        description="Positions in the target's canonical numbering scheme.",
    )
    note: str | None = Field(default=None)
    created_by: str | None = Field(default=None)


class Goal(TimestampedModel, table=True):
    """Free text in, structured objective out — with a confirmation gate between.

    `confirmed_at` is null until the user has seen the parse rendered back as chips
    and accepted it. No run may start from an unconfirmed parse; the product exists
    to not silently guess what "more thermostable" meant.
    """

    project_id: uuid.UUID = Field(foreign_key="project.id", index=True, nullable=False)
    target_id: uuid.UUID = Field(foreign_key="target.id", index=True, nullable=False)
    raw_text: str
    parsed_spec: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB, nullable=False)
    confirmed_at: datetime | None = utc_timestamp(nullable=True)

    @property
    def is_confirmed(self) -> bool:
        return self.confirmed_at is not None
