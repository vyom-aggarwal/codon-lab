"""The integrity rule the whole product rests on.

ARCHITECTURE.md §5: a Score cannot exist without both a ModelVersion and a Run, and
that is enforced by the database rather than by application convention. These tests
assert it on the mapped schema, so a later migration that relaxes the constraint
fails here rather than in production.
"""

from __future__ import annotations

from sqlmodel import SQLModel

import codonlab.models  # noqa: F401  (registers tables on SQLModel.metadata)


def _table(name: str):
    table = SQLModel.metadata.tables.get(name)
    assert table is not None, f"table {name!r} is not registered on SQLModel.metadata"
    return table


def test_score_requires_a_model_version() -> None:
    column = _table("score").c["model_version_id"]
    assert column.nullable is False, "a score without a model version is untraceable"
    targets = {fk.column.table.name for fk in column.foreign_keys}
    assert targets == {"modelversion"}


def test_score_requires_a_run() -> None:
    column = _table("score").c["run_id"]
    assert column.nullable is False, "a score without a run is untraceable"
    targets = {fk.column.table.name for fk in column.foreign_keys}
    assert targets == {"run"}


def test_score_has_no_cascade_delete_to_provenance_parents() -> None:
    """Deleting a model version or run must be refused while scores reference it.

    Postgres defaults to NO ACTION, so the requirement is that nothing has set an
    ON DELETE rule that would silently discard the provenance trail.
    """
    score = _table("score")
    for column_name in ("model_version_id", "run_id"):
        for fk in score.c[column_name].foreign_keys:
            assert fk.ondelete in (None, "RESTRICT", "NO ACTION"), (
                f"score.{column_name} would discard provenance on delete: {fk.ondelete}"
            )


def test_score_is_unique_per_variant_model_and_run() -> None:
    """Re-running must not silently accumulate duplicate numbers for the same cell."""
    constraints = {c.name for c in _table("score").constraints}
    assert "uq_score" in constraints


def test_every_specified_entity_exists() -> None:
    """Specification §8 lists the entities this schema must carry."""
    expected = {
        "project",
        "target",
        "numberingscheme",
        "structure",
        "constraint",
        "goal",
        "run",
        "runstage",
        "modelversion",
        "variant",
        "score",
        "designset",
        "designsetmember",
        "experiment",
        "measurement",
        "provenanceevent",
    }
    missing = expected - set(SQLModel.metadata.tables)
    assert not missing, f"missing tables: {sorted(missing)}"


def test_measurement_variant_is_nullable() -> None:
    """Bench rows that fail to join must survive import for manual resolution,
    rather than being dropped on the floor."""
    assert _table("measurement").c["variant_id"].nullable is True


def test_goal_confirmation_is_recorded() -> None:
    """No run may start from an unconfirmed parse, so confirmation must be a stored
    fact and not an ephemeral UI state."""
    assert "confirmed_at" in _table("goal").c
    assert _table("goal").c["confirmed_at"].nullable is True
