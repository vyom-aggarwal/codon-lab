"""Amino acid nomenclature.

Reference data, not a scientific default: these are the IUPAC one- and
three-letter codes. Nothing here is a threshold or a convention that could be
chosen differently.
"""

from __future__ import annotations

# The 20 proteinogenic amino acids, plus the two encoded non-standard residues
# and the unknown placeholder that appears in structures.
ONE_TO_THREE: dict[str, str] = {
    "A": "Ala",
    "R": "Arg",
    "N": "Asn",
    "D": "Asp",
    "C": "Cys",
    "Q": "Gln",
    "E": "Glu",
    "G": "Gly",
    "H": "His",
    "I": "Ile",
    "L": "Leu",
    "K": "Lys",
    "M": "Met",
    "F": "Phe",
    "P": "Pro",
    "S": "Ser",
    "T": "Thr",
    "W": "Trp",
    "Y": "Tyr",
    "V": "Val",
    "U": "Sec",  # selenocysteine
    "O": "Pyl",  # pyrrolysine
    "X": "Xaa",  # unknown / unspecified
}

THREE_TO_ONE: dict[str, str] = {three.upper(): one for one, three in ONE_TO_THREE.items()}

# Residues that appear in PDB files but are not standard amino acids. MSE
# (selenomethionine) is by far the most common — it is a crystallographic
# substitution for methionine and must map back to M, or every structure solved
# by MAD phasing would fail to align against its own sequence.
MODIFIED_TO_ONE: dict[str, str] = {
    "MSE": "M",  # selenomethionine
    "SEC": "U",
    "PYL": "O",
    "HYP": "P",  # hydroxyproline
    "PCA": "E",  # pyroglutamate
    "CSO": "C",  # S-hydroxycysteine
    "PTR": "Y",  # phosphotyrosine
    "SEP": "S",  # phosphoserine
    "TPO": "T",  # phosphothreonine
    "MLY": "K",  # N-dimethyl-lysine
    "KCX": "K",  # lysine NZ-carboxylic acid
}

#: The 20 standard residues, for validating that a sequence is a protein.
STANDARD = frozenset("ACDEFGHIKLMNPQRSTVWY")


def three_to_one(code: str) -> str:
    """PDB residue name to one-letter code. Unrecognised residues become 'X'.

    Returning 'X' rather than raising is deliberate: a ligand or a modified
    residue in a structure must not stop a target from loading. It becomes a
    visible gap in the numbering rather than a crash.
    """
    key = code.strip().upper()
    if key in THREE_TO_ONE:
        return THREE_TO_ONE[key]
    return MODIFIED_TO_ONE.get(key, "X")


def one_to_three(code: str) -> str:
    return ONE_TO_THREE.get(code.strip().upper(), "Xaa")


def is_protein_sequence(sequence: str) -> bool:
    """True when every character is a residue code we recognise.

    Used to reject a nucleotide sequence pasted into the sequence box. 'ACGT'
    is a valid peptide in principle, so a short all-ACGT string is genuinely
    ambiguous and is accepted here; the length and composition warning belongs
    in the UI, not in a boolean.
    """
    if not sequence:
        return False
    return all(character in ONE_TO_THREE for character in sequence.upper())
