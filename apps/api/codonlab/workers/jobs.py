"""Jobs, as thin as they can be.

Everything a job does lives in `services/`. This module exists to open a session,
name the unit of work, and let failures out — RQ records the traceback on the job
and the service has already written the failure onto the run itself, so a job
that dies leaves two independent records rather than none.
"""

from __future__ import annotations

import uuid

from sqlmodel import Session

from codonlab.db import get_engine
from codonlab.services import runs as run_service


def execute_run(run_id: str) -> str:
    """Execute a design run. Idempotent — replaying a claimed run does nothing.

    Takes a string because RQ serialises arguments and a plain string survives
    every serialiser identically.
    """
    with Session(get_engine()) as session:
        run = run_service.execute(session, uuid.UUID(run_id))
        return run.status.value
