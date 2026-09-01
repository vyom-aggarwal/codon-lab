"""The separation the 8A epistasis pair flag is measured with.

Specification §5.7 fixes the cutoff at 8A but does not say how the distance is
taken. This build uses the convention `ARCHITECTURE.md` §11 already settled for
distance to the active site: **minimum non-hydrogen atom separation, not CA-CA**.

That is not a stylistic choice, and the first test below is why. On crambin,
residues 1 and 46 sit 7.9A apart by their closest heavy atoms and 11.8A apart by
their alpha carbons. Under the brief's 8A rule the two conventions disagree about
whether that pair is flagged at all — one tells a bench scientist the mutations
may interact and the other tells them the mutations are independent.

Fixture is the committed `1crn.pdb`, whose provenance is recorded in
`tests/fixtures/README.md`. The expected values were produced by an independent
recomputation straight from the PDB text, without biotite, so the golden numbers
are not this implementation grading its own homework.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from codonlab.domain.epistasis import PAIR_PROXIMITY_ANGSTROM
from codonlab.features.structure import StructureFeatureError, pairwise_min_distances

FIXTURES = Path(__file__).parent / "fixtures"
CRAMBIN = (FIXTURES / "1crn.pdb").read_text()

#: Crambin is 46 residues and its author numbering runs 1..46 with no gaps and
#: no insertion codes, so sequence index and author label coincide here. That is
#: a property of this entry, not an assumption the code makes.
LABELS: list[str | None] = [str(index) for index in range(1, 47)]

#: Independently recomputed from the raw ATOM records. See the module docstring.
GOLDEN = {
    (1, 3): 4.2,
    (1, 20): 15.0,
    (1, 46): 7.9,
    (3, 46): 3.9,
    (20, 46): 18.3,
    (7, 32): 7.4,
}


def _measure(positions: list[int]):
    return pairwise_min_distances(
        structure_text=CRAMBIN,
        chain_id="A",
        author_labels=LABELS,
        positions=positions,
    )


def test_the_convention_decides_whether_a_pair_is_flagged_at_all() -> None:
    """The discriminating test for this whole feature.

    Residues 1 and 46 of crambin are 7.9A apart at their closest heavy atoms and
    11.8A apart at their alpha carbons. A regression to a CA-CA measurement would
    silently unflag this pair — and the same swap would unflag 7/32 as well.
    Both are asserted, because one example could be a coincidence.
    """
    result = _measure([1, 46, 7, 32])

    close_pairs = {
        pair
        for pair, separation in result.separations.items()
        if separation <= PAIR_PROXIMITY_ANGSTROM
    }
    assert (1, 46) in close_pairs
    assert (7, 32) in close_pairs

    # And the CA-CA figures these pairs would have reported instead.
    assert _ca_distance(1, 46) > PAIR_PROXIMITY_ANGSTROM
    assert _ca_distance(7, 32) > PAIR_PROXIMITY_ANGSTROM


def _ca_distance(first: int, second: int) -> float:
    """Alpha-carbon separation, read straight out of the fixture.

    Present only so the test above can state what the rejected convention would
    have answered. Nothing in the product measures distance this way.
    """
    coordinates: dict[int, tuple[float, float, float]] = {}
    for line in CRAMBIN.splitlines():
        if line.startswith("ATOM") and line[12:16].strip() == "CA":
            coordinates[int(line[22:26])] = (
                float(line[30:38]),
                float(line[38:46]),
                float(line[46:54]),
            )
    return math.dist(coordinates[first], coordinates[second])


def test_measured_separations_match_the_golden_table() -> None:
    result = _measure([1, 3, 7, 20, 32, 46])
    for pair, expected in GOLDEN.items():
        assert result.separations[pair] == pytest.approx(expected, abs=0.05), pair


def test_consecutive_residues_are_a_bond_length_apart() -> None:
    """A sanity check on the units and on which atoms are being compared: the
    closest heavy atoms of neighbouring residues are the peptide bond itself,
    about 1.33A. A value near 3.8A would mean alpha carbons."""
    result = _measure([10, 11])
    assert result.separations[(10, 11)] == pytest.approx(1.3, abs=0.15)


def test_pairs_are_keyed_low_position_first() -> None:
    result = _measure([46, 1])
    assert (1, 46) in result.separations
    assert (46, 1) not in result.separations


def test_a_position_the_structure_does_not_resolve_is_reported_not_dropped() -> None:
    """It must be possible to tell "not measured" from "not close". A silently
    missing pair would read as the latter."""
    result = pairwise_min_distances(
        structure_text=CRAMBIN,
        chain_id="A",
        # 47 is past the end of crambin, so the scheme labels it and the
        # coordinates do not contain it.
        author_labels=[*LABELS, "47"],
        positions=[1, 47],
    )
    assert result.unresolved == (47,)
    assert result.separations == {}


def test_a_position_the_scheme_cannot_name_is_unresolved() -> None:
    labels: list[str | None] = list(LABELS)
    labels[19] = None  # sequence position 20 has no label
    result = pairwise_min_distances(
        structure_text=CRAMBIN, chain_id="A", author_labels=labels, positions=[1, 20]
    )
    assert result.unresolved == (20,)
    assert result.separations == {}


def test_fewer_than_two_positions_produce_no_pairs() -> None:
    assert _measure([5]).separations == {}
    assert _measure([]).separations == {}


def test_the_same_position_twice_is_not_a_pair() -> None:
    assert _measure([5, 5]).separations == {}


def test_the_manifest_states_what_was_measured() -> None:
    result = _measure([1, 46])
    assert result.manifest["measure"] == "minimum non-hydrogen atom separation"
    assert result.manifest["positions_requested"] == 2
    assert result.manifest["positions_resolved"] == 2


def test_a_structure_with_no_amino_acids_is_refused_rather_than_returning_nothing() -> None:
    with pytest.raises(StructureFeatureError):
        pairwise_min_distances(
            structure_text="HETATM    1  O   HOH A   1       0.000   0.000   0.000\nEND\n",
            chain_id="A",
            author_labels=["1", "2"],
            positions=[1, 2],
        )
