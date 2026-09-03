"""SQLModel tables for the Codon Lab schema (specification §8).

Importing this package registers every table on ``SQLModel.metadata``, which is what
Alembic's autogenerate compares against. Any new table must be exported here or it
will be silently missing from migrations.
"""

from codonlab.models.base import TimestampedModel, UUIDModel, utcnow
from codonlab.models.enums import (
    AssayKind,
    ConstraintKind,
    Modality,
    NumberingKind,
    ProvenanceEventKind,
    Region,
    RunStatus,
    StageStatus,
    StructureSource,
)
from codonlab.models.experiment import (
    DesignSet,
    DesignSetMember,
    Experiment,
    Measurement,
)
from codonlab.models.identity import User
from codonlab.models.project import (
    Constraint,
    Goal,
    NumberingScheme,
    Project,
    Structure,
    Target,
)
from codonlab.models.provenance import ProvenanceEvent
from codonlab.models.run import ModelVersion, Run, RunStage, Score, Variant

__all__ = [
    "AssayKind",
    "Constraint",
    "ConstraintKind",
    "DesignSet",
    "DesignSetMember",
    "Experiment",
    "Goal",
    "Measurement",
    "Modality",
    "ModelVersion",
    "NumberingKind",
    "NumberingScheme",
    "Project",
    "ProvenanceEvent",
    "ProvenanceEventKind",
    "Region",
    "Run",
    "RunStage",
    "RunStatus",
    "Score",
    "StageStatus",
    "Structure",
    "StructureSource",
    "Target",
    "TimestampedModel",
    "UUIDModel",
    "User",
    "Variant",
    "utcnow",
]
