"""UniProt sequence retrieval.

The signal peptide is fetched deliberately. It is the source of the most common
numbering disagreement in this domain: UniProt numbers from the initiator
methionine of the full-length product, while the literature and the bench
usually number from the first residue of the mature protein. For B. subtilis
lipase A that is a 31-residue difference on every mutation code.

The offset is reported as a *candidate* scheme. Nothing here picks it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from codonlab.domain.aminoacid import is_protein_sequence

BASE = "https://rest.uniprot.org/uniprotkb"
TIMEOUT = httpx.Timeout(20.0, connect=10.0)

ACCESSION = re.compile(
    r"^(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})$",
    re.IGNORECASE,
)


class SourceError(RuntimeError):
    """A retrieval failed in a way the interface should explain, not retry."""

    def __init__(self, message: str, remedy: str) -> None:
        super().__init__(message)
        self.remedy = remedy


@dataclass(frozen=True, slots=True)
class SignalPeptide:
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start + 1


@dataclass(frozen=True, slots=True)
class AnnotatedFeature:
    """A residue annotation from the UniProt record.

    Positions are in the record's own full-length numbering. They are never
    used directly as constraints — they are translated through the target's
    canonical numbering scheme first, because that is exactly the 25-residue
    error the numbering subsystem exists to prevent.
    """

    kind: str
    start: int
    end: int
    description: str | None = None


@dataclass(frozen=True, slots=True)
class UniProtRecord:
    accession: str
    name: str
    organism: str | None
    sequence: str
    signal_peptide: SignalPeptide | None
    features: tuple[AnnotatedFeature, ...] = ()

    @property
    def length(self) -> int:
        return len(self.sequence)

    @property
    def mature_offset(self) -> int | None:
        """Offset from full-length numbering to mature-protein numbering.

        None when the record declares no signal peptide, in which case there is
        no second scheme to offer.
        """
        if self.signal_peptide is None:
            return None
        return -self.signal_peptide.end


def is_accession(text: str) -> bool:
    return bool(ACCESSION.match(text.strip()))


def _extract_signal(payload: dict[str, Any]) -> SignalPeptide | None:
    for feature in payload.get("features", []):
        if feature.get("type") != "Signal":
            continue
        location = feature.get("location", {})
        start = location.get("start", {}).get("value")
        end = location.get("end", {}).get("value")
        if isinstance(start, int) and isinstance(end, int):
            return SignalPeptide(start=start, end=end)
    return None


def _extract_name(payload: dict[str, Any]) -> str:
    description = payload.get("proteinDescription", {})
    recommended = description.get("recommendedName", {}).get("fullName", {}).get("value")
    if recommended:
        return str(recommended)
    submitted = description.get("submissionNames", [])
    if submitted:
        value = submitted[0].get("fullName", {}).get("value")
        if value:
            return str(value)
    return str(payload.get("uniProtkbId") or payload.get("primaryAccession") or "Unknown")


def fetch(accession: str, *, client: httpx.Client | None = None) -> UniProtRecord:
    """Retrieve one UniProt entry."""
    accession = accession.strip().upper()
    if not is_accession(accession):
        raise SourceError(
            f"{accession!r} is not a UniProt accession.",
            "Accessions look like P62593 or A0A0B4J2F0.",
        )

    owned = client is None
    http = client or httpx.Client(timeout=TIMEOUT, follow_redirects=True)
    try:
        response = http.get(f"{BASE}/{accession}.json")
    except httpx.HTTPError as error:
        raise SourceError(
            f"Could not reach UniProt: {error}.",
            "Check network access from the api container, then retry.",
        ) from error
    finally:
        if owned:
            http.close()

    if response.status_code == 404:
        raise SourceError(
            f"UniProt has no entry {accession}.",
            "Check the accession, or paste the sequence directly instead.",
        )
    if response.status_code != 200:
        raise SourceError(
            f"UniProt returned {response.status_code} for {accession}.",
            "This is usually transient. Retry in a moment.",
        )

    payload = response.json()
    sequence = payload.get("sequence", {}).get("value", "")
    if not sequence or not is_protein_sequence(sequence):
        raise SourceError(
            f"UniProt entry {accession} has no usable protein sequence.",
            "Paste the sequence directly instead.",
        )

    organism = payload.get("organism", {}).get("scientificName")
    return UniProtRecord(
        accession=payload.get("primaryAccession", accession),
        name=_extract_name(payload),
        organism=str(organism) if organism else None,
        sequence=sequence.upper(),
        signal_peptide=_extract_signal(payload),
        features=_extract_features(payload),
    )


#: UniProt feature types that correspond to a design constraint. Everything
#: else in the record — secondary structure, natural variants, sequence
#: conflicts — describes the protein rather than restricting where it may be
#: mutated, and is not imported.
CONSTRAINT_FEATURES = frozenset(
    {"Active site", "Binding site", "Site", "Disulfide bond", "Signal", "Metal binding"}
)


def _extract_features(payload: dict[str, Any]) -> tuple[AnnotatedFeature, ...]:
    found: list[AnnotatedFeature] = []
    for feature in payload.get("features", []):
        kind = feature.get("type")
        if kind not in CONSTRAINT_FEATURES:
            continue
        location = feature.get("location", {})
        start = location.get("start", {}).get("value")
        end = location.get("end", {}).get("value")
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        found.append(
            AnnotatedFeature(
                kind=str(kind),
                start=start,
                end=end,
                description=feature.get("description") or None,
            )
        )
    return tuple(found)
