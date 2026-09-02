"""The vendored deep mutational scan, and the checks that keep it honest.

`BRIEF.md` §7 asks for a DMS dataset with real measured values so the scorecard
is demoable with true numbers. These tests guard the data file itself rather
than the database write: the expensive failure is not "the seed crashed", it is
"the seed attached 2,172 real measurements to the wrong residues", which no
amount of exercising the write path would catch.

Hermetic — the files are vendored, so nothing here touches the network or a
database.
"""

from __future__ import annotations

import pytest

from codonlab.domain.mutation import parse_mutation
from codonlab.seed import (
    ASSAY,
    EXPECTED_LENGTH,
    _read_measurements,
    _read_sequence,
    _verify_against_sequence,
)


def test_the_vendored_sequence_is_the_length_it_claims() -> None:
    assert len(_read_sequence()) == EXPECTED_LENGTH


def test_the_vendored_sequence_is_lipase_a() -> None:
    """Two anchors from UniProt P37957, checked on 2026-09-01.

    Position 32 is the first residue of the mature protein — the fact the whole
    numbering story on this target rests on.
    """
    sequence = _read_sequence()
    assert sequence.startswith("MKFVKRRIIALVTILMLSVTSLFALQPSAKA")
    assert sequence[31] == "A", "residue 32 begins the mature protein"
    assert sequence.endswith("GLNGGGQNTN")


def test_every_measured_row_reads_as_a_mutation_code() -> None:
    rows = _read_measurements()
    assert len(rows) == 2172
    for code, _ in rows:
        parse_mutation(code)


def test_every_measured_row_names_the_residue_the_sequence_has() -> None:
    """The check that makes the seed safe, run against the real files.

    A code naming a residue the sequence does not carry means the measurements
    and the sequence have drifted apart, and seeding either would misattribute
    real bench values.
    """
    _verify_against_sequence(_read_sequence(), _read_measurements())


def test_the_verification_rejects_a_sequence_that_does_not_match() -> None:
    """Mutation-checks the check itself.

    Shifting the sequence by one residue is exactly the failure this guards
    against, and it must not pass.
    """
    sequence = _read_sequence()
    shifted = sequence[1:] + "A"
    with pytest.raises(RuntimeError, match="disagree"):
        _verify_against_sequence(shifted, _read_measurements())


def test_the_verification_rejects_a_position_off_the_end() -> None:
    with pytest.raises(RuntimeError, match="outside"):
        _verify_against_sequence(_read_sequence(), [("M999A", 1.0)])


def test_the_measured_values_are_temperatures_not_normalised_scores() -> None:
    """T50 in °C for this enzyme sits around 48 °C.

    A ProteinGym file whose scores had been z-scored or min-max normalised would
    still parse and still join; it would just silently stop being a temperature,
    and the unit the scorecard reports would become a lie.
    """
    values = [value for _, value in _read_measurements()]
    assert min(values) > 20.0
    assert max(values) < 80.0
    assert 40.0 < sum(values) / len(values) < 55.0


def test_the_assay_states_its_direction_and_unit() -> None:
    """Neither is defaulted anywhere. §7 forbids reading a °C figure as a ΔΔG,
    so the unit has to travel with the numbers from the seed onwards."""
    assert ASSAY.unit == "°C"
    assert ASSAY.metric == "t50_celsius"
    assert ASSAY.higher_is_better is True
    assert "doi:10.1021/acs.jcim.9b00954" in ASSAY.citation


def test_the_binarised_column_is_not_imported() -> None:
    """`DMS_score_bin` is a median split of a number already present. Importing
    it would create a second answer capable of disagreeing with the first."""
    rows = _read_measurements()
    # Every value is a temperature, not a 0/1 flag.
    assert not all(value in (0.0, 1.0) for value in [v for _, v in rows])
