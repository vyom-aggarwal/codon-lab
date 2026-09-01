"""The structured objective a free-text goal parses into.

The single rule governing this module: **a parser extracts what the user said
and never supplies what they did not.** Every field is optional, and an absent
field means "not stated" — never a default that looks like a decision. A parse
that quietly filled in 50 °C because thermostability usually means about that
would be indistinguishable, on screen, from a number the scientist chose.

Nothing here is a scientific threshold. `TargetValue` records a number the user
wrote down, with the unit they wrote it in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Objective(StrEnum):
    """What the user is trying to improve.

    Deliberately coarse. A finer taxonomy would force the parser to choose
    between neighbouring categories on thin evidence, and the free-text detail
    is preserved alongside it anyway.
    """

    THERMOSTABILITY = "thermostability"
    ACTIVITY = "activity"
    EXPRESSION = "expression"
    SOLUBILITY = "solubility"
    BINDING_AFFINITY = "binding_affinity"
    SPECIFICITY = "specificity"
    SOLVENT_TOLERANCE = "solvent_tolerance"
    OTHER = "other"


class ParseMethod(StrEnum):
    RULES = "rules"
    CLAUDE = "claude"


@dataclass(frozen=True, slots=True)
class TargetValue:
    """A quantity the user stated, in the unit they stated it in.

    Never converted. "65 °C" is stored as 65 and "C", not normalised to kelvin,
    because the restatement shown back to the user has to read like the sentence
    they wrote.
    """

    value: float
    unit: str

    def render(self) -> str:
        return f"{self.value:g} {self.unit}".strip()


@dataclass(frozen=True, slots=True)
class Budget:
    """How many variants the user is willing to order, and at what cost."""

    variants: int | None = None
    amount: float | None = None
    currency: str | None = None

    @property
    def is_empty(self) -> bool:
        return self.variants is None and self.amount is None

    def render(self) -> str:
        parts: list[str] = []
        if self.variants is not None:
            parts.append(f"{self.variants} variants")
        if self.amount is not None:
            currency = f"{self.currency} " if self.currency else ""
            parts.append(f"{currency}{self.amount:,.0f}")
        return ", ".join(parts)


@dataclass(frozen=True, slots=True)
class GoalSpec:
    """The parsed objective, shown back as editable chips before anything runs."""

    objective: Objective | None = None
    #: The user's own words for the objective, kept verbatim.
    objective_detail: str | None = None
    target_value: TargetValue | None = None
    #: Properties to hold constant, e.g. "preserve catalytic activity".
    preserve: tuple[str, ...] = ()
    budget: Budget = field(default_factory=Budget)
    expression_host: str | None = None
    assay: str | None = None
    #: Phrases the parser could not place. Shown to the user rather than
    #: dropped — a silently ignored clause is a misread goal.
    unparsed: tuple[str, ...] = ()

    @property
    def missing_required(self) -> tuple[str, ...]:
        """Fields a run genuinely cannot proceed without.

        Only the objective. Budget, host and assay shape the handoff and the
        report, but a design run can be computed without them, and demanding
        them would be inventing a requirement the science does not have.
        """
        return () if self.objective is not None else ("objective",)

    @property
    def is_runnable(self) -> bool:
        return not self.missing_required


@dataclass(frozen=True, slots=True)
class ParsedGoal:
    """A parse, plus everything needed to judge how much to trust it."""

    raw_text: str
    spec: GoalSpec
    method: ParseMethod
    #: Present only for the rule-based parser, which can say which patterns
    #: fired. A language model's parse is confirmed by reading it, not by a
    #: number it made up about itself.
    matched_phrases: tuple[str, ...] = ()
    note: str = ""

    @property
    def needs_review_badge(self) -> bool:
        """The rule parser matches keywords, not sentences. Its output is
        always badged so it is never mistaken for a reading of the goal."""
        return self.method is ParseMethod.RULES


def restate(spec: GoalSpec) -> str:
    """A plain-English restatement of the parse, shown above the run button.

    Written from the parsed fields rather than the original text, so that a
    misparse reads wrong. A restatement that echoes the input would look
    correct no matter what the parser actually understood.
    """
    if spec.objective is None:
        return "No objective identified yet."

    subject = spec.objective.value.replace("_", " ")
    sentence = f"Improve {subject}"
    if spec.target_value is not None:
        sentence += f", targeting {spec.target_value.render()}"
    if spec.preserve:
        sentence += f", while preserving {', '.join(spec.preserve)}"
    sentence += "."

    if spec.expression_host:
        sentence += f" Expressed in {spec.expression_host}."
    if spec.assay:
        sentence += f" Measured by {spec.assay}."
    if not spec.budget.is_empty:
        sentence += f" Budget: {spec.budget.render()}."
    return sentence


#: Shown on the goal composer before the run, never after. A scientist deciding
#: whether to spend ordering budget needs the limits stated up front.
EXPECTATIONS: dict[str, list[str]] = {
    "will": [
        "Rank candidate point mutations by the predictors available for this objective.",
        "Show each predictor's score separately, including where they disagree.",
        "Filter out variants at constrained positions, and keep them retrievable "
        "with the reason they were filtered.",
        "Trace every number to the model version and run that produced it.",
    ],
    "will_not": [
        "Predict a melting temperature in degrees. Stability predictions are "
        "reported as a change in folding free energy, which does not convert to "
        "a Tm shift.",
        "Account for effects it has no model for, including expression, "
        "aggregation, and anything downstream of the purified protein.",
        "Model how mutations interact. Stacked mutations are assumed additive, "
        "and that assumption is often wrong.",
        "Replace a bench measurement. Every ranking here is a hypothesis until you measure it.",
    ],
}


def spec_to_json(spec: GoalSpec) -> dict[str, Any]:
    """Serialise for storage on `Goal.parsed_spec`."""
    return {
        "objective": spec.objective.value if spec.objective else None,
        "objective_detail": spec.objective_detail,
        "target_value": (
            None
            if spec.target_value is None
            else {"value": spec.target_value.value, "unit": spec.target_value.unit}
        ),
        "preserve": list(spec.preserve),
        "budget": {
            "variants": spec.budget.variants,
            "amount": spec.budget.amount,
            "currency": spec.budget.currency,
        },
        "expression_host": spec.expression_host,
        "assay": spec.assay,
        "unparsed": list(spec.unparsed),
    }


def spec_from_json(payload: dict[str, Any]) -> GoalSpec:
    """Rebuild a spec from storage, or from the user's edited chips."""
    objective_raw = payload.get("objective")
    target_raw = payload.get("target_value") or {}
    budget_raw = payload.get("budget") or {}

    return GoalSpec(
        objective=Objective(objective_raw) if objective_raw else None,
        objective_detail=payload.get("objective_detail"),
        target_value=(
            TargetValue(value=float(target_raw["value"]), unit=str(target_raw["unit"]))
            if target_raw.get("value") is not None and target_raw.get("unit")
            else None
        ),
        preserve=tuple(payload.get("preserve") or ()),
        budget=Budget(
            variants=budget_raw.get("variants"),
            amount=budget_raw.get("amount"),
            currency=budget_raw.get("currency"),
        ),
        expression_host=payload.get("expression_host"),
        assay=payload.get("assay"),
        unparsed=tuple(payload.get("unparsed") or ()),
    )
