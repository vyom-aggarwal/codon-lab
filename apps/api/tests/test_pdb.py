"""PDB parsing.

The fixture is built field by field rather than pasted, because PDB is a
fixed-column format and a test written with hand-counted spaces would pass
against a parser that splits on whitespace — which breaks on real files with
four-character atom names or run-together negative coordinates.
"""

from __future__ import annotations

import pytest

from codonlab.domain.numbering import reconcile
from codonlab.sources.pdb import ParsedStructure, StructureParseError, parse_pdb, parse_seqres


def atom(
    serial: int,
    name: str,
    resname: str,
    chain: str,
    resseq: int,
    icode: str = " ",
    alt: str = " ",
    record: str = "ATOM",
) -> str:
    """One record, placed on the columns the format actually specifies."""
    return (
        f"{record:<6}{serial:>5} {name:^4}{alt}{resname:>3} {chain}{resseq:>4}{icode}"
        f"   {0.0:8.3f}{0.0:8.3f}{0.0:8.3f}{1.0:6.2f}{0.0:6.2f}"
    )


def residue(serial: int, resname: str, chain: str, resseq: int, **kwargs: str) -> list[str]:
    """Backbone atoms for one residue, as a real file would carry them."""
    return [
        atom(serial + offset, name, resname, chain, resseq, **kwargs)
        for offset, name in enumerate(("N", "CA", "C", "O"))
    ]


class TestParsing:
    def test_reads_residues_in_author_numbering(self) -> None:
        lines = residue(1, "MET", "A", 1) + residue(5, "LYS", "A", 2) + residue(9, "ALA", "A", 3)
        structure = parse_pdb("\n".join(lines))
        chain = structure.chain("A")
        assert chain is not None
        assert chain.sequence == "MKA"
        assert [r.slot.number for r in chain.residues] == [1, 2, 3]

    def test_author_numbering_may_start_anywhere(self) -> None:
        lines = residue(1, "MET", "A", 26) + residue(5, "LYS", "A", 27)
        chain = parse_pdb("\n".join(lines)).chain("A")
        assert chain is not None
        assert chain.first is not None and chain.first.number == 26

    def test_selenomethionine_is_part_of_the_chain(self) -> None:
        """MSE is HETATM but is a methionine. Dropping it would punch a hole in
        every structure solved by MAD phasing."""
        lines = residue(1, "MET", "A", 1) + residue(5, "MSE", "A", 2, record="HETATM")
        chain = parse_pdb("\n".join(lines)).chain("A")
        assert chain is not None
        assert chain.sequence == "MM"

    def test_water_and_ligands_are_not_residues(self) -> None:
        lines = [
            *residue(1, "MET", "A", 1),
            atom(9, "O", "HOH", "A", 401, record="HETATM"),
            atom(10, "ZN", "ZN", "A", 402, record="HETATM"),
        ]
        chain = parse_pdb("\n".join(lines)).chain("A")
        assert chain is not None
        assert chain.sequence == "M"

    def test_alternate_conformations_do_not_double_count(self) -> None:
        lines = [
            *residue(1, "MET", "A", 1),
            *residue(5, "SER", "A", 2, alt="A"),
            *residue(9, "SER", "A", 2, alt="B"),
        ]
        chain = parse_pdb("\n".join(lines)).chain("A")
        assert chain is not None
        assert chain.sequence == "MS"
        assert chain.length == 2

    def test_insertion_codes_are_preserved(self) -> None:
        lines = [
            *residue(1, "HIS", "A", 100),
            *residue(5, "ALA", "A", 100, icode="A"),
            *residue(9, "LEU", "A", 101),
        ]
        chain = parse_pdb("\n".join(lines)).chain("A")
        assert chain is not None
        assert [slot.label for slot in (r.slot for r in chain.residues)] == ["100", "100A", "101"]

    def test_chains_are_separated(self) -> None:
        lines = residue(1, "MET", "A", 1) + residue(5, "LYS", "B", 1)
        structure = parse_pdb("\n".join(lines))
        assert [chain.chain_id for chain in structure.chains] == ["A", "B"]

    def test_unknown_residue_becomes_x_rather_than_failing(self) -> None:
        lines = residue(1, "MET", "A", 1) + residue(5, "UNK", "A", 2)
        chain = parse_pdb("\n".join(lines)).chain("A")
        assert chain is not None
        assert chain.sequence == "MX"

    def test_header_and_title(self) -> None:
        text = "\n".join(
            [
                f"{'HEADER':<62}1BTL",
                f"{'TITLE':<10}BETA-LACTAMASE TEM-1",
                *residue(1, "MET", "A", 1),
            ]
        )
        structure = parse_pdb(text)
        assert structure.entry_id == "1BTL"
        assert structure.title == "BETA-LACTAMASE TEM-1"

    def test_a_file_with_no_atoms_is_refused(self) -> None:
        with pytest.raises(StructureParseError, match="mmCIF"):
            parse_pdb("data_1ABC\n_entry.id 1ABC\n")


class TestSeqres:
    def test_reads_the_full_construct_including_unresolved_residues(self) -> None:
        text = f"{'SEQRES':<6}{1:>4} A{5:>5}  MET LYS ALA ILE LEU"
        assert parse_seqres(text)["A"] == "MKAIL"

    def test_ignores_waters_and_ligands(self) -> None:
        text = f"{'SEQRES':<6}{1:>4} A{3:>5}  MET HOH LYS"
        assert parse_seqres(text)["A"] == "MK"


class TestParsingFeedsNumbering:
    def test_a_parsed_chain_reconciles_against_its_sequence(self) -> None:
        """The two halves of Phase 2 have to meet: what the parser produces is
        exactly what reconciliation consumes."""
        sequence = "MKAILVVLLY"
        names = {
            "M": "MET",
            "K": "LYS",
            "A": "ALA",
            "I": "ILE",
            "L": "LEU",
            "V": "VAL",
            "Y": "TYR",
        }
        lines: list[str] = []
        for index, residue_code in enumerate(sequence):
            lines += residue(index * 4 + 1, names[residue_code], "A", index + 26)

        chain = parse_pdb("\n".join(lines)).chain("A")
        assert chain is not None

        result = reconcile(sequence, chain.residues)
        assert result.coverage == 1.0
        assert result.mismatches == ()
        first = result.mapping[0]
        assert first is not None and first.number == 26


def test_protein_chains_excludes_short_peptides() -> None:
    lines: list[str] = []
    for index in range(25):
        lines += residue(index * 4 + 1, "ALA", "A", index + 1)
    lines += residue(200, "ALA", "B", 1)
    structure: ParsedStructure = parse_pdb("\n".join(lines))
    assert [chain.chain_id for chain in structure.protein_chains] == ["A"]
