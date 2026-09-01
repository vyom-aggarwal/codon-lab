"""Maximum allowed solvent accessibility per residue type.

The denominator of relative solvent accessibility. RSA = ASA / MaxASA, so this
table decides which residues are called buried, and changing it moves residues
across the core/surface boundary without changing a single coordinate.

Source
------
Tien MZ, Meyer AG, Sydykova DK, Spielman SJ, Wilke CO (2013).
"Maximum Allowed Solvent Accessibilites of Residues in Proteins."
PLoS ONE 8(11): e80635. https://doi.org/10.1371/journal.pone.0080635

Table 1, **Theoretical** column — the Gly-X-Gly tripeptide maxima. Transcribed
from the publisher's manuscript XML, not from a secondary source.

Why the theoretical column and not the alternatives
---------------------------------------------------
The same paper tabulates Miller et al. (1987) and Rose et al. (1985) for
comparison. Both understate the maxima — on TEM-1 (PDB 1BTL, 263 residues),
switching this table to Miller's values moves 27 residues (10.3%) across a
region boundary and produces residues at RSA 1.00, where the theoretical set
tops out at 0.84 on the same coordinates. A scale that saturates cannot
distinguish "fully exposed" from "more exposed than the reference allows".

**This is the only copy of these numbers in the codebase.** A second copy is a
second answer to which residues are buried.
"""

from __future__ import annotations

#: Digital Object Identifier, carried into every run's provenance record so a
#: number on screen can be traced to the paper it was normalised against.
CITATION_DOI = "10.1371/journal.pone.0080635"

CITATION = (
    "Tien MZ, Meyer AG, Sydykova DK, Spielman SJ, Wilke CO (2013). Maximum Allowed "
    "Solvent Accessibilites of Residues in Proteins. PLoS ONE 8(11): e80635. "
    f"https://doi.org/{CITATION_DOI}"
)

#: Which column of Table 1 these values are, stated so the provenance record can
#: say it rather than implying it.
REFERENCE_SET = "Tien et al. 2013, theoretical (Gly-X-Gly tripeptide)"

#: Three-letter residue code to maximum ASA in square angstroms.
MAX_ASA: dict[str, float] = {
    "ALA": 129.0,
    "ARG": 274.0,
    "ASN": 195.0,
    "ASP": 193.0,
    "CYS": 167.0,
    "GLU": 223.0,
    "GLN": 225.0,
    "GLY": 104.0,
    "HIS": 224.0,
    "ILE": 197.0,
    "LEU": 201.0,
    "LYS": 236.0,
    "MET": 224.0,
    "PHE": 240.0,
    "PRO": 159.0,
    "SER": 155.0,
    "THR": 172.0,
    "TRP": 285.0,
    "TYR": 263.0,
    "VAL": 174.0,
}


def max_asa(residue_name: str) -> float | None:
    """The maximum ASA for a three-letter residue code, or None if unlisted.

    None rather than a fallback value: a modified or non-standard residue has no
    published maximum here, and dividing by a guessed one would produce an RSA
    that looks like every other RSA on the screen. The caller renders it as
    unavailable instead.
    """
    return MAX_ASA.get(residue_name.strip().upper())
