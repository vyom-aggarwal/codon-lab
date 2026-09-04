"""The check that stands between a paste and an oligo order.

Everything downstream — primer position, flanking arms, melting temperature — is
computed against the sequence this module accepts. A wrong acceptance does not
produce a visibly wrong number; it produces primers that look correct, get
synthesised, and do not anneal.

So the tests below are mostly about **what must be refused**, and each refusal
names a way a real paste goes wrong: the wrong construct, the wrong frame, the
precursor instead of the mature protein, a truncation, an ambiguity code.
"""

from __future__ import annotations

import pytest

from codonlab.domain.translation import clean, validate

# A short protein and a coding sequence that genuinely encodes it. Written as
# DNA and translated by biotite in the test itself, so the fixture cannot drift
# from what the module computes.
CDS = "ATGAAATTTGGCTGGCATTTAGATTGCGAA"
PROTEIN = "MKFGWHLDCE"
WITH_STOP = CDS + "TAA"


def test_the_fixture_really_does_encode_the_protein() -> None:
    """Guards the other tests. If this drifts, every acceptance below is
    asserting something about the wrong pair of sequences."""
    assert validate(CDS, protein=PROTEIN).ok


def test_a_coding_sequence_that_encodes_the_protein_is_accepted() -> None:
    result = validate(CDS, protein=PROTEIN)
    assert result.ok
    assert result.protein == PROTEIN


def test_a_trailing_stop_codon_is_accepted() -> None:
    """A CDS normally runs through its stop; the stored protein never carries
    one. Refusing this would refuse almost every real paste."""
    result = validate(WITH_STOP, protein=PROTEIN)
    assert result.ok
    assert result.protein == PROTEIN


def test_headers_whitespace_and_numbering_are_stripped() -> None:
    """What survives a copy out of SnapGene, Benchling or a supplier's email.
    Stripping these is convenience, not interpretation."""
    pasted = f">lcl|construct pUC19-lipA\n  1 {CDS[:15].lower()}\n 16 {CDS[15:].lower()}\n"
    assert validate(pasted, protein=PROTEIN).ok


def test_clean_leaves_only_bases() -> None:
    assert clean(">header\n 1 atg aaa\n") == "ATGAAA"


def test_an_empty_paste_is_refused_with_a_remedy() -> None:
    result = validate("   \n  ", protein=PROTEIN)
    assert not result.ok
    assert result.remedy


@pytest.mark.parametrize("code", ["N", "R", "Y", "U"])
def test_an_ambiguity_code_is_refused_rather_than_guessed(code: str) -> None:
    """A primer designed over an unknown base is a primer that may not anneal.
    Resolving N to a base would be inventing the user's plasmid."""
    result = validate(CDS[:9] + code + CDS[10:], protein=PROTEIN)
    assert not result.ok
    assert code in (result.reason or "")


def test_a_sequence_that_is_not_whole_codons_is_refused() -> None:
    result = validate(CDS + "AT", protein=PROTEIN)
    assert not result.ok
    assert "codons" in (result.reason or "")


def test_an_internal_stop_codon_is_refused_and_located() -> None:
    """The commonest frame error. The sequence is still a whole number of
    codons, so length alone does not catch it."""
    broken = CDS[:9] + "TAA" + CDS[12:]
    result = validate(broken, protein=PROTEIN)
    assert not result.ok
    assert "stop codon at codon 4" in (result.reason or "")


def test_a_different_protein_is_refused_and_the_first_difference_named() -> None:
    """"It failed validation" is useless to somebody holding a tube. The residue
    number is what lets them see whether they pasted the wrong construct or the
    wrong target."""
    # Change codon 3 from TTT (F) to TGG (W).
    other = CDS[:6] + "TGG" + CDS[9:]
    result = validate(other, protein=PROTEIN)
    assert not result.ok
    assert result.first_difference == 3
    assert "residue 3" in (result.reason or "")


def test_a_precursor_containing_the_mature_protein_is_refused_with_its_offset() -> None:
    """The signal-peptide case, and the one most likely to be waved through.

    The translation *contains* the stored protein, so a check that asked
    "is the protein in there?" would accept it — and every primer position would
    then be wrong by the length of the leader. It is reported, with the offset,
    and refused.
    """
    leader_dna = "ATGAAAGCTTTAAGT"  # 5 residues of leader
    result = validate(leader_dna + CDS[3:], protein=PROTEIN[1:])

    assert not result.ok
    assert result.offset == 5
    assert "signal peptide" in (result.reason or "")
    assert "shift" in (result.remedy or "")


def test_a_truncation_is_refused_even_though_it_agrees_as_far_as_it_goes() -> None:
    """A prefix matches everywhere it exists. Accepting it would produce primers
    for positions the construct does not contain."""
    result = validate(CDS[:18], protein=PROTEIN)
    assert not result.ok
    assert "as far as the shorter one goes" in (result.reason or "")


def test_every_refusal_carries_a_remedy() -> None:
    """The house rule: an error that does not say what fixes it is useless to
    somebody who is busy. Asserted over every refusal path at once so a new one
    cannot be added without it."""
    refusals = [
        validate("", protein=PROTEIN),
        validate("ATGNNN", protein=PROTEIN),
        validate(CDS + "A", protein=PROTEIN),
        validate(CDS[:9] + "TAA" + CDS[12:], protein=PROTEIN),
        validate(CDS[:6] + "TGG" + CDS[9:], protein=PROTEIN),
        validate(CDS[:18], protein=PROTEIN),
    ]
    for result in refusals:
        assert not result.ok
        assert result.reason, "a refusal must say what is wrong"
        assert result.remedy, f"no remedy for: {result.reason}"
