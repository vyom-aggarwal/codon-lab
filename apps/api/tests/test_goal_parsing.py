"""Goal parsing.

The property under test throughout: **the parser records what was said and
never supplies what was not.** A parse that fills in a plausible default is
indistinguishable on screen from a number the scientist chose, which is the
failure this whole subsystem exists to prevent.
"""

from __future__ import annotations

import pytest

from codonlab.domain.goal import EXPECTATIONS, GoalSpec, Objective, ParseMethod, restate
from codonlab.parsers import rules


class TestObjective:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("make this enzyme survive 65C without killing activity", Objective.THERMOSTABILITY),
            ("improve the melting temperature", Objective.THERMOSTABILITY),
            ("raise Tm by a few degrees", Objective.THERMOSTABILITY),
            ("improve tolerance to organic cosolvent", Objective.SOLVENT_TOLERANCE),
            ("increase expression yield in E. coli", Objective.EXPRESSION),
            ("reduce aggregation and improve solubility", Objective.SOLUBILITY),
            ("tighten binding affinity for the substrate", Objective.BINDING_AFFINITY),
            ("improve kcat", Objective.ACTIVITY),
            ("make the enzyme more selective", Objective.SPECIFICITY),
        ],
    )
    def test_identifies_the_objective(self, text: str, expected: Objective) -> None:
        assert rules.parse(text).spec.objective is expected

    def test_solvent_tolerance_wins_over_generic_stability(self) -> None:
        """Both keywords are present; the more specific reading is correct."""
        result = rules.parse("improve stability in organic solvent")
        assert result.spec.objective is Objective.SOLVENT_TOLERANCE

    def test_an_unrecognised_goal_yields_no_objective(self) -> None:
        """Silence, not a guess. The UI reports the objective as required."""
        result = rules.parse("do something clever with this protein")
        assert result.spec.objective is None
        assert result.spec.is_runnable is False
        assert result.spec.missing_required == ("objective",)


class TestStatedValues:
    def test_reads_a_temperature_in_the_unit_written(self) -> None:
        spec = rules.parse("make it survive 65 °C").spec
        assert spec.target_value is not None
        assert spec.target_value.value == 65.0
        assert spec.target_value.unit == "°C"

    def test_does_not_convert_units(self) -> None:
        """149 F stays 149 F. A converted number is not the one they wrote."""
        spec = rules.parse("thermostable up to 149 F").spec
        assert spec.target_value is not None
        assert spec.target_value.value == 149.0
        assert spec.target_value.unit == "°F"

    def test_no_temperature_means_no_target(self) -> None:
        """The single most important negative case: 'more thermostable' has no
        number in it, and inventing one is the failure this product refuses."""
        assert rules.parse("make this more thermostable").spec.target_value is None

    def test_a_temperature_is_not_a_target_for_a_non_thermal_objective(self) -> None:
        """65 C in a solvent-tolerance goal is an assay condition, not a goal."""
        spec = rules.parse("improve solvent tolerance, assayed at 37 C").spec
        assert spec.objective is Objective.SOLVENT_TOLERANCE
        assert spec.target_value is None

    def test_a_bare_number_is_not_a_temperature(self) -> None:
        assert (
            rules.parse("make this enzyme survive 65 without losing activity").spec.target_value
            is None
        )


class TestPreserve:
    @pytest.mark.parametrize(
        "text",
        [
            "more thermostable without killing activity",
            "more thermostable while preserving activity",
            "more thermostable, don't lose activity",
        ],
    )
    def test_reads_what_must_be_held_constant(self, text: str) -> None:
        assert "activity" in " ".join(rules.parse(text).spec.preserve).lower()

    def test_keeps_the_users_words(self) -> None:
        spec = rules.parse("thermostable without losing catalytic efficiency").spec
        assert spec.preserve == ("catalytic efficiency",)

    def test_nothing_stated_means_nothing_preserved(self) -> None:
        assert rules.parse("make this more thermostable").spec.preserve == ()


class TestBudget:
    def test_reads_a_variant_count(self) -> None:
        assert rules.parse("thermostability, 48 variants").spec.budget.variants == 48

    def test_reads_a_plate_as_its_well_count(self) -> None:
        """Labs budget in plates; 96 wells is 96 variants."""
        assert rules.parse("thermostability, one 96-well plate").spec.budget.variants == 96

    def test_reads_money_with_its_currency(self) -> None:
        budget = rules.parse("thermostability on a $4,000 budget").spec.budget
        assert budget.amount == 4000.0
        assert budget.currency == "USD"

    def test_reads_thousands_shorthand(self) -> None:
        assert rules.parse("thermostability, £5k budget").spec.budget.amount == 5000.0

    def test_no_budget_stated_is_empty_not_zero(self) -> None:
        """Zero would read as 'cannot order anything'."""
        budget = rules.parse("make this more thermostable").spec.budget
        assert budget.is_empty
        assert budget.variants is None and budget.amount is None


class TestHostAndAssay:
    def test_reads_the_expression_host(self) -> None:
        assert rules.parse("thermostability, expressed in E. coli").spec.expression_host == (
            "Escherichia coli"
        )

    def test_prefers_a_named_yeast_over_bare_yeast(self) -> None:
        assert rules.parse("expression in Pichia yeast").spec.expression_host == "Pichia pastoris"

    def test_reads_the_assay(self) -> None:
        assert rules.parse("thermostability measured by DSF").spec.assay == (
            "Differential scanning fluorimetry"
        )

    def test_nothing_stated_means_none(self) -> None:
        spec = rules.parse("make this more thermostable").spec
        assert spec.expression_host is None
        assert spec.assay is None


class TestUnparsedClauses:
    def test_surfaces_what_it_could_not_place(self) -> None:
        """A dropped clause is a clause the user believes was understood."""
        result = rules.parse("make it thermostable and please avoid the his-tag region entirely")
        assert result.spec.unparsed != ()
        assert any("his-tag" in clause.lower() for clause in result.spec.unparsed)

    def test_a_fully_understood_goal_leaves_little_behind(self) -> None:
        result = rules.parse("improve thermostability to 65 C in E. coli")
        assert len(result.spec.unparsed) <= 1


class TestBadging:
    def test_a_rule_based_parse_is_always_badged(self) -> None:
        """It matches phrases; it does not read sentences. The user must know."""
        result = rules.parse("make this more thermostable")
        assert result.method is ParseMethod.RULES
        assert result.needs_review_badge is True
        assert "keyword" in result.note.lower()

    def test_empty_input_does_not_raise(self) -> None:
        assert rules.parse("").spec.objective is None


class TestRestatement:
    def test_restates_from_the_parse_not_the_input(self) -> None:
        """Echoing the input would look correct regardless of what was
        understood. The restatement is built from the parsed fields so a
        misparse reads wrong."""
        spec = rules.parse(
            "make this enzyme survive 65 C without killing activity, in E. coli"
        ).spec
        sentence = restate(spec)
        assert "thermostability" in sentence
        assert "65 °C" in sentence
        assert "activity" in sentence
        assert "Escherichia coli" in sentence

    def test_says_so_when_there_is_no_objective(self) -> None:
        assert "No objective" in restate(GoalSpec())

    def test_omits_what_was_never_stated(self) -> None:
        sentence = restate(rules.parse("make this more thermostable").spec)
        assert "targeting" not in sentence
        assert "Budget" not in sentence


class TestExpectations:
    def test_states_that_it_will_not_predict_a_tm_shift(self) -> None:
        """The specification's hardest honesty requirement, shown before the
        run rather than explained after a surprising result."""
        combined = " ".join(EXPECTATIONS["will_not"]).lower()
        assert "melting temperature" in combined
        assert "additive" in combined
        assert EXPECTATIONS["will"] and EXPECTATIONS["will_not"]
