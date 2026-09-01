"""Which predictors are active, and what that means for the whole interface.

The demo flag is derived here, from the predictors themselves, rather than from
the string ``mock`` appearing in an environment variable. Those two answers agree
today; they would drift the first time a provider was renamed or a real provider
shipped alongside a synthetic one, and the drift would be invisible — a screen
with no amber bar over numbers that were fabricated. Deriving it from
``Predictor.is_mock`` makes the flag a fact about what is running.

Registering a ``ModelVersion`` also lives here, because a score's traceability
starts before the score does: the row that a ``Score`` points at must exist, be
unique on (model, version, weights hash), and record whether it fabricates.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, col, select

from codonlab.config import Settings, get_settings
from codonlab.domain.goal import Objective
from codonlab.models import ModelVersion
from codonlab.providers import Predictor, resolve
from codonlab.services.targets import ServiceError


def active(settings: Settings | None = None) -> list[Predictor]:
    """The predictors this deployment has switched on."""
    predictors, _ = resolve((settings or get_settings()).providers)
    return predictors


def unknown_ids(settings: Settings | None = None) -> list[str]:
    """Configured ids that match no predictor. Surfaced, never swallowed."""
    _, unknown = resolve((settings or get_settings()).providers)
    return unknown


def require_active(settings: Settings | None = None) -> list[Predictor]:
    """The active predictors, refusing to proceed if any id matched nothing."""
    settings = settings or get_settings()
    predictors, unknown = resolve(settings.providers)

    if unknown:
        raise ServiceError(
            f"CODONLAB_PROVIDERS names {len(unknown)} unknown provider(s): "
            f"{', '.join(unknown)}.",
            "Correct the value, or remove it — a run started with a mistyped "
            "provider would quietly be missing a predictor.",
        )
    if not predictors:
        raise ServiceError(
            "No predictors are configured.",
            "Set CODONLAB_PROVIDERS, for example to `mock`, and restart the API.",
        )
    return predictors


def demo_mode(settings: Settings | None = None) -> bool:
    """True when any active predictor fabricates its numbers.

    Drives the persistent amber bar on every screen, the badge on every
    individual number, export watermarking, and the refusal to emit primers.
    """
    return any(predictor.is_mock for predictor in active(settings))


def runnable(settings: Settings | None = None) -> list[Predictor]:
    """Active predictors that can actually run here.

    A configured predictor whose runtime or weights are missing is *active* — it
    is what the deployment asked for — but it is not runnable, and a run must not
    plan a stage for it. It never falls back to another provider; the objective it
    covered simply greys out with its reason.
    """
    return [predictor for predictor in active(settings) if predictor.available() is None]


def supported_objectives(settings: Settings | None = None) -> set[Objective]:
    """Objectives at least one active predictor can speak to.

    The goal composer greys out everything else rather than starting a run that
    would return something worthless. ``Objective.OTHER`` is never in this set:
    it is the bucket for an objective the parser could not name, and no provider
    can support what has not been named.
    """
    covered: set[Objective] = set()
    for predictor in runnable(settings):
        covered |= predictor.objectives
    return covered


def predictors_for(
    objective: Objective | None, settings: Settings | None = None
) -> list[Predictor]:
    """The active predictors that declare support for this objective."""
    if objective is None:
        return []
    return [predictor for predictor in runnable(settings) if objective in predictor.objectives]


def ensure_model_version(session: Session, predictor: Predictor) -> ModelVersion:
    """Find or create the row every score produced by this predictor points at.

    Keyed on (model id, version, weights hash) — the same triple the unique
    constraint uses — so a predictor whose weights change becomes a different
    ``ModelVersion`` rather than silently rewriting the identity of numbers that
    were produced by the old ones.
    """
    existing = session.exec(
        select(ModelVersion).where(
            col(ModelVersion.model_id) == predictor.id,
            col(ModelVersion.version) == predictor.version,
            col(ModelVersion.weights_hash) == predictor.weights_hash,
        )
    ).first()
    if existing is not None:
        return existing

    created = ModelVersion(
        model_id=predictor.id,
        name=predictor.name,
        version=predictor.version,
        weights_hash=predictor.weights_hash,
        modality=predictor.modality,
        citation=predictor.citation,
        is_mock=predictor.is_mock,
    )
    session.add(created)
    session.flush()
    return created


def objective_support(settings: Settings | None = None) -> dict[str, dict[str, Any]]:
    """Per objective: whether anything covers it, and if not, why not.

    `BRIEF.md` §6 requires the interface to grey out an objective no available
    provider supports. Greying it out silently would leave a scientist guessing
    whether the tool is broken or the question is out of scope, so the reason is
    stated here — in the API, once — rather than composed by a screen that would
    have to know which models exist.
    """
    predictors = active(settings)
    support: dict[str, dict[str, Any]] = {}

    for objective in Objective:
        covering = [p for p in predictors if objective in p.objectives]
        available = [p for p in covering if p.available() is None]

        if available:
            reason = None
        elif covering:
            # Something covers it in principle but cannot run here.
            blocked = "; ".join(f"{p.name}: {p.available()}" for p in covering)
            reason = (
                f"The predictors that cover {objective.value.replace('_', ' ')} cannot "
                f"run here. {blocked}"
            )
        elif objective is Objective.OTHER:
            reason = (
                "This is the bucket for an objective the parser could not name. No "
                "predictor can support what has not been named — edit the objective "
                "chip to something specific."
            )
        else:
            covered = sorted(
                {o.value.replace("_", " ") for p in predictors for o in p.objectives}
            )
            reason = (
                f"No configured predictor is offered for "
                f"{objective.value.replace('_', ' ')}. Between them the configured "
                f"predictors cover: {', '.join(covered) or 'nothing'}."
            )

        support[objective.value] = {
            "supported": bool(available),
            "predictors": [p.id for p in available],
            "reason": reason,
        }
    return support
