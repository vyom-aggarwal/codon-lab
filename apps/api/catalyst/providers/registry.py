"""Which predictors exist, and which of them this deployment has switched on.

``CATALYST_PROVIDERS`` names them. An id that resolves to nothing is reported
rather than skipped: a typo that silently disables a predictor would produce a
run that looks complete and is missing a column, which is worse than a run that
refuses to start.
"""

from __future__ import annotations

from catalyst.providers.base import Predictor
from catalyst.providers.esm import ESM2_650M
from catalyst.providers.mock import MOCK_FITNESS, MOCK_STABILITY
from catalyst.providers.thermompnn import THERMOMPNN

#: Every predictor this build can run, by id.
REGISTRY: dict[str, Predictor] = {
    predictor.id: predictor
    for predictor in (
        MOCK_STABILITY,
        MOCK_FITNESS,
        ESM2_650M,
        THERMOMPNN,
    )
}

#: Shorthands accepted in ``CATALYST_PROVIDERS``. ``mock`` turns on the whole
#: synthetic set, which is what a machine without GPUs wants and what the
#: shipped docker-compose configures.
GROUPS: dict[str, tuple[str, ...]] = {
    "mock": (MOCK_STABILITY.id, MOCK_FITNESS.id),
    #: The real set. Each member declares itself unavailable, with a reason, if
    #: its runtime or its weights are missing — nothing here falls back to mock.
    "real": (ESM2_650M.id, THERMOMPNN.id),
}


def resolve(ids: tuple[str, ...]) -> tuple[list[Predictor], list[str]]:
    """Expand configured ids into predictors, plus the ids that matched nothing.

    Order follows the configuration, and duplicates collapse, so the stage list
    in the run view is stable and never lists the same predictor twice.
    """
    predictors: list[Predictor] = []
    unknown: list[str] = []
    seen: set[str] = set()

    for identifier in ids:
        expanded = GROUPS.get(identifier, (identifier,))
        matched = False
        for member in expanded:
            predictor = REGISTRY.get(member)
            if predictor is None:
                continue
            matched = True
            if predictor.id not in seen:
                seen.add(predictor.id)
                predictors.append(predictor)
        if not matched:
            unknown.append(identifier)

    return predictors, unknown


def get(identifier: str) -> Predictor | None:
    return REGISTRY.get(identifier)
