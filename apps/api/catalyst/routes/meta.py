"""Service metadata, including the demo-mode flag the entire interface keys off."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from catalyst import queue
from catalyst.config import get_settings
from catalyst.providers import describe
from catalyst.services import providers as provider_service

router = APIRouter(tags=["meta"])


class QueueMeta(BaseModel):
    connected: bool
    workers: int
    queued: int
    detail: str | None = None


class Meta(BaseModel):
    demo_mode: bool = Field(
        description="True when a provider that fabricates numbers is active. The web "
        "app renders a persistent 'Demo data — not model output' bar whenever this is "
        "true and badges every number the mock produced. Derived from the active "
        "predictors themselves, not from a string in the environment, so it cannot "
        "drift away from what is actually running."
    )
    providers: list[str]
    #: Each active predictor as data: identity, citation, what it requires, which
    #: objectives it covers, and the sign convention of every metric it fills. The
    #: interface varies by model from this and never by naming one.
    predictors: list[dict[str, Any]]
    #: Objectives at least one active predictor supports. The goal composer greys
    #: out the rest rather than running something no provider can answer.
    supported_objectives: list[str]
    #: Configured ids that matched no predictor. Reported rather than skipped: a
    #: typo would otherwise silently remove a column from every run.
    unknown_providers: list[str]
    #: Per objective: whether anything runnable covers it, and if not, the reason
    #: — so the composer greys it out *with an explanation* rather than silently.
    objective_support: dict[str, dict[str, Any]]
    queue: QueueMeta


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/meta", response_model=Meta)
def meta() -> Meta:
    settings = get_settings()
    status = queue.status()
    return Meta(
        demo_mode=provider_service.demo_mode(settings),
        providers=list(settings.providers),
        predictors=[describe(predictor) for predictor in provider_service.active(settings)],
        supported_objectives=sorted(
            objective.value for objective in provider_service.supported_objectives(settings)
        ),
        unknown_providers=provider_service.unknown_ids(settings),
        objective_support=provider_service.objective_support(settings),
        queue=QueueMeta(
            connected=status.connected,
            workers=status.workers,
            queued=status.queued,
            detail=status.detail,
        ),
    )
