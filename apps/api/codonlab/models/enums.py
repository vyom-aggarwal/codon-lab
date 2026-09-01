"""Controlled vocabularies.

Every value here is named by the product specification. Nothing in this file is a
scientific threshold — thresholds (for example the relative-solvent-accessibility
cutoffs that separate core from boundary from surface) are deliberately absent and
are decided with the domain owner before the layer that needs them is written.
"""

from __future__ import annotations

from enum import StrEnum


class NumberingKind(StrEnum):
    """Residue numbering schemes that must be reconciled before any design work.

    Off-by-one numbering is the most expensive error this application can make, so
    the scheme is always explicit and never inferred.
    """

    SEQUENCE = "sequence"
    PDB_AUTHOR = "pdb_author"
    CONSTRUCT = "construct"


class ConstraintKind(StrEnum):
    """Annotations that act as hard filters during design."""

    CATALYTIC = "catalytic"
    LIGAND_CONTACT = "ligand_contact"
    COFACTOR_CONTACT = "cofactor_contact"
    BINDING_INTERFACE = "binding_interface"
    DISULFIDE = "disulfide"
    SIGNAL_PEPTIDE = "signal_peptide"
    PURIFICATION_TAG = "purification_tag"
    DO_NOT_TOUCH = "do_not_touch"


class StructureSource(StrEnum):
    ALPHAFOLD_DB = "alphafold_db"
    UPLOADED_PDB = "uploaded_pdb"
    ESMFOLD = "esmfold"
    PDB = "pdb"


class Modality(StrEnum):
    """What a predictor is for. A generative provider is never presented as a
    point-mutation oracle."""

    STABILITY = "stability"
    FITNESS = "fitness"
    STRUCTURE = "structure"
    GENERATIVE = "generative"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class Region(StrEnum):
    """Burial class, derived from relative solvent accessibility.

    The cutoffs are a domain decision and are not encoded yet — engineering
    strategy differs by region (core packing vs surface charge), so getting them
    wrong changes the advice the product gives.
    """

    CORE = "core"
    BOUNDARY = "boundary"
    SURFACE = "surface"


class ProvenanceEventKind(StrEnum):
    """Append-only audit vocabulary. `CONSTRAINT_OVERRIDDEN` exists because the
    specification requires every override of a constrained position to be logged."""

    PROJECT_CREATED = "project_created"
    TARGET_ADDED = "target_added"
    NUMBERING_RECONCILED = "numbering_reconciled"
    CONSTRAINT_ADDED = "constraint_added"
    CONSTRAINT_OVERRIDDEN = "constraint_overridden"
    GOAL_PARSED = "goal_parsed"
    GOAL_CONFIRMED = "goal_confirmed"
    RUN_STARTED = "run_started"
    RUN_STAGE_COMPLETED = "run_stage_completed"
    #: Derived structural features and the full parameter manifest that produced
    #: them. A relative solvent accessibility is as traceable as a model score:
    #: the reference table, its DOI, the radii set, the cutoffs in force and the
    #: coordinate set all live in this event's payload.
    FEATURES_COMPUTED = "features_computed"
    RUN_COMPLETED = "run_completed"
    RUN_CANCELLED = "run_cancelled"
    SCORES_WRITTEN = "scores_written"
    DESIGN_SET_CREATED = "design_set_created"
    EXPORT_GENERATED = "export_generated"
    MEASUREMENTS_IMPORTED = "measurements_imported"


class AssayKind(StrEnum):
    THERMAL_STABILITY = "thermal_stability"
    ACTIVITY = "activity"
    EXPRESSION = "expression"
    BINDING = "binding"
    OTHER = "other"
