"""How much of the shared worker one caller may hold at once.

**What this protects.** A design run scores every single substitution in the
target and takes up to `JOB_TIMEOUT_SECONDS` (3600) to do it. One worker
executes one job at a time. So `POST /goals/{id}/runs` is an endpoint where a
single unauthenticated HTTP request buys an hour of somebody else's CPU, and
before this module existed there was nothing between the open internet and that
queue.

**Why a ceiling on work in flight rather than a rate limit.** A rate — "N runs
per hour" — would be a number invented to sound reasonable, and it would measure
the wrong thing. The scarce resource is not request frequency; it is the worker,
and what consumes it is runs that have not finished. Ten enqueues in a second
are harmless if nine are cache hits on an identical content address, which this
product supports and treats as the same run. One enqueue an hour is a permanent
backlog if each takes fifty-five minutes.

So the quantity rationed here is the one actually being rationed: **runs a caller
has pending or running at this moment**. It needs no window, no clock and no
invented rate. Finishing a run frees capacity immediately, which is the correct
behaviour and also the intuitive one.

**The default of 3, and its basis.** The seeded 212-residue lipase used 93% of
the hour-long timeout. With one worker, three runs in flight is already about
three hours of queue for whoever is behind them. It is set as a configurable
ceiling (`CODONLAB_MAX_RUNS_IN_FLIGHT`) rather than a constant because the right
number is a function of how many workers are deployed, which is an operator's
decision and not a scientific one.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func
from sqlmodel import Session, col, select

from codonlab.config import get_settings
from codonlab.models import Project, Run, RunStatus, User

#: A run in one of these states is still holding, or waiting to hold, the worker.
#: Terminal states are not counted: they have given the capacity back.
IN_FLIGHT = (RunStatus.PENDING, RunStatus.RUNNING)


class QuotaError(RuntimeError):
    """The caller already holds as much of the worker as they may."""

    def __init__(self, message: str, remedy: str) -> None:
        super().__init__(message)
        self.remedy = remedy


def runs_in_flight(session: Session, *, owner_id: uuid.UUID) -> int:
    """How many of this owner's runs are pending or running right now."""
    statement = (
        select(func.count(col(Run.id)))
        .join(Project, col(Run.project_id) == col(Project.id))
        .where(col(Project.owner_id) == owner_id)
        .where(col(Run.status).in_(IN_FLIGHT))
    )
    return session.exec(statement).one()


def assert_capacity(session: Session, *, user: User) -> None:
    """Raise `QuotaError` if this caller may not start another run.

    Called on every path that dispatches work to the queue. There are two of
    them — starting a run and re-running one — and `tests/test_quota.py` asserts
    that every route reaching `queue.enqueue_run` passes through here, so a third
    cannot be added without the test noticing.

    Not enforced when running unauthenticated: that is a single-user local
    instance where the only person who can exhaust the worker is the person who
    owns it, and a developer waiting on their own fourth run is being obstructed
    for nothing.
    """
    settings = get_settings()
    if not settings.auth_required:
        return

    ceiling = settings.max_runs_in_flight
    current = runs_in_flight(session, owner_id=user.id)
    if current < ceiling:
        return

    raise QuotaError(
        f"You already have {current} design run(s) queued or running, which is the "
        f"limit of {ceiling} on this instance.",
        "Wait for one to finish, or cancel one from its run view. A run that has "
        "finished — succeeded, failed or cancelled — no longer counts against this.",
    )
