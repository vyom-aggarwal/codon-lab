"""The only place in this codebase permitted to invent a scientific number.

Specification §6: ship a ``MockProvider`` so the full interface is usable without
GPUs, producing deterministic, plausibly-shaped synthetic output — and mark it,
everywhere, as synthetic. Every predictor here sets ``is_mock``; that single
field is what raises the persistent amber bar, badges every individual number,
watermarks exports, and refuses to generate primers. Nothing downstream
recognises these providers by name.

**Deterministic** means a function of content, not of a seeded generator: the
same target and the same variant produce the same number on any machine, in any
process, in any order. That is what makes the content-addressed cache in
ARCHITECTURE.md §6 correct rather than merely plausible.

**Plausibly shaped** means the distribution looks like the thing it stands in
for — most substitutions destabilize, most are evolutionarily unfavourable — and
that two predictors mostly agree and sometimes do not, because a demo where the
disagreement column is always empty would fail to show the feature that matters
most. The shape is fiction with a badge on it, not a prediction.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

from codonlab.domain.goal import Objective
from codonlab.domain.hashing import content_hash
from codonlab.domain.variants import VariantInput
from codonlab.models.enums import Modality
from codonlab.providers.base import (
    Capabilities,
    MetricSpec,
    ScoreValue,
    TargetContext,
)

#: How much of a variant's synthetic value is shared between predictors. Two
#: mocks drawing independently would disagree about everything, which would make
#: the disagreement column noise; two mocks drawing identically would never
#: disagree, which would hide the column entirely. Neither would show a user
#: what predictor disagreement actually looks like.
_SHARED_WEIGHT = 0.7

#: The shared draw is a latent "how good is this substitution", 1 best. Each
#: predictor reads it in the direction its own metric runs — a ΔΔG reported
#: destabilizing-positive gets `1 - latent`, a log-likelihood ratio gets the
#: latent itself. Without this the two mocks would be anti-correlated by
#: construction: every variant would carry maximal disagreement, and a demo where
#: the predictors always disagree misleads exactly as badly as one where they
#: never do.


def _unit_pair(*parts: str) -> tuple[float, float]:
    """Two reproducible values in [0, 1) derived from the given content."""
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    return (
        int.from_bytes(digest[0:8], "big") / 2**64,
        int.from_bytes(digest[8:16], "big") / 2**64,
    )


def _blend(shared: float, own: float) -> float:
    return _SHARED_WEIGHT * shared + (1.0 - _SHARED_WEIGHT) * own


@dataclass(frozen=True, slots=True)
class MockPredictor:
    """A predictor that fabricates, and says so in every field it fills."""

    id: str
    name: str
    version: str
    weights_hash: str
    modality: Modality
    requires: Capabilities
    citation: str
    objectives: frozenset[Objective]
    metrics: tuple[MetricSpec, ...]
    #: Affine transform applied to the blended latent, plus the exponent that
    #: gives the distribution its skew: ``low + span * driver ** skew``, where
    #: ``driver`` is the latent read in this metric's own direction. A skew below
    #: 1 pushes mass toward the top of the range, above 1 toward the bottom.
    low: float
    span: float
    skew: float
    #: Half-width parameters for the reported interval, or None for a metric
    #: that legitimately has no uncertainty to report.
    sd_low: float | None = None
    sd_span: float | None = None

    is_mock: bool = True

    @property
    def metric(self) -> MetricSpec:
        return self.metrics[0]

    def available(self) -> str | None:
        """Always. Arithmetic has no weights to download and nothing to install —
        which is the entire reason this provider exists."""
        return None

    def score(
        self, variants: Sequence[VariantInput], ctx: TargetContext
    ) -> list[ScoreValue]:
        """Fabricate one value per variant, reproducibly.

        The structure's content hash is part of the derivation for a predictor
        that requires one, so re-running against a re-fetched structure that has
        changed produces different numbers rather than stale ones.
        """
        structure = ctx.structure.content_hash if ctx.structure else ""
        results: list[ScoreValue] = []

        for variant in variants:
            # NOT a brand string, and deliberately not renamed with the product.
            # It is an opaque salt: every synthetic number this provider has ever
            # produced derives from it, so changing the token changes the numbers
            # and silently breaks reproducibility against every score already
            # stored. Leave it exactly as it is.
            shared_a, shared_b = _unit_pair("catalyst.mock.shared", ctx.sequence, variant.code)
            own_a, own_b = _unit_pair(self.id, self.version, ctx.sequence, structure, variant.code)

            latent = _blend(shared_a, own_a)
            driver = latent if self.metric.higher_is_better else 1.0 - latent
            value = round(self.low + self.span * driver**self.skew, 2)

            uncertainty: float | None = None
            ci_low: float | None = None
            ci_high: float | None = None
            if self.sd_low is not None and self.sd_span is not None:
                uncertainty = round(self.sd_low + self.sd_span * _blend(shared_b, own_b), 2)
                # 95% interval, stated as such wherever it is rendered.
                ci_low = round(value - 1.96 * uncertainty, 2)
                ci_high = round(value + 1.96 * uncertainty, 2)

            results.append(
                ScoreValue(
                    variant_code=variant.code,
                    metric=self.metric.id,
                    value=value,
                    uncertainty=uncertainty,
                    ci_low=ci_low,
                    ci_high=ci_high,
                    detail={"synthetic": True, "generator": f"{self.id}@{self.version}"},
                )
            )
        return results


def _generator_hash(model_id: str, version: str, parameters: dict[str, object]) -> str:
    """There are no weights, so the hash addresses the generator instead.

    A fabricated hex string here would be indistinguishable from a real weights
    hash in the provenance trail, which is exactly the confusion this product
    exists to prevent. This value is reproducible and identifies precisely what
    produced the numbers: the generator and its parameters.
    """
    return content_hash(
        {
            "generator": "codonlab.providers.mock",
            "id": model_id,
            "version": version,
            "parameters": parameters,
            "note": "synthetic generator, no trained weights exist",
        }
    )


_CITATION = (
    "No citation. Synthetic output from codonlab.providers.mock, provided so the "
    "interface is usable without GPUs. Not a model and not a prediction."
)

_VERSION = "0.1.0"

#: ΔΔG. Sign convention fixed by specification §7 and never changed: destabilizing
#: positive, kcal/mol, always with an interval — a bare point estimate is not
#: acceptable output for a stability prediction.
DDG = MetricSpec(
    id="ddg_kcal_per_mol",
    label="Predicted ΔΔG",
    unit="kcal/mol",
    sign_convention="destabilizing positive",
    higher_is_better=False,
    reports_interval=True,
)

#: A masked-marginal log-odds ratio is a point estimate by construction. It is
#: reported without an interval rather than with an invented one.
LLR = MetricSpec(
    id="fitness_llr",
    label="Fitness log-likelihood ratio",
    unit=None,
    sign_convention="mutant minus wild type; higher is more favourable",
    higher_is_better=True,
    reports_interval=False,
)

_STABILITY_PARAMETERS: dict[str, object] = {
    "low": "-1.2",
    "span": "4.4",
    "skew": "0.65",
    "sd_low": "0.25",
    "sd_span": "0.55",
    "shared_weight": str(_SHARED_WEIGHT),
}

_FITNESS_PARAMETERS: dict[str, object] = {
    "low": "-9.0",
    "span": "11.0",
    "skew": "1.4",
    "shared_weight": str(_SHARED_WEIGHT),
}

#: Requires a structure, as a real ThermoMPNN-shaped adapter would — so the
#: pipeline genuinely skips it, with a stated reason, on a target that has no
#: structure attached. ``needs_gpu`` is false because this one truthfully does
#: not; the capability describes this provider, not the thing it stands in for.
MOCK_STABILITY = MockPredictor(
    id="mock_stability",
    name="Mock stability predictor",
    version=_VERSION,
    weights_hash=_generator_hash("mock_stability", _VERSION, _STABILITY_PARAMETERS),
    modality=Modality.STABILITY,
    requires=Capabilities(needs_structure=True, needs_msa=False, needs_gpu=False),
    citation=_CITATION,
    # Folding free energy speaks to thermal stability and to nothing else here.
    # Narrow on purpose: a mock that claimed every objective would leave the
    # "grey out what no provider supports" path permanently untested.
    objectives=frozenset({Objective.THERMOSTABILITY}),
    metrics=(DDG,),
    low=-1.2,
    span=4.4,
    skew=0.65,
    sd_low=0.25,
    sd_span=0.55,
)

#: Sequence-only, as masked-marginal scoring genuinely is: no structure, no MSA.
#: The breadth of `objectives` below is a property of this mock, chosen so the
#: interface is exercisable end to end. It is not a claim about what any real
#: fitness model can do — Phase 6 must state each real predictor's coverage
#: explicitly rather than inheriting this list.
MOCK_FITNESS = MockPredictor(
    id="mock_fitness",
    name="Mock fitness predictor",
    version=_VERSION,
    weights_hash=_generator_hash("mock_fitness", _VERSION, _FITNESS_PARAMETERS),
    modality=Modality.FITNESS,
    requires=Capabilities(needs_structure=False, needs_msa=False, needs_gpu=False),
    citation=_CITATION,
    objectives=frozenset(
        {
            Objective.THERMOSTABILITY,
            Objective.ACTIVITY,
            Objective.EXPRESSION,
            Objective.SOLUBILITY,
            Objective.BINDING_AFFINITY,
            Objective.SPECIFICITY,
            Objective.SOLVENT_TOLERANCE,
        }
    ),
    metrics=(LLR,),
    low=-9.0,
    span=11.0,
    skew=1.4,
)
