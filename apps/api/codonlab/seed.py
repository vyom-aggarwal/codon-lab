"""Idempotent development seed.

Scope note — this seeds *projects only*, deliberately.

A Target requires an amino acid sequence, and writing a real protein sequence from
memory is exactly the kind of fabricated scientific content this product exists to
refuse. Real targets arrive in Phase 2, whose exit gate is fetching a UniProt
accession and a PDB for real and reconciling their numbering. Until then the
projects table honestly shows no target rather than an invented one.

The two projects below are real, standard protein-engineering subjects, recorded as
metadata only. The accessions in each objective are for the Phase 2 fetch to
resolve and verify against live UniProt.
"""

from __future__ import annotations

import sys

from sqlmodel import Session, select

from codonlab.db import get_engine
from codonlab.models import Project

SEED_PROJECTS: tuple[dict[str, str], ...] = (
    {
        "name": "TEM-1 thermostability",
        "organism": "Escherichia coli",
        "objective": "Raise the melting temperature of TEM-1 beta-lactamase "
        "(UniProt P62593) without losing hydrolytic activity.",
    },
    {
        "name": "Lipase A solvent tolerance",
        "organism": "Bacillus subtilis",
        "objective": "Improve tolerance of lipase A (UniProt P37957) to organic "
        "cosolvent while preserving expression yield.",
    },
)


def seed() -> int:
    """Insert any missing seed projects. Safe to run on every container start."""
    inserted = 0
    with Session(get_engine()) as session:
        for row in SEED_PROJECTS:
            existing = session.exec(select(Project).where(Project.name == row["name"])).first()
            if existing is not None:
                continue
            session.add(Project(**row))
            inserted += 1
        session.commit()
    return inserted


def main() -> None:
    inserted = seed()
    if inserted:
        print(f"seed: inserted {inserted} project(s)", file=sys.stderr)
    else:
        print("seed: already present, nothing to do", file=sys.stderr)


if __name__ == "__main__":
    main()
