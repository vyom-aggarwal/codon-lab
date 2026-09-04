"""Does this DNA actually encode the protein we hold?

A site-directed mutagenesis primer anneals to the construct **on the bench**.
Everything downstream of this module — primer position, flanking arms, melting
temperature — is computed against the sequence pasted here, so if it is not the
user's real plasmid the primers will not anneal and the failure costs a
synthesis order and a week.

That is why the coding sequence is pasted rather than fetched. `ARCHITECTURE.md`
§16 records the decision and the rejected alternative: an ENA/EMBL cross-reference
returns the *reference* CDS, usually codon-optimised differently and often
tagged, and back-translating the protein through a usage table invents a
plausible sequence that is nobody's plasmid. Both would produce primers that look
correct and do not work.

So the only check worth having is the one this module performs: **translate what
was pasted and require it to equal the protein already stored.** The
translation itself is biotite's, not ours — the same rule §11 applies to the
van der Waals radii. A hand-typed genetic code is sixty-four opportunities to
introduce a silent error, and a single wrong codon would mistranslate one residue
and pass every other check here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import biotite.sequence as bioseq

#: A stop codon, as biotite renders it in a translated sequence.
STOP = "*"

#: What a pasted sequence may contain besides bases. FASTA headers, the digits
#: and spaces of a numbered listing, and line breaks all survive a copy out of
#: SnapGene, Benchling or a supplier's confirmation email — stripping them is
#: convenience, not interpretation, so it happens silently.
_HEADER = re.compile(r"^>.*$", re.MULTILINE)
_NOISE = re.compile(r"[\s\d]+")


@dataclass(frozen=True, slots=True)
class TranslationCheck:
    """The verdict, and enough to act on it.

    `ok` is the only thing that may gate an attachment. Everything else exists so
    that a refusal tells the user what is wrong with *their* sequence rather than
    that it "failed validation".
    """

    ok: bool
    #: What the DNA translates to, when it could be translated at all.
    protein: str | None = None
    #: Why it was refused, in the user's terms.
    reason: str | None = None
    #: What would fix it.
    remedy: str | None = None
    #: 1-based residue where the translation first disagrees with the stored
    #: protein. None when the lengths differ before any residue does, or when
    #: the failure is not a mismatch at all.
    first_difference: int | None = None
    #: Set when the translation contains the stored protein at a constant
    #: offset — the signal-peptide case. Reported rather than accepted.
    offset: int | None = None


def clean(pasted: str) -> str:
    """Strip what a paste carries and normalise case. Not interpretation."""
    without_headers = _HEADER.sub("", pasted or "")
    return _NOISE.sub("", without_headers).upper()


def validate(pasted: str, *, protein: str) -> TranslationCheck:
    """Check that `pasted` encodes exactly `protein`.

    Accepts a trailing stop codon, because a CDS usually carries one and the
    stored protein never does. Rejects everything else — including a translation
    that merely *contains* the protein, which is the signal-peptide case and is
    reported with its offset rather than quietly accepted. Getting that wrong
    would shift every primer by the length of the leader.
    """
    dna = clean(pasted)
    if not dna:
        return TranslationCheck(
            ok=False,
            reason="No sequence was provided.",
            remedy="Paste the coding sequence of the construct on your bench.",
        )

    illegal = sorted(set(dna) - set("ACGT"))
    if illegal:
        return TranslationCheck(
            ok=False,
            reason=f"The sequence contains {', '.join(illegal)}, which are not bases.",
            remedy=(
                "Paste unambiguous DNA. Ambiguity codes such as N are refused rather "
                "than guessed: a primer designed over an unknown base is a primer "
                "that may not anneal."
            ),
        )

    if len(dna) % 3 != 0:
        return TranslationCheck(
            ok=False,
            reason=(
                f"The sequence is {len(dna):,} bases, which is not a whole number of "
                f"codons ({len(dna) % 3} left over)."
            ),
            remedy=(
                "Paste the coding sequence only — from the start codon through the "
                "stop — with no promoter, tag or vector backbone attached."
            ),
        )

    translated = str(bioseq.NucleotideSequence(dna).translate(complete=True))
    body = translated[:-1] if translated.endswith(STOP) else translated

    internal = body.find(STOP)
    if internal >= 0:
        return TranslationCheck(
            ok=False,
            protein=translated,
            reason=f"There is a stop codon at codon {internal + 1}, before the end.",
            remedy=(
                "Check the reading frame. A sequence that is a whole number of codons "
                "can still be out of frame if it does not begin at the start codon."
            ),
        )

    if body == protein:
        return TranslationCheck(ok=True, protein=body)

    at = body.find(protein)
    if at > 0:
        return TranslationCheck(
            ok=False,
            protein=body,
            offset=at,
            reason=(
                f"This translates to {len(body):,} residues that contain the stored "
                f"{len(protein):,}-residue protein starting at residue {at + 1} — a "
                f"leader of {at} residues, which is the length of a signal peptide."
            ),
            remedy=(
                "Paste the coding sequence for the protein this project actually "
                "holds. Trimming the leader here is not offered on purpose: every "
                "primer position would shift by its length, and a primer at the "
                "wrong position anneals to nothing."
            ),
        )

    difference = next(
        (index for index, (a, b) in enumerate(zip(body, protein, strict=False)) if a != b),
        None,
    )
    if difference is not None:
        return TranslationCheck(
            ok=False,
            protein=body,
            first_difference=difference + 1,
            reason=(
                f"This translates to a different protein. The first difference is at "
                f"residue {difference + 1}: the DNA gives {body[difference]}, the "
                f"stored protein has {protein[difference]}."
            ),
            remedy=(
                "Check that this is the construct for this target, and that it is in "
                "frame."
            ),
        )

    return TranslationCheck(
        ok=False,
        protein=body,
        reason=(
            f"This translates to {len(body):,} residues; the stored protein is "
            f"{len(protein):,}. They agree as far as the shorter one goes."
        ),
        remedy=(
            "Paste the full coding sequence for this protein — a truncation would "
            "produce primers for positions the construct does not contain."
        ),
    )
