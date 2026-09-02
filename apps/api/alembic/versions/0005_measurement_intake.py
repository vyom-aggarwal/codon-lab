"""An import states which way its numbers point, and where they came from.

Phase 8. Two columns on `experiment`, both carrying facts that cannot be
recovered from the measurements themselves.

**`higher_is_better`, nullable, no default.** Whether a larger value is a better
result is a property of the assay that only the person who ran it knows. A T50 in
degrees Celsius is higher-is-better; a ddG reported destabilizing-positive is
not; an IC50 is not. Every rank statistic on the scorecard needs it to orient
itself, and the absolute-error terms need it to refuse a comparison across
opposed sign conventions (`domain/scorecard.commensurable`).

It is nullable rather than defaulted **because a default would be an invented
sign convention**, which HANDOFF.md §7 records the owner forbidding by name. Null
means the direction was never stated, and the scorecard reports that it cannot
rank rather than guessing. The import route requires the field, so nothing
written from here on can be null; existing rows (there are none — nothing has
imported measurements before this revision) would be.

**`source_note`, nullable.** Where the values came from, in the user's words or
as a citation: an uploaded file name, or the DOI of a published deep mutational
scan. `Measurement.raw_label` records what each row said; this records what the
file was. Null means an import that predates the column.

`Measurement.metric` and `Measurement.unit` are deliberately **not** duplicated
onto `experiment`. They are already per-row, and a second copy could only ever
be an answer capable of disagreeing with the first — the rule the design set's
additive totals and the ranking consensus both follow. One import writes one
metric today, which is what makes an experiment-level direction unambiguous; if
an import is ever allowed to write several metrics at once, the direction has to
move down to the row with them.

Revision ID: 0005_measurement_intake
Revises: 0004_design_sets
Create Date: 2026-09-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_measurement_intake"
down_revision: str | None = "0004_design_sets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("experiment", sa.Column("higher_is_better", sa.Boolean(), nullable=True))
    op.add_column("experiment", sa.Column("source_note", sa.String(), nullable=True))

    # Measurements are read back by (variant, metric) on every scorecard, and by
    # experiment when one import is being reviewed. The experiment index already
    # exists from 0001; this is the join the scorecard actually makes.
    op.create_index(
        "ix_measurement_variant_metric",
        "measurement",
        ["variant_id", "metric"],
    )


def downgrade() -> None:
    op.drop_index("ix_measurement_variant_metric", table_name="measurement")
    op.drop_column("experiment", "source_note")
    op.drop_column("experiment", "higher_is_better")
