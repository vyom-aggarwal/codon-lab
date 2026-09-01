"""Predictor implementations — the only layer that may import a model client.

ARCHITECTURE.md §2: the web application knows about scores and model versions; it
does not know that ESM exists. Everything that varies by model reaches a screen
as data from ``base.describe`` and from ``ModelVersion`` rows, never as a branch.

The test for whether that still holds: adding a fourth stability predictor must
touch zero files under ``apps/web/components``.
"""

from codonlab.providers.base import (
    Capabilities,
    MetricSpec,
    Predictor,
    PredictorUnavailableError,
    ScoreValue,
    StructureRef,
    TargetContext,
    describe,
)
from codonlab.providers.registry import GROUPS, REGISTRY, get, resolve

__all__ = [
    "GROUPS",
    "REGISTRY",
    "Capabilities",
    "MetricSpec",
    "Predictor",
    "PredictorUnavailableError",
    "ScoreValue",
    "StructureRef",
    "TargetContext",
    "describe",
    "get",
    "resolve",
]
