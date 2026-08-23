"""The job queue client.

Infrastructure, sitting beside ``db.py`` rather than inside ``workers/``: the API
enqueues, the worker consumes, and both need the same connection. Putting it in
the worker package would make a route import an entry point, which is the one
direction ARCHITECTURE.md §3 does not allow.

The job is referenced by dotted path rather than by importing the function, so
the API process never imports the worker module and cannot accidentally acquire
the ability to execute a run in a request handler.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from redis import Redis
from redis.exceptions import RedisError
from rq import Queue, Worker

from catalyst.config import get_settings

QUEUE_NAME = "catalyst"
JOB_PATH = "catalyst.workers.jobs.execute_run"

#: Generous, because a run scores the whole single-point space of a protein with
#: a real model. ESM-2 650M masked-marginal is one forward pass per position —
#: measured at 3.4s on CPU here, so ~31 minutes for a 550-residue target. The
#: cost is paid once per (target, checkpoint, candidate set) and then served from
#: the content-addressed cache; a timeout that killed the first pass would make
#: the cache impossible to fill. See ARCHITECTURE.md §14.1.
#:
#: It exists so a wedged job is eventually reaped, not as a performance target.
JOB_TIMEOUT_SECONDS = 3600


class QueueUnavailableError(RuntimeError):
    """Redis could not be reached. Carries the fix, like every other failure."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.remedy = "Start Redis with `docker compose up -d redis`, then retry."


def get_queue() -> Queue:
    settings = get_settings()
    return Queue(
        QUEUE_NAME,
        connection=Redis.from_url(settings.redis_url),
        default_timeout=JOB_TIMEOUT_SECONDS,
    )


def enqueue_run(run_id: uuid.UUID) -> str:
    """Hand a run to a worker. Returns the job id.

    Raises rather than falling back to running the pipeline inline: a stack whose
    worker is not running should say so, not quietly execute a long job inside a
    request and appear healthy.
    """
    try:
        # Derived from the run id, so re-enqueueing the same run cannot produce
        # two jobs. Hyphen-separated: RQ rejects a colon in a job id.
        job = get_queue().enqueue(JOB_PATH, str(run_id), job_id=f"run-{run_id}")
    except RedisError as error:
        raise QueueUnavailableError(f"The job queue is unreachable: {error}") from error
    return str(job.id)


@dataclass(frozen=True, slots=True)
class QueueStatus:
    """What the interface needs in order to explain a run that is not moving."""

    connected: bool
    workers: int
    queued: int
    detail: str | None = None


def status() -> QueueStatus:
    """Queue health, for ``/meta``.

    A run sitting at 'queued' forever has exactly two causes — Redis is down, or
    no worker is consuming — and both are invisible from the run itself. Reading
    them here lets the run view say which, instead of showing a spinner that
    means nothing.
    """
    try:
        queue = get_queue()
        return QueueStatus(
            connected=True,
            workers=Worker.count(queue=queue),
            queued=queue.count,
        )
    except RedisError as error:
        return QueueStatus(connected=False, workers=0, queued=0, detail=str(error))
