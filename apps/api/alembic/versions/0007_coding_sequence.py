"""A target can carry the DNA of the construct on the bench.

This is the column `BRIEF.md` §5.8 has been blocked on since Phase 7. A
site-directed mutagenesis primer anneals to a real template, and until now the
data model held a one-letter amino acid sequence and nothing else — so there was
nothing to design against, and `services/exports` refused primers with that
reason rather than inventing one.

**Nullable, and it stays nullable.** A target without a coding sequence is not
broken; it is a target nobody has attached a construct to yet, which is the
normal state right after import. Every existing row is in exactly that state,
and there is nothing to backfill from: the sequence has to come from the user's
plasmid, and no column here knows what that is. `ARCHITECTURE.md` §16 records why
ENA cross-reference and codon back-translation were both rejected — each
produces a sequence that is plausible, is not theirs, and yields primers that do
not anneal.

**No index.** It is read only when a target is opened or a primer is designed,
always by target id, and it is a kilobase of text. An index would be a cost with
no reader.

Revision ID: 0007_coding_sequence
Revises: 0006_ownership
Create Date: 2026-09-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_coding_sequence"
down_revision: str | None = "0006_ownership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("target", sa.Column("coding_sequence", sa.String(), nullable=True))

    # `provenanceeventkind` is a real Postgres enum, so a new audit kind is a
    # schema change rather than a Python-side constant. Labels are stored as the
    # member *name*, which is what the existing rows carry.
    #
    # `IF NOT EXISTS` because this migration may be re-applied against a
    # database that already has it, and a failed ALTER TYPE would abort the
    # whole upgrade for something already true.
    op.execute(
        "ALTER TYPE provenanceeventkind ADD VALUE IF NOT EXISTS 'CODING_SEQUENCE_ATTACHED'"
    )


def downgrade() -> None:
    op.drop_column("target", "coding_sequence")
    # The enum label is deliberately not removed. Postgres cannot drop a value
    # from an enum type, and rebuilding the type would rewrite every row of an
    # append-only audit table to undo one addition nothing reads.
