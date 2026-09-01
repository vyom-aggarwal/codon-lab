"""FASTA parsing for pasted sequences."""

from __future__ import annotations

from dataclasses import dataclass

from codonlab.domain.aminoacid import ONE_TO_THREE, STANDARD

#: Unambiguous nucleotide alphabet. A short peptide can legitimately be all
#: ACGT, so this is used to warn, never to reject.
NUCLEOTIDES = frozenset("ACGTUN")


class FastaError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PastedSequence:
    header: str | None
    sequence: str

    @property
    def length(self) -> int:
        return len(self.sequence)

    @property
    def looks_like_nucleotides(self) -> bool:
        """True when the sequence is long and uses only nucleotide letters.

        Surfaced as a warning on the setup screen. Pasting a gene instead of a
        protein is a common slip, and every residue number downstream would be
        wrong in a way that looks superficially fine.
        """
        if self.length < 30:
            return False
        return set(self.sequence) <= NUCLEOTIDES


def parse_fasta(text: str) -> PastedSequence:
    """Parse a single FASTA record, or a bare sequence with no header."""
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        raise FastaError("No sequence found.")

    header: str | None = None
    if lines[0].startswith(">"):
        header = lines[0][1:].strip() or None
        lines = lines[1:]

    if any(line.startswith(">") for line in lines):
        raise FastaError(
            "More than one FASTA record was pasted. Add one target at a time so "
            "its numbering can be reconciled on its own."
        )

    sequence = "".join(lines).replace(" ", "").replace("*", "").upper()
    if not sequence:
        raise FastaError("The record has a header but no sequence.")

    unknown = sorted(set(sequence) - set(ONE_TO_THREE))
    if unknown:
        raise FastaError(
            f"Not an amino acid sequence: unexpected {', '.join(unknown)}. "
            "Gaps and alignment characters must be removed first."
        )

    return PastedSequence(header=header, sequence=sequence)


def non_standard_positions(sequence: str) -> tuple[int, ...]:
    """1-based positions holding something other than the standard 20.

    Selenocysteine, pyrrolysine and X are accepted into a target but cannot be
    designed against, so the positions are flagged rather than silently kept.
    """
    return tuple(index + 1 for index, residue in enumerate(sequence) if residue not in STANDARD)
