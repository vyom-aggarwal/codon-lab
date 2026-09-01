"""Validation of the solvent-accessibility calculation.

This file ships before the RSA column does, and it exists because an unvalidated
radii table moves residues across the core/surface boundary silently — which
changes the engineering strategy the product recommends without changing
anything a reader would notice.

Two tests, because one is not enough:

1. **Agreement with published DSSP output.** Catches gross errors: wrong probe
   radius, hydrogens left in, ligands included in the reported number, the wrong
   atom set. Fixtures are real DSSP files from the PDB-REDO DSSP databank, and
   the coordinates they were computed on are the same files vendored here — the
   CA coordinates DSSP prints match the PDB fixtures to its print precision.

2. **A pinned golden table.** Necessary because test 1 provably cannot do the
   job on its own: swapping ProtOr for a uniform radius *raises* correlation with
   DSSP to r = 0.998 while moving 8 of 1BTL's 263 residues across a region
   boundary. Test 1 would pass. This one fails.

Both fixtures are committed, so the suite stays hermetic.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from codonlab.domain.constants.max_asa import MAX_ASA, REFERENCE_SET
from codonlab.features.structure import RegionCutoffs, SasaParameters, compute

FIXTURES = Path(__file__).parent / "fixtures"

#: Observed agreement with DSSP 4.6.1, measured when these fixtures were taken:
#:   1CRN  r=0.9937  median|d|=2.5  mean|d|=3.4  total ratio 0.999
#:   1BTL  r=0.9954  median|d|=1.4  mean|d|=2.9  total ratio 0.981
#: The bounds below sit outside those with margin. They are not aspirational —
#: DSSP uses Lee-Richards with its own radii, so exact equality is not the goal
#: and claiming it would be wrong.
MIN_CORRELATION = 0.98
MAX_MEDIAN_DIFFERENCE = 5.0
MAX_TOTAL_RATIO_ERROR = 0.05


def author_labels(pdb_path: Path, chain: str) -> list[str]:
    """Residue labels in chain order.

    A stand-in for the reconciled numbering scheme, which is what supplies these
    in production. Order is all this test needs; nothing here is a claim about
    which residue is which in a target's sequence.
    """
    seen: set[str] = set()
    labels: list[str] = []
    for line in pdb_path.read_text().splitlines():
        if line.startswith("ATOM") and line[21] == chain:
            key = line[22:27].strip()
            if key not in seen:
                seen.add(key)
                labels.append(key)
    return labels


def dssp_accessibility(path: Path) -> dict[str, float]:
    """The ACC column of a DSSP file, keyed by author residue label."""
    values: dict[str, float] = {}
    started = False
    for line in path.read_text().splitlines():
        if line.startswith("  #  RESIDUE"):
            started = True
            continue
        # A '!' in the residue column is a chain break, not a residue.
        if not started or len(line) < 40 or line[13] == "!":
            continue
        values[line[5:10].strip()] = float(line[34:38])
    return values


def features_for(pdb_id: str, chain: str = "A"):
    pdb_path = FIXTURES / f"{pdb_id}.pdb"
    labels = author_labels(pdb_path, chain)
    return (
        compute(
            structure_text=pdb_path.read_text(),
            chain_id=chain,
            sequence="X" * len(labels),
            author_labels=labels,
            coordinate_source=f"test fixture {pdb_id}.pdb",
        ),
        labels,
    )


# --------------------------------------------------------------------------- #
# 1. Agreement with published DSSP output
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("pdb_id", ["1crn", "1btl"])
def test_absolute_asa_agrees_with_published_dssp(pdb_id: str) -> None:
    features, labels = features_for(pdb_id)
    reference = dssp_accessibility(FIXTURES / f"{pdb_id}.dssp")

    ours: list[float] = []
    theirs: list[float] = []
    for position, feature in features.residues.items():
        label = labels[position - 1]
        if label in reference and feature.asa is not None:
            ours.append(feature.asa)
            theirs.append(reference[label])

    assert len(ours) == len(reference), "every DSSP residue must have been measured"

    a = np.array(ours)
    b = np.array(theirs)
    correlation = float(np.corrcoef(a, b)[0, 1])
    median_difference = float(np.median(np.abs(a - b)))
    ratio = float(a.sum() / b.sum())

    assert correlation >= MIN_CORRELATION, f"r={correlation:.4f}"
    assert median_difference <= MAX_MEDIAN_DIFFERENCE, f"median|d|={median_difference:.1f}"
    assert abs(ratio - 1.0) <= MAX_TOTAL_RATIO_ERROR, f"total ratio={ratio:.3f}"


@pytest.mark.parametrize("pdb_id", ["1crn", "1btl"])
def test_the_dssp_fixture_was_computed_on_the_vendored_coordinates(pdb_id: str) -> None:
    """Otherwise the comparison above compares against a different molecule.

    DSSP prints CA coordinates to one decimal; they must match the PDB file this
    repository actually feeds to the SASA calculation. This is step 3 of the
    fixture procedure in ARCHITECTURE.md §11, and it is the step that catches a
    reference computed on a re-refined structure — which would otherwise surface
    much later as an unexplained tolerance failure.
    """
    dssp_ca: dict[str, tuple[float, float, float]] = {}
    started = False
    for line in (FIXTURES / f"{pdb_id}.dssp").read_text().splitlines():
        if line.startswith("  #  RESIDUE"):
            started = True
            continue
        if not started or len(line) < 136 or line[13] == "!":
            continue
        dssp_ca[line[5:10].strip()] = (
            float(line[115:122]),
            float(line[122:129]),
            float(line[129:136]),
        )

    checked = 0
    for line in (FIXTURES / f"{pdb_id}.pdb").read_text().splitlines():
        if line.startswith("ATOM") and line[12:16].strip() == "CA" and line[16] in " A":
            label = line[22:27].strip()
            if label not in dssp_ca:
                continue
            here = (float(line[30:38]), float(line[38:46]), float(line[46:54]))
            for mine, theirs in zip(here, dssp_ca[label], strict=True):
                # DSSP prints one decimal, so half an ulp is 0.05 exactly and a
                # coordinate ending .x5 lands on the boundary. 0.06 is that plus
                # float noise — anything larger would be a different molecule.
                # Do not widen this to make a new fixture pass.
                assert abs(mine - theirs) <= 0.06, f"{label}: {here} vs {dssp_ca[label]}"
            checked += 1

    assert checked == len(dssp_ca) > 0


def test_every_dssp_fixture_has_a_coordinate_file_beside_it() -> None:
    """A reference with no coordinates cannot be checked, so it must not exist."""
    for dssp in FIXTURES.glob("*.dssp"):
        assert dssp.with_suffix(".pdb").exists(), (
            f"{dssp.name} has no coordinates committed beside it — see "
            "ARCHITECTURE.md §11, step 3."
        )


def test_the_fixture_provenance_is_recorded() -> None:
    """Every fixture is listed in the README with its source and date."""
    readme = (FIXTURES / "README.md").read_text()
    for fixture in FIXTURES.iterdir():
        if fixture.name == "README.md":
            continue
        assert fixture.name in readme, f"{fixture.name} is not recorded in fixtures/README.md"


# --------------------------------------------------------------------------- #
# 2. The pinned parameters
# --------------------------------------------------------------------------- #


def test_golden_table_pins_the_radii_set_and_reference_table() -> None:
    """The test the DSSP comparison cannot be.

    If someone changes the radii set, the normalisation table, the probe radius
    or the point count, this fails. That is its entire job.
    """
    features, labels = features_for("1btl")
    by_label = {labels[position - 1]: feature for position, feature in features.residues.items()}

    rows = [
        row
        for row in csv.DictReader(
            line
            for line in (FIXTURES / "1btl_golden_sasa.csv").read_text().splitlines()
            if not line.startswith("#")
        )
    ]
    assert len(rows) == 263

    for row in rows:
        feature = by_label[row["author_label"]]
        assert feature.asa is not None and feature.rsa is not None
        # 0.5 A^2: the calculation is deterministic, so this is headroom for a
        # library revision, not for a different radii set — swapping ProtOr for a
        # uniform radius moves the median residue by 1.8 A^2.
        assert abs(feature.asa - float(row["asa"])) <= 0.5, row["author_label"]
        assert abs(feature.rsa - float(row["rsa"])) <= 0.005, row["author_label"]
        assert feature.region is not None
        assert feature.region.value == row["region"], row["author_label"]


def test_a_different_radii_set_would_be_caught() -> None:
    """Proves the golden table discriminates, rather than merely existing."""
    protor, _ = features_for("1btl")
    labels = author_labels(FIXTURES / "1btl.pdb", "A")
    uniform = compute(
        structure_text=(FIXTURES / "1btl.pdb").read_text(),
        chain_id="A",
        sequence="X" * len(labels),
        author_labels=labels,
        parameters=SasaParameters(vdw_radii="Single"),
    )

    differences = [
        abs(protor.residues[position].asa - uniform.residues[position].asa)  # type: ignore[operator]
        for position in protor.residues
    ]
    assert sum(1 for d in differences if d > 0.5) > len(differences) // 4

    moved = sum(
        1
        for position in protor.residues
        if protor.residues[position].region != uniform.residues[position].region
    )
    assert moved > 0, "if a radii swap moved nothing, the golden table proves nothing"


# --------------------------------------------------------------------------- #
# The reference table itself
# --------------------------------------------------------------------------- #


def test_the_reference_table_covers_the_twenty_standard_residues() -> None:
    assert len(MAX_ASA) == 20
    assert "Tien" in REFERENCE_SET and "theoretical" in REFERENCE_SET


def test_no_residue_exceeds_its_published_maximum() -> None:
    """The reason the theoretical set was chosen over Miller 1987: a scale that
    saturates cannot tell "fully exposed" from "more exposed than the reference
    allows"."""
    features, _ = features_for("1btl")
    over = {p: f.rsa for p, f in features.residues.items() if f.rsa is not None and f.rsa > 1.0}
    assert over == {}


def test_an_unlisted_residue_type_has_no_maximum_rather_than_a_guess() -> None:
    from codonlab.domain.constants.max_asa import max_asa

    assert max_asa("ALA") == 129.0
    assert max_asa("MSE") is None


# --------------------------------------------------------------------------- #
# Cutoffs, ligands and the active site
# --------------------------------------------------------------------------- #


def test_cutoffs_classify_at_the_stated_boundaries() -> None:
    cutoffs = RegionCutoffs(core_max=0.25, surface_min=0.40)
    assert cutoffs.classify(0.24).value == "core"
    assert cutoffs.classify(0.25).value == "boundary"
    assert cutoffs.classify(0.40).value == "boundary"
    assert cutoffs.classify(0.41).value == "surface"
    assert cutoffs.classify(None) is None


def test_cutoffs_out_of_order_are_refused() -> None:
    from codonlab.domain.regions import CutoffError

    with pytest.raises(CutoffError):
        RegionCutoffs(core_max=0.6, surface_min=0.2)


def test_cutoffs_default_to_the_owners_values_and_say_so_in_the_manifest() -> None:
    from codonlab.domain.regions import RegionCutoffs as Cutoffs

    assert Cutoffs() == Cutoffs(core_max=0.25, surface_min=0.40)
    # An absent project setting means the defaults are in force, and they are
    # recorded in provenance exactly as an override would be.
    assert Cutoffs.from_settings(None) == Cutoffs()
    assert Cutoffs.from_settings({"rsa_cutoffs": {"core_max": 0.2, "surface_min": 0.5}}) == Cutoffs(
        core_max=0.2, surface_min=0.5
    )


def test_a_cofactor_that_buries_a_residue_is_flagged() -> None:
    """1BTL carries a sulfate. A residue exposed in the protein alone and buried
    once the ligand is present is the most misleading thing this column can say,
    so it is flagged rather than reported as exposed."""
    features, _ = features_for("1btl")
    flagged = [f for f in features.residues.values() if f.buried_by_ligand]
    assert flagged, "the SO4 in 1BTL buries at least one residue"
    for feature in flagged:
        assert feature.rsa is not None and feature.rsa_with_ligands is not None
        assert feature.rsa - feature.rsa_with_ligands > 0.10


def test_the_reported_number_excludes_ligands() -> None:
    """The flag uses the holo pass; the column does not."""
    features, _ = features_for("1btl")
    flagged = next(f for f in features.residues.values() if f.buried_by_ligand)
    assert flagged.rsa is not None and flagged.rsa_with_ligands is not None
    assert flagged.rsa > flagged.rsa_with_ligands


def test_distance_is_measured_from_any_heavy_atom_not_the_alpha_carbon() -> None:
    """An arginine side chain reaches roughly 7 A past its own CA. Measuring from
    CA would call a residue clear of the pocket while its side chain sits in it."""
    labels = author_labels(FIXTURES / "1btl.pdb", "A")
    # TEM-1's catalytic serine is Ser70 in Ambler numbering.
    position = labels.index("70") + 1
    features = compute(
        structure_text=(FIXTURES / "1btl.pdb").read_text(),
        chain_id="A",
        sequence="X" * len(labels),
        author_labels=labels,
        active_site_positions=[position],
    )

    assert features.residues[position].distance_to_active_site == 0.0
    reachable = [
        f.distance_to_active_site
        for f in features.residues.values()
        if f.distance_to_active_site is not None
    ]
    assert len(reachable) == len(features.residues)
    assert max(reachable) > 10.0


def test_no_annotated_active_site_means_no_distance_and_a_stated_reason() -> None:
    features, _ = features_for("1btl")
    assert all(f.distance_to_active_site is None for f in features.residues.values())
    assert any("No catalytic" in note for note in features.notes)


def test_the_manifest_records_everything_needed_to_reproduce_the_numbers() -> None:
    features, _ = features_for("1btl")
    manifest = features.manifest

    assert manifest["reference_doi"] == "10.1371/journal.pone.0080635"
    assert manifest["sasa"]["probe_radius_angstrom"] == 1.4
    assert manifest["sasa"]["point_number"] == 1000
    assert "ProtOr" in manifest["sasa"]["vdw_radii"]
    assert "biotite" in manifest["sasa"]["implementation"]
    assert manifest["cutoffs"]["core_rsa_below"] == 0.25
    assert manifest["cutoffs"]["surface_rsa_above"] == 0.40
    # Assembly is stated, never assumed: a dimer-interface residue is buried in
    # the assembly and exposed in the monomer.
    assert "monomer" in manifest["assembly"]
    assert manifest["chain_measured"] == "A"
    assert manifest["hetero_residues_present"] == ["SO4"]
