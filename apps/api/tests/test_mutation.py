"""Mutation codes must be unambiguous or refused. There is no third option."""

from __future__ import annotations

import pytest

from codonlab.domain.mutation import (
    Mutation,
    MutationParseError,
    format_mutation_set,
    parse_mutation,
    parse_mutation_set,
)


class TestParsing:
    def test_short_form(self) -> None:
        mutation = parse_mutation("A123V")
        assert (mutation.wild, mutation.position, mutation.mutant) == ("A", 123, "V")
        assert mutation.insertion_code is None

    def test_hgvs_form(self) -> None:
        assert parse_mutation("p.Ala123Val") == Mutation(wild="A", position=123, mutant="V")

    def test_both_forms_agree(self) -> None:
        assert parse_mutation("A123V") == parse_mutation("p.Ala123Val")

    def test_insertion_code_binds_to_the_position_not_the_mutant(self) -> None:
        """H100AY is His-100A to Tyr, not His-100 to Ala with a stray Y.

        Reading this the other way would silently place the mutation at the
        wrong residue in any structure that uses insertion codes.
        """
        mutation = parse_mutation("H100AY")
        assert mutation.wild == "H"
        assert mutation.position == 100
        assert mutation.insertion_code == "A"
        assert mutation.mutant == "Y"
        assert mutation.label == "100A"

    def test_lowercase_is_accepted(self) -> None:
        assert parse_mutation("a123v") == parse_mutation("A123V")

    @pytest.mark.parametrize(
        "code",
        ["", "   ", "123", "A123", "AV", "A0V", "A-5V", "B123V", "A123Z", "p.Xyz1Abc"],
    )
    def test_rejects_nonsense(self, code: str) -> None:
        with pytest.raises(MutationParseError):
            parse_mutation(code)

    def test_rejects_position_zero_because_numbering_is_one_based(self) -> None:
        with pytest.raises(MutationParseError):
            parse_mutation("A0V")


class TestRendering:
    def test_render_always_carries_the_scheme(self) -> None:
        """A code without its scheme is the error this product exists to avoid."""
        rendered = parse_mutation("A123V").render("UniProt P62593")
        assert "A123V" in rendered
        assert "p.Ala123Val" in rendered
        assert "UniProt P62593" in rendered

    def test_render_differs_by_scheme_for_the_same_residue(self) -> None:
        mutation = parse_mutation("A123V")
        assert mutation.render("UniProt P37957") != mutation.render("Mature protein")

    def test_hgvs_includes_the_insertion_code(self) -> None:
        assert parse_mutation("H100AY").hgvs() == "p.His100ATyr"


class TestMutationSets:
    def test_parses_slash_and_comma_separated(self) -> None:
        assert parse_mutation_set("A123V/L45M") == parse_mutation_set("A123V, L45M")

    def test_formats_in_position_order_so_a_set_has_one_spelling(self) -> None:
        assert format_mutation_set(parse_mutation_set("L45M/A123V")) == "L45M/A123V"
        assert format_mutation_set(parse_mutation_set("A123V/L45M")) == "L45M/A123V"

    def test_rejects_two_mutations_at_one_position(self) -> None:
        """Accepting this would produce a design that cannot be built."""
        with pytest.raises(MutationParseError, match="twice"):
            parse_mutation_set("A123V/A123L")

    def test_insertion_codes_are_distinct_positions(self) -> None:
        assert len(parse_mutation_set("H100AY/H100Y")) == 2

    def test_synonymous_substitution_is_flagged_not_rejected(self) -> None:
        """A123A is a real thing to request as a silent control."""
        assert parse_mutation("A123A").is_synonymous is True
        assert parse_mutation("A123V").is_synonymous is False
