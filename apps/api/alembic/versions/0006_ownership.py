"""Projects belong to somebody.

Deployment. Until this revision the schema had no notion of a user at all: any
caller could read every project in the database and queue an hour of compute per
request. That was correct for a tool that only ever ran on one researcher's
machine, and is indefensible the moment it is reachable from a URL.

**`user`.** One row per identity that has presented a valid token, keyed on the
provider's `sub` claim. No credentials are stored — see `models/identity` for
why identity is delegated to an OIDC provider rather than implemented here.
`subject` is unique because two rows for one person would split their projects
in half with no way to tell from the interface.

**`project.owner_id`, nullable.** The nullability is the whole design decision
in this migration, so it is worth being explicit about.

Every existing project was created before authentication existed. Nothing in the
database records who made them — there was nobody to record. Backfilling them to
some user would be inventing a claim about authorship, which is the same class
of thing as inventing a scientific number: it would render identically to a true
one and there would be no way to tell later.

So they stay null, and null is given a meaning that is safe rather than
convenient: **an unowned project belongs to nobody, and under
`CODONLAB_AUTH=jwt` it is served to nobody.** It remains visible when the API
runs unauthenticated, which is local development, where the alternative would be
a developer's existing work vanishing on upgrade.

The consequence is deliberate and worth stating plainly: deploying this against
a database that already has projects in it will show an empty project list. That
is the correct outcome — those projects have no owner, and guessing one would be
worse than showing none. `DEPLOYMENT.md` says so where an operator will read it.

Revision ID: 0006_ownership
Revises: 0005_measurement_intake
Create Date: 2026-09-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_ownership"
down_revision: str | None = "0005_measurement_intake"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_created_at", "user", ["created_at"])
    op.create_index("ix_user_email", "user", ["email"])
    # Unique, not merely indexed. This is the constraint that makes "one person,
    # one account" true under concurrency — two simultaneous first requests from
    # the same new subject would otherwise both find nothing and both insert.
    op.create_index("ix_user_subject", "user", ["subject"], unique=True)

    op.add_column(
        "project",
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_project_owner_id", "project", ["owner_id"])
    op.create_foreign_key(
        "fk_project_owner_id_user",
        "project",
        "user",
        ["owner_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_project_owner_id_user", "project", type_="foreignkey")
    op.drop_index("ix_project_owner_id", table_name="project")
    op.drop_column("project", "owner_id")
    op.drop_index("ix_user_subject", table_name="user")
    op.drop_index("ix_user_email", table_name="user")
    op.drop_index("ix_user_created_at", table_name="user")
    op.drop_table("user")
