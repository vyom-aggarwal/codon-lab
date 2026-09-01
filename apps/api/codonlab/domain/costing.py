"""What a design set costs to order, from prices the lab stated.

Specification §5.7 asks for "running budget and cost estimate". This module
computes one and, more often than you might expect, refuses to.

**No price is ever invented.** Oligo and synthesis pricing varies by vendor, by
scale, by contract and by country, and the whole reason this product exists is a
scientist deciding whether to spend $4,000 of ordering budget (`BRIEF.md` §1). A
plausible-looking default here would be a fabricated number attached to exactly
the decision the user came to make. So unit prices are a **project setting with
no default**, and an unset price produces `total = None` with the reason
attached — the same em-dash-plus-tooltip treatment an unavailable model score
gets, for the same reason.

This is the one place in the product where a number is withheld that is not
scientific. It is withheld on the same principle: `ARCHITECTURE.md` §4's honesty
boundary is about not fabricating numbers the user will act on, and a price is
the most directly actionable number on the screen.

Pure: no I/O, no database. The prices arrive from `Project.settings`, which is
where the RSA cutoffs already live for the same reason — a decision the product
makes visible and editable rather than compiling in (`ARCHITECTURE.md` §11).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


class CostError(ValueError):
    """A cost basis that does not describe a usable price list."""

    def __init__(self, message: str, remedy: str) -> None:
        super().__init__(message)
        self.remedy = remedy


@dataclass(frozen=True, slots=True)
class CostBasis:
    """The lab's own prices. Every field is optional and none has a default.

    An absent price is not zero. Zero is a claim that something is free; absent
    is a statement that nobody has said what it costs, and the estimate says so.
    """

    currency: str | None = None
    #: Price per base of synthesised oligonucleotide.
    oligo_per_base: float | None = None
    #: Flat charge per oligo ordered, on top of the per-base price.
    oligo_per_order: float | None = None
    #: Price per base pair of synthesised double-stranded gene fragment.
    fragment_per_bp: float | None = None
    #: Flat charge per gene fragment ordered.
    fragment_per_order: float | None = None

    def __post_init__(self) -> None:
        for name in (
            "oligo_per_base",
            "oligo_per_order",
            "fragment_per_bp",
            "fragment_per_order",
        ):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise CostError(
                    f"{name.replace('_', ' ')} cannot be negative.",
                    "Enter the price your vendor charges, or leave it unset.",
                )
        if self.priced and not self.currency:
            raise CostError(
                "A price list needs a currency.",
                "Set the currency alongside the prices, so the total is unambiguous.",
            )

    @property
    def priced(self) -> bool:
        """Whether anything at all has been priced."""
        return any(
            value is not None
            for value in (
                self.oligo_per_base,
                self.oligo_per_order,
                self.fragment_per_bp,
                self.fragment_per_order,
            )
        )

    def can_price_oligos(self) -> bool:
        return self.oligo_per_base is not None

    def can_price_fragments(self) -> bool:
        return self.fragment_per_bp is not None

    def as_manifest(self) -> dict[str, Any]:
        return {
            "currency": self.currency,
            "oligo_per_base": self.oligo_per_base,
            "oligo_per_order": self.oligo_per_order,
            "fragment_per_bp": self.fragment_per_bp,
            "fragment_per_order": self.fragment_per_order,
            "source": "stated by the project, not by this application",
        }

    @classmethod
    def from_settings(cls, settings: dict[str, Any] | None) -> CostBasis:
        stored = (settings or {}).get("cost_basis") or {}

        def number(key: str) -> float | None:
            value = stored.get(key)
            return None if value is None else float(value)

        return cls(
            currency=stored.get("currency") or None,
            oligo_per_base=number("oligo_per_base"),
            oligo_per_order=number("oligo_per_order"),
            fragment_per_bp=number("fragment_per_bp"),
            fragment_per_order=number("fragment_per_order"),
        )

    def to_settings(self) -> dict[str, Any]:
        return {
            "cost_basis": {
                "currency": self.currency,
                "oligo_per_base": self.oligo_per_base,
                "oligo_per_order": self.oligo_per_order,
                "fragment_per_bp": self.fragment_per_bp,
                "fragment_per_order": self.fragment_per_order,
            }
        }


@dataclass(frozen=True, slots=True)
class CostLine:
    """One orderable item. `amount` is None when its price is not set."""

    description: str
    quantity: int
    #: Bases for an oligo, base pairs for a fragment. What the price multiplies.
    length: int
    unit: str
    amount: float | None
    unpriced_reason: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "quantity": self.quantity,
            "length": self.length,
            "unit": self.unit,
            "amount": self.amount,
            "unpriced_reason": self.unpriced_reason,
        }


@dataclass(frozen=True, slots=True)
class CostEstimate:
    """A running total against a stated budget, or an explicit refusal to guess."""

    currency: str | None
    #: None whenever any line is unpriced. A partial total presented as the total
    #: is worse than no total: it is an underestimate that looks authoritative.
    total: float | None
    lines: tuple[CostLine, ...]
    #: Why there is no total, when there is not.
    unavailable_reason: str | None = None
    budget_amount: float | None = None
    budget_currency: str | None = None

    @property
    def over_budget(self) -> bool | None:
        """None when either side is unknown — never False by default."""
        if self.total is None or self.budget_amount is None:
            return None
        if self.budget_currency and self.currency and self.budget_currency != self.currency:
            # Two currencies are not comparable and this module does not convert:
            # an exchange rate is another number nobody stated.
            return None
        return self.total > self.budget_amount

    @property
    def remaining(self) -> float | None:
        if self.total is None or self.budget_amount is None:
            return None
        if self.budget_currency and self.currency and self.budget_currency != self.currency:
            return None
        return round(self.budget_amount - self.total, 2)

    def to_json(self) -> dict[str, Any]:
        return {
            "currency": self.currency,
            "total": self.total,
            "lines": [line.to_json() for line in self.lines],
            "unavailable_reason": self.unavailable_reason,
            "budget_amount": self.budget_amount,
            "budget_currency": self.budget_currency,
            "over_budget": self.over_budget,
            "remaining": self.remaining,
        }


UNSET_OLIGO = "No oligo price is set for this project."
UNSET_FRAGMENT = "No gene-fragment price is set for this project."


def estimate_oligos(
    basis: CostBasis,
    *,
    lengths: Sequence[int],
    description: str = "Mutagenesis primer",
) -> tuple[CostLine, ...]:
    """One line per oligo. Unpriced lines carry the reason instead of a number."""
    if not basis.can_price_oligos():
        return tuple(
            CostLine(
                description=description,
                quantity=1,
                length=length,
                unit="base",
                amount=None,
                unpriced_reason=UNSET_OLIGO,
            )
            for length in lengths
        )

    per_base = basis.oligo_per_base or 0.0
    per_order = basis.oligo_per_order or 0.0
    return tuple(
        CostLine(
            description=description,
            quantity=1,
            length=length,
            unit="base",
            amount=round(per_base * length + per_order, 2),
        )
        for length in lengths
    )


def estimate_fragments(
    basis: CostBasis,
    *,
    lengths: Sequence[int],
    description: str = "Gene fragment",
) -> tuple[CostLine, ...]:
    if not basis.can_price_fragments():
        return tuple(
            CostLine(
                description=description,
                quantity=1,
                length=length,
                unit="bp",
                amount=None,
                unpriced_reason=UNSET_FRAGMENT,
            )
            for length in lengths
        )

    per_bp = basis.fragment_per_bp or 0.0
    per_order = basis.fragment_per_order or 0.0
    return tuple(
        CostLine(
            description=description,
            quantity=1,
            length=length,
            unit="bp",
            amount=round(per_bp * length + per_order, 2),
        )
        for length in lengths
    )


def total_of(
    basis: CostBasis,
    lines: Sequence[CostLine],
    *,
    budget_amount: float | None = None,
    budget_currency: str | None = None,
    no_lines_reason: str | None = None,
) -> CostEstimate:
    """Sum the lines, or explain why there is no sum.

    Any unpriced line makes the total unavailable. Summing the priced ones would
    produce a figure lower than the real cost, presented with the authority of a
    total — the most expensive shape of wrong this screen could take.
    """
    unpriced = [line for line in lines if line.amount is None]
    if not lines:
        # "Nothing to add up" and "the total is zero" are different statements,
        # and the caller knows which one applies here — a set with no members is
        # not the same as a set whose items are not orderable yet.
        return CostEstimate(
            currency=basis.currency,
            total=None,
            lines=(),
            unavailable_reason=no_lines_reason or "There is nothing to cost yet.",
            budget_amount=budget_amount,
            budget_currency=budget_currency,
        )
    if unpriced:
        reasons = sorted({line.unpriced_reason or "Unpriced." for line in unpriced})
        return CostEstimate(
            currency=basis.currency,
            total=None,
            lines=tuple(lines),
            unavailable_reason=" ".join(reasons)
            + " Set the prices your vendor charges to see a total.",
            budget_amount=budget_amount,
            budget_currency=budget_currency,
        )

    return CostEstimate(
        currency=basis.currency,
        total=round(sum(line.amount or 0.0 for line in lines), 2),
        lines=tuple(lines),
        budget_amount=budget_amount,
        budget_currency=budget_currency,
    )
