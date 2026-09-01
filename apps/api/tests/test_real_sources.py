"""Integration tests against the live UniProt, RCSB and AlphaFold services.

Skipped automatically when the network is unavailable, so the default suite
stays hermetic. They are worth keeping because every interesting numbering case
in this domain came from real records rather than from imagination — the Ambler
convention below is not something a synthetic fixture would have suggested.
"""

from __future__ import annotations

import httpx
import pytest

from codonlab.domain.numbering import ReconcileOutcome, align, contiguous_runs, reconcile
from codonlab.sources import structures, uniprot
from codonlab.sources.pdb import parse_pdb


def _online() -> bool:
    try:
        httpx.get("https://rest.uniprot.org/uniprotkb/P62593.fasta", timeout=10.0)
    except httpx.HTTPError:
        return False
    return True


pytestmark = pytest.mark.skipif(not _online(), reason="needs network access")


@pytest.fixture(scope="module")
def tem1() -> uniprot.UniProtRecord:
    return uniprot.fetch("P62593")


@pytest.fixture(scope="module")
def lipase() -> uniprot.UniProtRecord:
    return uniprot.fetch("P37957")


@pytest.fixture(scope="module")
def btl_chain():
    structure = parse_pdb(structures.fetch_rcsb("1BTL").text)
    return structure.protein_chains[0]


class TestUniProt:
    def test_fetches_tem1(self, tem1: uniprot.UniProtRecord) -> None:
        assert tem1.accession == "P62593"
        assert tem1.organism == "Escherichia coli"
        assert tem1.length == 286

    def test_reports_the_signal_peptide_that_drives_mature_numbering(
        self, lipase: uniprot.UniProtRecord
    ) -> None:
        """P37957 is 212 aa full length; the literature numbers the 181 aa
        mature lipase. Missing this is a 31-residue error on every code."""
        assert lipase.signal_peptide is not None
        assert lipase.signal_peptide.end == 31
        assert lipase.mature_offset == -31
        assert lipase.length - lipase.signal_peptide.length == 181

    def test_rejects_a_malformed_accession(self) -> None:
        with pytest.raises(uniprot.SourceError, match="not a UniProt accession"):
            uniprot.fetch("not-an-accession")

    # The missing-entry path is covered hermetically in test_source_errors.py.
    # Asserting that some accession is absent would be a test of UniProt's
    # database contents rather than of this code.


class TestAlphaFold:
    def test_predicted_structure_reconciles_exactly(self, lipase: uniprot.UniProtRecord) -> None:
        """A prediction is built from the sequence, so it should correspond to
        it exactly. If this ever needs alignment, something is wrong upstream."""
        fetched = structures.fetch_alphafold("P37957")
        assert fetched.is_predicted
        assert "Predicted, not experimental" in fetched.note

        chain = parse_pdb(fetched.text).protein_chains[0]
        result = reconcile(lipase.sequence, chain.residues)
        assert result.outcome is ReconcileOutcome.RECONCILED
        assert result.coverage == 1.0
        assert result.identity == 1.0


class TestAmblerNumbering:
    """1BTL uses Ambler numbering, which deliberately skips residues so that
    class A beta-lactamases stay comparable across the family."""

    def test_the_chain_is_discontinuous_by_convention(self, btl_chain) -> None:
        runs = contiguous_runs(btl_chain.residues)
        assert len(runs) == 3
        assert btl_chain.first is not None and btl_chain.first.number == 26
        assert btl_chain.last is not None and btl_chain.last.number == 290

    def test_exact_matching_refuses_rather_than_forcing_an_offset(
        self, tem1: uniprot.UniProtRecord, btl_chain
    ) -> None:
        """The conventional gaps break the constant-offset assumption. Forcing
        one would misnumber every residue past 238."""
        result = reconcile(tem1.sequence, btl_chain.residues)
        assert result.outcome is ReconcileOutcome.NEEDS_ALIGNMENT
        assert result.mapping == ()

    def test_explicit_alignment_resolves_it_and_reports_every_difference(
        self, tem1: uniprot.UniProtRecord, btl_chain
    ) -> None:
        result = align(tem1.sequence, btl_chain.residues)
        assert result.outcome is ReconcileOutcome.RECONCILED
        assert result.identity > 0.98
        assert result.parameters is not None

        # Real differences between the reference and this crystal form. They are
        # reported, never quietly absorbed into a match.
        assert len(result.mismatches) == 2
        observed = {
            (m.canonical_residue, m.observed_slot.label, m.observed_residue)
            for m in result.mismatches
        }
        assert ("V", "84", "I") in observed
        assert ("A", "184", "V") in observed

    def test_mature_numbering_covers_the_whole_structure(
        self, tem1: uniprot.UniProtRecord, btl_chain
    ) -> None:
        """The crystal has no signal peptide, so full-length numbering leaves
        23 residues unresolved while mature numbering covers everything. This is
        the evidence a user needs to choose a canonical scheme."""
        assert tem1.signal_peptide is not None
        mature = tem1.sequence[tem1.signal_peptide.end :]

        full_coverage = align(tem1.sequence, btl_chain.residues).coverage
        mature_coverage = align(mature, btl_chain.residues).coverage
        assert mature_coverage == 1.0
        assert full_coverage < mature_coverage
