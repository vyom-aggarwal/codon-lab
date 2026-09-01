"""Retrieval failure paths, driven by a mock transport.

Hermetic on purpose. These assert what the interface will show a user when a
fetch goes wrong, and that must not depend on the current contents or mood of
an external service.
"""

from __future__ import annotations

import httpx
import pytest

from codonlab.sources import structures, uniprot


def client_returning(*responses: httpx.Response) -> httpx.Client:
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        return queue.pop(0) if queue else httpx.Response(500)

    return httpx.Client(transport=httpx.MockTransport(handler))


class TestUniProtErrors:
    def test_missing_entry_says_so_and_offers_the_way_round_it(self) -> None:
        with (
            client_returning(httpx.Response(404)) as client,
            pytest.raises(uniprot.SourceError) as caught,
        ):
            uniprot.fetch("P62593", client=client)
        assert "no entry" in str(caught.value)
        assert "paste the sequence" in caught.value.remedy.lower()

    def test_server_error_is_reported_as_transient(self) -> None:
        with (
            client_returning(httpx.Response(503)) as client,
            pytest.raises(uniprot.SourceError) as caught,
        ):
            uniprot.fetch("P62593", client=client)
        assert "503" in str(caught.value)
        assert "retry" in caught.value.remedy.lower()

    def test_an_entry_without_a_sequence_is_refused_not_defaulted(self) -> None:
        """An empty sequence must never become an empty target."""
        with (
            client_returning(httpx.Response(200, json={"sequence": {"value": ""}})) as client,
            pytest.raises(uniprot.SourceError, match="no usable protein sequence"),
        ):
            uniprot.fetch("P62593", client=client)

    def test_a_record_with_no_signal_peptide_offers_no_mature_scheme(self) -> None:
        payload = {
            "primaryAccession": "P62593",
            "sequence": {"value": "MKAILVVLLY"},
            "features": [],
        }
        with client_returning(httpx.Response(200, json=payload)) as client:
            record = uniprot.fetch("P62593", client=client)
        assert record.signal_peptide is None
        assert record.mature_offset is None

    def test_signal_peptide_is_read_from_the_features(self) -> None:
        payload = {
            "primaryAccession": "P37957",
            "sequence": {"value": "MKAILVVLLY"},
            "features": [
                {
                    "type": "Signal",
                    "location": {"start": {"value": 1}, "end": {"value": 4}},
                }
            ],
        }
        with client_returning(httpx.Response(200, json=payload)) as client:
            record = uniprot.fetch("P37957", client=client)
        assert record.signal_peptide is not None
        assert record.signal_peptide.length == 4
        assert record.mature_offset == -4


class TestStructureErrors:
    def test_rejects_a_malformed_pdb_id(self) -> None:
        with pytest.raises(structures.SourceError, match="not a PDB id"):
            structures.fetch_rcsb("nope")

    def test_a_cif_only_entry_explains_the_limitation(self) -> None:
        with (
            client_returning(httpx.Response(404)) as client,
            pytest.raises(structures.SourceError) as caught,
        ):
            structures.fetch_rcsb("1BTL", client=client)
        assert "mmCIF" in caught.value.remedy

    def test_alphafold_with_no_prediction_says_so(self) -> None:
        with (
            client_returning(httpx.Response(200, json=[])) as client,
            pytest.raises(structures.SourceError, match="no prediction"),
        ):
            structures.fetch_alphafold("P62593", client=client)

    def test_structures_are_content_addressed(self) -> None:
        """A re-fetch that returns different bytes must be detectable, not
        silently swapped under a run that already used the old file."""
        text = "ATOM      1  N   MET A   1       0.000   0.000   0.000  1.00  0.00"
        with client_returning(httpx.Response(200, text=text)) as client:
            first = structures.fetch_rcsb("1BTL", client=client)
        with client_returning(httpx.Response(200, text=text)) as client:
            again = structures.fetch_rcsb("1BTL", client=client)
        with client_returning(httpx.Response(200, text=text + "\n")) as client:
            changed = structures.fetch_rcsb("1BTL", client=client)

        assert first.content_hash == again.content_hash
        assert first.content_hash != changed.content_hash

    def test_a_predicted_structure_is_labelled_as_predicted(self) -> None:
        prediction = [{"pdbUrl": "https://example.invalid/p.pdb", "latestVersion": 4}]
        with client_returning(
            httpx.Response(200, json=prediction),
            httpx.Response(200, text="ATOM      1  N   MET A   1"),
        ) as client:
            fetched = structures.fetch_alphafold("P37957", client=client)

        assert fetched.is_predicted is True
        assert "Predicted, not experimental" in fetched.note
        assert "pLDDT" in fetched.note
