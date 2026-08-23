"""ThermoMPNN: the sign convention, the pin, and what it refuses to answer.

Hermetic by default; the tests that load the model are opt-in:

    CATALYST_TEST_REAL_MODELS=1 pytest tests/test_thermompnn.py

The sign convention is the one that matters most here. Getting it backwards would
invert every stability recommendation the product makes, silently, and the output
would look entirely reasonable either way. It was established two ways, and both
are recorded below rather than in a commit message someone has to go digging for.
"""

from __future__ import annotations

import os
import uuid

import pytest

from catalyst.domain.goal import Objective
from catalyst.providers.base import StructureRef, TargetContext
from catalyst.providers.thermompnn import COMMIT, THERMOMPNN

REAL = os.environ.get("CATALYST_TEST_REAL_MODELS") == "1"
requires_model = pytest.mark.skipif(
    not REAL, reason="needs the ThermoMPNN weights; set CATALYST_TEST_REAL_MODELS=1"
)


def test_it_does_not_claim_to_be_a_mock() -> None:
    assert THERMOMPNN.is_mock is False


def test_the_sign_convention_is_the_one_the_brief_fixes() -> None:
    """Destabilizing positive, per specification §7, and it never changes.

    Established from upstream's own `retrieve_best_mutants`, which selects the
    *minimum* predicted ddG as the best substitution at a position — so more
    negative is more stabilizing — and corroborated by running the model: on
    crambin, hydrophobic-to-charged substitutions average +0.83 against +0.42 for
    hydrophobic-to-hydrophobic.
    """
    assert THERMOMPNN.metrics[0].sign_convention == "destabilizing positive"
    assert THERMOMPNN.metrics[0].higher_is_better is False
    assert THERMOMPNN.metrics[0].unit == "kcal/mol"


def test_it_reports_no_interval_rather_than_inventing_one() -> None:
    """`BRIEF.md` §7 wants an interval on a ΔΔG and ThermoMPNN has none to give.

    Flagged for the owner rather than papered over. A benchmark RMSE presented as
    a per-variant interval would be a fabrication with a citation attached, which
    is worse than an absent one.
    """
    assert THERMOMPNN.metrics[0].reports_interval is False


def test_it_is_offered_for_thermostability_only() -> None:
    """ARCHITECTURE.md §14.4. It predicts the free energy change of folding;
    offering it for solvent tolerance would invite the reading that a stable
    protein is a solvent-tolerant one."""
    assert THERMOMPNN.objectives == frozenset({Objective.THERMOSTABILITY})
    assert Objective.SOLVENT_TOLERANCE not in THERMOMPNN.objectives


def test_it_requires_a_structure() -> None:
    context = TargetContext(target_id=uuid.uuid4(), sequence="ACDE", scheme_label="t")
    reason = THERMOMPNN.requires.unmet(context)
    assert reason is not None
    assert "structure" in reason.lower()


def test_the_pin_is_an_exact_commit_and_appears_in_the_version() -> None:
    """A moving `main` would silently change what a stored weights_hash refers
    to, which is the one thing that field must never do."""
    assert len(COMMIT) == 40
    assert COMMIT[:12] in THERMOMPNN.version
    assert COMMIT[:12] in THERMOMPNN.citation


def test_the_citation_names_the_paper_and_the_licence() -> None:
    assert "Dieckhaus" in THERMOMPNN.citation
    assert "MIT" in THERMOMPNN.citation


def test_the_vendored_source_records_its_provenance() -> None:
    """Anyone reading the vendored files must be able to find what they came
    from without going through git history."""
    from pathlib import Path

    vendor = Path(__file__).parent.parent / "catalyst" / "providers" / "_vendor" / "thermompnn"
    assert (vendor / "LICENSE").exists()
    for name in ("transfer_model.py", "protein_mpnn_utils.py"):
        header = (vendor / name).read_text(encoding="utf-8")[:800]
        assert COMMIT in header
        assert "Kuhlman-Lab/ThermoMPNN" in header
        assert "MIT" in header


# --------------------------------------------------------------------------- #
# With the real weights
# --------------------------------------------------------------------------- #


def crambin() -> tuple[str, str]:
    from pathlib import Path

    from catalyst.domain.aminoacid import three_to_one

    pdb = (Path(__file__).parent / "fixtures" / "1crn.pdb").read_text()
    seen: set[str] = set()
    residues: list[str] = []
    for line in pdb.splitlines():
        if line.startswith("ATOM") and line[21] == "A":
            key = line[22:27].strip()
            if key not in seen:
                seen.add(key)
                residues.append(line[17:20].strip())
    return pdb, "".join(three_to_one(name) for name in residues)


@requires_model
def test_the_weights_hash_covers_both_checkpoints() -> None:
    """ThermoMPNN is a head on frozen ProteinMPNN embeddings, so the ProteinMPNN
    weights are part of what produces the number."""
    import hashlib

    assert THERMOMPNN.available() is None
    paths = THERMOMPNN._weight_paths()
    assert set(paths) == {"thermompnn", "proteinmpnn"}

    digest = hashlib.sha256()
    for name in sorted(paths):
        digest.update(name.encode())
        digest.update(paths[name].read_bytes())
    assert THERMOMPNN.weights_hash == f"sha256:{digest.hexdigest()}"


@requires_model
def test_it_scores_a_real_structure_in_a_plausible_range() -> None:
    from catalyst.domain.variants import enumerate_single_substitutions

    pdb, sequence = crambin()
    labels: list[str | None] = [str(index + 1) for index in range(len(sequence))]
    candidates = list(enumerate_single_substitutions(sequence, labels).candidates)
    context = TargetContext(
        target_id=uuid.uuid4(),
        sequence=sequence,
        scheme_label="test",
        structure=StructureRef(
            identifier="1CRN", source="pdb", content_hash="sha256:x", chain="A"
        ),
        structure_text=pdb,
    )

    scored = THERMOMPNN.score(candidates, context)
    assert len(scored) == len(candidates)

    values = [value.value for value in scored]
    # Folding free-energy changes for point mutations sit within a few kcal/mol.
    # A model returning logits or normalised units would fail here.
    assert -10.0 < min(values) < 10.0
    assert -10.0 < max(values) < 10.0
    assert all(value.uncertainty is None for value in scored)


@requires_model
def test_the_sign_convention_holds_against_physics() -> None:
    """Corroborates the reading of upstream's code with the model's behaviour.

    Burying a charge in a hydrophobic core is destabilizing. Under
    destabilizing-positive that must come out higher than a conservative
    hydrophobic swap at the same positions.
    """
    import statistics

    from catalyst.domain.variants import enumerate_single_substitutions

    pdb, sequence = crambin()
    labels: list[str | None] = [str(index + 1) for index in range(len(sequence))]
    candidates = list(enumerate_single_substitutions(sequence, labels).candidates)
    context = TargetContext(
        target_id=uuid.uuid4(),
        sequence=sequence,
        scheme_label="test",
        structure=StructureRef(
            identifier="1CRN", source="pdb", content_hash="sha256:x", chain="A"
        ),
        structure_text=pdb,
    )
    by_code = {value.variant_code: value.value for value in THERMOMPNN.score(candidates, context)}

    hydrophobic = [index + 1 for index, residue in enumerate(sequence) if residue in "IVLF"]
    to_charged = [
        by_code[f"{sequence[position - 1]}{position}{mutant}"]
        for position in hydrophobic
        for mutant in "DEKR"
        if f"{sequence[position - 1]}{position}{mutant}" in by_code
    ]
    to_hydrophobic = [
        by_code[f"{sequence[position - 1]}{position}{mutant}"]
        for position in hydrophobic
        for mutant in "IVLA"
        if f"{sequence[position - 1]}{position}{mutant}" in by_code
        and sequence[position - 1] != mutant
    ]

    assert statistics.mean(to_charged) > statistics.mean(to_hydrophobic), (
        "burying a charge came out more stabilizing than a conservative swap — "
        "the sign convention is inverted"
    )


@requires_model
def test_a_residue_mismatch_refuses_rather_than_scoring_the_wrong_one() -> None:
    """The same class of check as the ESM tokenizer alignment."""
    from dataclasses import replace

    from catalyst.domain.variants import enumerate_single_substitutions
    from catalyst.providers.base import PredictorUnavailableError

    pdb, sequence = crambin()
    labels: list[str | None] = [str(index + 1) for index in range(len(sequence))]
    candidates = list(enumerate_single_substitutions(sequence, labels).candidates)[:5]
    # Claim a residue the structure does not have at that position.
    lying = [replace(candidate, wild="W") for candidate in candidates]
    context = TargetContext(
        target_id=uuid.uuid4(),
        sequence=sequence,
        scheme_label="test",
        structure=StructureRef(
            identifier="1CRN", source="pdb", content_hash="sha256:x", chain="A"
        ),
        structure_text=pdb,
    )

    with pytest.raises(PredictorUnavailableError) as error:
        THERMOMPNN.score(lying, context)
    assert "mismatch" in str(error.value).lower()
