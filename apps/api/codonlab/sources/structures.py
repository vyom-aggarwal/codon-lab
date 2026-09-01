"""Structure retrieval: RCSB PDB and the AlphaFold database.

Both return PDB-format text, which `codonlab.sources.pdb` parses. Neither is a
`Predictor` — no model runs here, these are downloads — so they sit in
`sources/` rather than `providers/`.

A predicted structure and an experimental one are not interchangeable evidence,
so which source a structure came from is recorded on it and never averaged away.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

import httpx

from codonlab.models.enums import StructureSource
from codonlab.sources.uniprot import SourceError

RCSB_FILE = "https://files.rcsb.org/download"
ALPHAFOLD_API = "https://alphafold.ebi.ac.uk/api/prediction"
TIMEOUT = httpx.Timeout(45.0, connect=10.0)

PDB_ID = re.compile(r"^[0-9][A-Za-z0-9]{3}$")


@dataclass(frozen=True, slots=True)
class FetchedStructure:
    source: StructureSource
    identifier: str
    text: str
    #: Content address of the file, so a re-fetch that returns different bytes
    #: is detectable rather than silently replacing what a run was based on.
    content_hash: str
    note: str

    @property
    def is_predicted(self) -> bool:
        return self.source in (StructureSource.ALPHAFOLD_DB, StructureSource.ESMFOLD)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_pdb_id(text: str) -> bool:
    return bool(PDB_ID.match(text.strip()))


def _get(url: str, client: httpx.Client | None, *, what: str) -> httpx.Response:
    owned = client is None
    http = client or httpx.Client(timeout=TIMEOUT, follow_redirects=True)
    try:
        return http.get(url)
    except httpx.HTTPError as error:
        raise SourceError(
            f"Could not reach {what}: {error}.",
            "Check network access from the api container, then retry.",
        ) from error
    finally:
        if owned:
            http.close()


def fetch_rcsb(pdb_id: str, *, client: httpx.Client | None = None) -> FetchedStructure:
    """Download an experimental structure from RCSB."""
    identifier = pdb_id.strip().upper()
    if not is_pdb_id(identifier):
        raise SourceError(
            f"{pdb_id!r} is not a PDB id.",
            "PDB ids are four characters starting with a digit, such as 1BTL.",
        )

    response = _get(f"{RCSB_FILE}/{identifier}.pdb", client, what="RCSB")
    if response.status_code == 404:
        raise SourceError(
            f"RCSB has no PDB-format file for {identifier}.",
            "Very large entries are distributed only as mmCIF, which is not "
            "supported yet. Upload a PDB file instead.",
        )
    if response.status_code != 200:
        raise SourceError(
            f"RCSB returned {response.status_code} for {identifier}.",
            "This is usually transient. Retry in a moment.",
        )

    return FetchedStructure(
        source=StructureSource.PDB,
        identifier=identifier,
        text=response.text,
        content_hash=content_hash(response.text),
        note=f"Experimental structure {identifier} from RCSB.",
    )


def fetch_alphafold(accession: str, *, client: httpx.Client | None = None) -> FetchedStructure:
    """Download a predicted structure from the AlphaFold database.

    The per-residue pLDDT lives in the B-factor column of the returned file.
    It is a confidence score, not a temperature factor, and must be labelled as
    such wherever it is shown.
    """
    identifier = accession.strip().upper()
    response = _get(f"{ALPHAFOLD_API}/{identifier}", client, what="AlphaFold DB")

    if response.status_code == 404:
        raise SourceError(
            f"AlphaFold DB has no prediction for {identifier}.",
            "Upload a structure, or fetch an experimental one from RCSB.",
        )
    if response.status_code != 200:
        raise SourceError(
            f"AlphaFold DB returned {response.status_code} for {identifier}.",
            "This is usually transient. Retry in a moment.",
        )

    entries = response.json()
    if not entries:
        raise SourceError(
            f"AlphaFold DB returned no prediction for {identifier}.",
            "Upload a structure, or fetch an experimental one from RCSB.",
        )

    url = entries[0].get("pdbUrl")
    if not url:
        raise SourceError(
            f"The AlphaFold entry for {identifier} has no PDB-format file.",
            "Upload a structure instead.",
        )

    file_response = _get(url, client, what="AlphaFold DB")
    if file_response.status_code != 200:
        raise SourceError(
            f"Could not download the AlphaFold structure for {identifier}.",
            "This is usually transient. Retry in a moment.",
        )

    version = entries[0].get("latestVersion", "")
    return FetchedStructure(
        source=StructureSource.ALPHAFOLD_DB,
        identifier=identifier,
        text=file_response.text,
        content_hash=content_hash(file_response.text),
        note=(
            f"Predicted structure for {identifier} from AlphaFold DB"
            f"{f' (v{version})' if version else ''}. "
            "Predicted, not experimental — per-residue confidence is pLDDT, "
            "carried in the B-factor column."
        ),
    )
