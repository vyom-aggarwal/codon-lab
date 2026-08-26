"""A design set is derived from one run, and a variant is one row.

Two changes, both about making a Phase 7 guarantee structural rather than a
matter of service-layer discipline.

**`designset.run_id`, NOT NULL.** Specification §5.7's builder stacks mutations
and shows an additive total across them. That total is arithmetic over scores,
and a total assembled from two different runs' scores would be untraceable in
exactly the way specification §2.2 forbids — the numbers would each have a
provenance trail and the sum would have none. Requiring the run makes "which run
did these numbers come from" answerable by the schema. The table is empty at this
revision (the feature did not exist before Phase 7), so there is nothing to
backfill.

**`uq_variant_target_code`.** `services/runs._ensure_candidates` already treats a
variant as the same variant whoever proposed it, and reuses rows across runs so
that Phase 8's measured values join to one row rather than one per run. It
enforced that with a read-then-insert, which two concurrent writers can both
pass — the same failure mode migration 0003 fixed for runs. Phase 7 adds a second
writer creating variant rows (stacked designs), so the guarantee is moved into
the database before there are two callers rather than after.

Revision ID: 0004_design_sets
Revises: 0003_run_idempotency
Create Date: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_design_sets"
down_revision: str | None = "0003_run_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Duplicates would block the unique constraint. There should be none —
    # _ensure_candidates has always deduplicated on read — but a constraint added
    # over silently bad data is worse than no constraint, so fail loudly here.
    duplicates = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM ("
                "  SELECT target_id, code FROM variant"
                "  GROUP BY target_id, code HAVING count(*) > 1"
                ") AS d"
            )
        )
        .scalar_one()
    )
    if duplicates:
        raise RuntimeError(
            f"{duplicates} (target, mutation code) pair(s) have more than one variant "
            "row. Merge them before applying this migration — deduplicating "
            "automatically would silently discard whichever scores hang off the "
            "row that lost."
        )

    op.create_unique_constraint("uq_variant_target_code", "variant", ["target_id", "code"])

    op.add_column("designset", sa.Column("run_id", sa.Uuid(), nullable=False))
    op.create_foreign_key(
        "fk_designset_run_id", "designset", "run", ["run_id"], ["id"]
    )
    op.create_index("ix_designset_run_id", "designset", ["run_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_designset_run_id", table_name="designset")
    op.drop_constraint("fk_designset_run_id", "designset", type_="foreignkey")
    op.drop_column("designset", "run_id")
    op.drop_constraint("uq_variant_target_code", "variant", type_="unique")
