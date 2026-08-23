"""The one seam between what the product asks for and what a model can do.

Specification §6 and ARCHITECTURE.md §4. Everything a screen needs to vary by
model arrives through the types in this file as *data* — never as a branch in a
component and never as a model name in a conditional.

Three deviations from the protocol as sketched in the specification, each made
for the same reason and each recorded in ARCHITECTURE.md §4:

* ``score`` takes ``VariantInput``, not the ``Variant`` table row. A provider
  that took an ORM row would need a database session, and providers sit below
  services precisely so that they do not.
* ``score`` returns ``ScoreValue``, not ``Score``. A ``Score`` cannot exist
  without a run and a model version, and a provider knows about neither. This is
  not a workaround: it is the integrity rule from ARCHITECTURE.md §5 showing up
  in the type system. A provider is structurally incapable of writing an
  untraceable number.
* ``objectives`` and ``metrics`` are added to the protocol, so the interface can
  grey out an objective no provider supports and label a column with its unit
  and sign convention without knowing which model filled it.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from catalyst.domain.goal import Objective
from catalyst.domain.variants import VariantInput
from catalyst.models.enums import Modality


class PredictorUnavailableError(RuntimeError):
    """A predictor cannot run here, with the reason it cannot.

    The reason is carried all the way to the cell, which reads ``—`` with this
    text on hover. It is never replaced by an imputed value or a placeholder.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class Capabilities:
    """What a predictor needs in order to run at all.

    Stated by the provider about itself. The pipeline checks these against what
    the target actually has and skips the predictor with a reason when they are
    not met — rather than running it on missing inputs and returning something
    worthless.
    """

    needs_structure: bool = False
    needs_msa: bool = False
    max_length: int | None = None
    needs_gpu: bool = False

    def unmet(self, ctx: TargetContext) -> str | None:
        """Why this predictor cannot run against ``ctx``, or None if it can."""
        if self.needs_structure and ctx.structure is None:
            return (
                "This predictor requires a structure and none is attached to the "
                "target. Attach a PDB entry or an AlphaFold model and re-run."
            )
        if self.needs_msa and ctx.msa is None:
            return (
                "This predictor requires a multiple sequence alignment and no MSA "
                "provider is configured in this build."
            )
        if self.max_length is not None and len(ctx.sequence) > self.max_length:
            return (
                f"This predictor accepts at most {self.max_length} residues and the "
                f"target is {len(ctx.sequence)}."
            )
        return None


@dataclass(frozen=True, slots=True)
class MetricSpec:
    """A column, described by whoever fills it.

    The sign convention travels with the metric rather than being written into a
    component, because specification §7 requires it stated in the column header
    and never changed — and a convention that lives in the UI is a convention a
    second UI can contradict.
    """

    id: str
    label: str
    unit: str | None
    sign_convention: str
    higher_is_better: bool
    #: False for metrics that are legitimately point estimates. A stability
    #: prediction without an interval is not acceptable output; a masked-marginal
    #: log-likelihood ratio genuinely has none, and inventing one would be worse.
    reports_interval: bool = True


@dataclass(frozen=True, slots=True)
class StructureRef:
    """The structure a run is using, as its content address rather than its file.

    Structures are re-fetched by identity when they are needed; what a prediction
    depends on is the exact bytes, and the hash is what makes that dependency
    part of the cache key.
    """

    identifier: str | None
    source: str
    content_hash: str
    chain: str | None = None
    is_predicted: bool = False


@dataclass(frozen=True, slots=True)
class TargetContext:
    """Everything a predictor is allowed to know about the target.

    No session, no request, no settings. What is not in here, a predictor cannot
    reach — which is what keeps a provider testable without a database and keeps
    the model layer from growing a dependency on the rest of the application.
    """

    target_id: uuid.UUID
    sequence: str
    scheme_label: str
    objective: Objective | None = None
    structure: StructureRef | None = None
    #: No MSAProvider exists yet; this stays None and the capability check above
    #: turns it into a stated reason rather than a silent absence.
    msa: str | None = None
    #: The coordinates themselves, for a predictor that reads structure rather
    #: than just depending on it. Deliberately absent from `cache_key`: the
    #: structure's content hash already identifies these bytes, and hashing the
    #: whole file again would make every cache key megabytes long.
    structure_text: str | None = None

    def cache_key(self) -> dict[str, object]:
        """The parts of the context a prediction actually depends on."""
        return {
            "sequence": self.sequence,
            "structure": None if self.structure is None else self.structure.content_hash,
            "msa": self.msa,
        }


@dataclass(frozen=True, slots=True)
class ScoreValue:
    """One number, before it acquires its provenance.

    Carries no run and no model version: a provider does not have them, and the
    service that does is the only thing that can turn this into a ``Score``.
    """

    variant_code: str
    metric: str
    value: float
    uncertainty: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    #: Anything the provider wants on the record, e.g. which inputs it used.
    detail: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class Predictor(Protocol):
    """One interface, many providers. The UI never imports an implementation.

    Every attribute is declared read-only. A predictor's identity — which model,
    which version, which weights — is the thing a provenance trail is built on,
    and nothing in the application has any business reassigning it after the fact.
    Implementations are consequently free to be frozen dataclasses.
    """

    @property
    def id(self) -> str: ...

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def weights_hash(self) -> str: ...

    @property
    def modality(self) -> Modality: ...

    @property
    def requires(self) -> Capabilities: ...

    @property
    def citation(self) -> str: ...

    @property
    def is_mock(self) -> bool:
        """True when this provider fabricates numbers.

        The demo bar, the per-number badge, export watermarking and the refusal
        to emit primers all key off this one field, so that nothing in the
        product has to recognise a model by name in order to know whether to
        trust it.
        """
        ...

    @property
    def objectives(self) -> frozenset[Objective]:
        """The objectives this predictor can speak to.

        The goal composer greys out anything no available provider covers rather
        than running it and returning something worthless.
        """
        ...

    @property
    def metrics(self) -> tuple[MetricSpec, ...]: ...

    def available(self) -> str | None:
        """Why this predictor cannot run *at all*, or None if it can.

        Distinct from `Capabilities.unmet`, which asks whether a predictor suits
        a particular target. This asks whether it exists here: are its runtime
        dependencies installed, are its weights on disk, can they be read.

        A real predictor that cannot load must say so and produce nothing. It
        must never fall back to another provider's output, and it must never
        report a placeholder `weights_hash` — a made-up hash turns the entire
        traceability claim into a lie, which is worse than an absent column.
        """
        ...

    def score(
        self, variants: Sequence[VariantInput], ctx: TargetContext
    ) -> list[ScoreValue]: ...


def describe(predictor: Predictor) -> dict[str, object]:
    """The provider as data, for ``/meta`` and for the run view's stage list."""
    unavailable = predictor.available()
    return {
        "id": predictor.id,
        "name": predictor.name,
        "available": unavailable is None,
        "unavailable_reason": unavailable,
        "version": predictor.version,
        "weights_hash": predictor.weights_hash,
        "modality": predictor.modality.value,
        "citation": predictor.citation,
        "is_mock": predictor.is_mock,
        "objectives": sorted(objective.value for objective in predictor.objectives),
        "requires": {
            "structure": predictor.requires.needs_structure,
            "msa": predictor.requires.needs_msa,
            "max_length": predictor.requires.max_length,
            "gpu": predictor.requires.needs_gpu,
        },
        "metrics": [
            {
                "id": metric.id,
                "label": metric.label,
                "unit": metric.unit,
                "sign_convention": metric.sign_convention,
                "higher_is_better": metric.higher_is_better,
                "reports_interval": metric.reports_interval,
            }
            for metric in predictor.metrics
        ],
    }
