"""PDB-format structure parsing.

Only the columns that bear on residue identity and numbering are read. This is
fixed-column format, not whitespace-delimited: splitting on spaces breaks on
four-character atom names and on negative coordinates that run together, both of
which occur in real files.

mmCIF is not handled. A handful of very large RCSB entries are CIF-only, and
those currently fail with a message saying so rather than parsing to something
plausible-looking.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from codonlab.domain.aminoacid import MODIFIED_TO_ONE, THREE_TO_ONE, three_to_one
from codonlab.domain.numbering import ObservedResidue, ResidueSlot


class StructureParseError(ValueError):
    """The file is not parseable as PDB format."""


@dataclass(slots=True)
class Chain:
    chain_id: str
    residues: list[ObservedResidue] = field(default_factory=list)

    @property
    def sequence(self) -> str:
        return "".join(residue.residue for residue in self.residues)

    @property
    def length(self) -> int:
        return len(self.residues)

    @property
    def first(self) -> ResidueSlot | None:
        return self.residues[0].slot if self.residues else None

    @property
    def last(self) -> ResidueSlot | None:
        return self.residues[-1].slot if self.residues else None


@dataclass(slots=True)
class ParsedStructure:
    entry_id: str | None
    title: str | None
    chains: list[Chain]

    def chain(self, chain_id: str) -> Chain | None:
        for candidate in self.chains:
            if candidate.chain_id == chain_id:
                return candidate
        return None

    @property
    def protein_chains(self) -> list[Chain]:
        """Chains with enough residues to be a protein rather than a ligand."""
        return [chain for chain in self.chains if chain.length >= 20]


def _is_residue_record(record: str, residue_name: str) -> bool:
    if record == "ATOM":
        return True
    # Selenomethionine and other modified residues are HETATM but are part of
    # the chain. Excluding them would punch holes in every structure solved by
    # MAD phasing.
    return record == "HETATM" and residue_name in MODIFIED_TO_ONE


def parse_pdb(text: str) -> ParsedStructure:
    """Parse residues and author numbering out of a PDB-format file."""
    entry_id: str | None = None
    title_parts: list[str] = []
    chains: dict[str, Chain] = {}
    seen: set[tuple[str, int, str]] = set()
    saw_any_record = False

    for line in text.splitlines():
        record = line[:6].strip()

        if record == "HEADER" and len(line) >= 66:
            entry_id = line[62:66].strip() or None
            continue
        if record == "TITLE":
            title_parts.append(line[10:].strip())
            continue
        if record not in ("ATOM", "HETATM"):
            continue
        if len(line) < 27:
            continue

        saw_any_record = True
        residue_name = line[17:20].strip().upper()
        if not _is_residue_record(record, residue_name):
            continue

        # Alternate conformations describe the same residue more than once.
        # Take the primary one; anything else double-counts positions.
        alt_loc = line[16].strip()
        if alt_loc not in ("", "A"):
            continue

        chain_id = line[21].strip() or "A"
        try:
            number = int(line[22:26])
        except ValueError:
            continue
        insertion_code = line[26].strip() or None

        key = (chain_id, number, insertion_code or "")
        if key in seen:
            continue
        seen.add(key)

        chains.setdefault(chain_id, Chain(chain_id=chain_id)).residues.append(
            ObservedResidue(
                slot=ResidueSlot(number=number, insertion_code=insertion_code),
                residue=three_to_one(residue_name),
            )
        )

    if not saw_any_record:
        raise StructureParseError(
            "No ATOM or HETATM records found. This does not look like a "
            "PDB-format file; mmCIF (.cif) is not supported yet."
        )

    for chain in chains.values():
        # Files are usually already in order, but not guaranteed to be, and the
        # numbering logic downstream depends on it.
        chain.residues.sort(key=lambda residue: residue.slot.sort_key)

    return ParsedStructure(
        entry_id=entry_id,
        title=" ".join(part for part in title_parts if part) or None,
        chains=[chains[key] for key in sorted(chains)],
    )


def parse_seqres(text: str) -> dict[str, str]:
    """The full construct sequence per chain, including unresolved residues.

    SEQRES is what was in the crystallisation tube; ATOM records are what the
    density resolved. The difference between the two is exactly the set of
    residues that exist but are not visible, which is worth showing.
    """
    chains: dict[str, list[str]] = {}
    for line in text.splitlines():
        if line[:6].strip() != "SEQRES" or len(line) < 19:
            continue
        chain_id = line[11].strip() or "A"
        # SEQRES also lists waters, ions and ligands for the chain. Only
        # residues we recognise as amino acids belong in a protein sequence.
        names = [
            name
            for name in line[19:].split()
            if name.upper() in THREE_TO_ONE or name.upper() in MODIFIED_TO_ONE
        ]
        chains.setdefault(chain_id, []).extend(three_to_one(name) for name in names)
    return {chain_id: "".join(residues) for chain_id, residues in chains.items()}
