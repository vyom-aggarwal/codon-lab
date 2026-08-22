"""Starting a run is idempotent on its content address.

`POST` is not idempotent by default. A client that retries after a lost response
— a dropped connection, a proxy timeout, a double-clicked button — would
otherwise start the same work twice, and the duplicate would be
indistinguishable from a deliberate re-run. That is how a queue acquires
duplicate jobs overnight.

`services/runs.create` checks for an identical active run before writing. This
index is what makes the guarantee structural rather than a matter of timing: two
concurrent requests that both pass the check cannot both insert.

Partial, on the statuses that mean the work is happening or has happened. A
failed or cancelled run leaves the index, so retrying after a genuine failure
starts fresh rather than being deduplicated against a corpse. Postgres enum
labels are the uppercase member names, matching `0001_initial`.

Revision ID: 0003_run_idempotency
Revises: 0002_features
Create Date: 2026-08-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_run_idempotency"
down_revision: str | None = "0002_features"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVE = "status IN ('PENDING', 'RUNNING', 'SUCCEEDED')"


def upgrade() -> None:
    # Existing duplicates would block the index. There should be none — the
    # deduplication is new, so any pair here was created before it existed — but
    # failing the migration with a bare index error would be unhelpful, so the
    # older duplicates are stood down rather than deleted. Nothing is discarded:
    # a cancelled run keeps its stages, scores and provenance.
    op.execute(
        sa.text(
            f"""
            UPDATE run SET status = 'CANCELLED', error = COALESCE(error,
                'Superseded: an identical run already existed. Deduplicated by '
                'migration 0003, which made starting a run idempotent.')
            WHERE id IN (
                SELECT id FROM (
                    SELECT id, ROW_NUMBER() OVER (
                        PARTITION BY goal_id, input_hash ORDER BY created_at
                    ) AS rank
                    FROM run WHERE {ACTIVE}
                ) ranked WHERE ranked.rank > 1
            )
            """
        )
    )
    op.create_index(
        "uq_run_active_input",
        "run",
        ["goal_id", "input_hash"],
        unique=True,
        postgresql_where=sa.text(ACTIVE),
    )


def downgrade() -> None:
    op.drop_index("uq_run_active_input", table_name="run")
