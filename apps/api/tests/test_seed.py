"""The seed must stay free of invented science."""

from __future__ import annotations

import re

from codonlab.seed import SEED_PROJECTS

# Any residue-level claim or measured quantity in seed metadata would be fabricated,
# since Phase 1 has no provider and no bench data.
MUTATION_CODE = re.compile(r"\b[ACDEFGHIKLMNPQRSTVWY]\d{1,4}[ACDEFGHIKLMNPQRSTVWY]\b")
MEASURED_QUANTITY = re.compile(
    r"\d+(\.\d+)?\s*(°C|kcal/mol|kJ/mol|mg/L|mg/ml|s-1|M-1)", re.IGNORECASE
)


def test_seed_projects_are_metadata_only() -> None:
    for project in SEED_PROJECTS:
        assert set(project) == {"name", "organism", "objective"}


def test_seed_states_no_mutation_codes() -> None:
    for project in SEED_PROJECTS:
        assert not MUTATION_CODE.search(project["objective"])


def test_seed_states_no_measured_values() -> None:
    for project in SEED_PROJECTS:
        assert not MEASURED_QUANTITY.search(project["objective"])


def test_seed_objectives_are_sentence_case_without_banned_copy() -> None:
    for project in SEED_PROJECTS:
        objective = project["objective"]
        assert "!" not in objective
        assert objective[0].isupper()
        assert objective.rstrip().endswith(".")
