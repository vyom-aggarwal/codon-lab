"""Whose data is this, and may the caller see it.

**Why this is a dependency and not a check inside each service.**
`ARCHITECTURE.md` §3 keeps guarantees in the service layer, and `HANDOFF.md`
records the reason: the job queue is a second caller, so a rule enforced in a
route can be routed around. That reasoning is what puts `require_confirmed` in
`services/goals`.

Ownership is the case where it does not apply, and the difference is worth being
precise about. The worker never *authorises* anything — it executes a run that
was already authorised when somebody enqueued it, and it has no caller to
attribute the work to. Ownership is therefore a property of an HTTP request
rather than an invariant of the domain, and the request boundary is where it
belongs.

**Why a router dependency rather than a parameter on 51 handlers.**
The failure this design rules out is the one that actually happens: someone adds
a route six months from now and does not add the check. Attached to the router,
this runs for every path in it — the ones that exist today and the ones that do
not yet. A handler cannot forget to opt in, because it never opts in.

The cost is that the guard resolves entities from `request.path_params` rather
than from typed arguments, so the mapping below is the thing to keep correct. A
path parameter naming an owned entity that is missing from `RESOLVERS` is not
refused — it is simply unchecked. `tests/test_ownership.py` asserts that every
path parameter the application actually serves is either resolvable or on the
explicit public list, so adding an unguarded one fails the suite.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session

from codonlab.auth import CurrentUser
from codonlab.db import get_session
from codonlab.models import (
    Constraint,
    DesignSet,
    Experiment,
    Goal,
    Measurement,
    Project,
    Run,
    Target,
    User,
    Variant,
)

#: Path parameters that do not name an owned resource. Listed explicitly so the
#: test that walks the application's routes can tell "not owned" from
#: "forgotten".
PUBLIC_PARAMS = frozenset(
    {
        # A mutation code such as "p.Ser77Ala". Not an id, and meaningless
        # without the target_id that appears beside it in the same path.
        "code",
    }
)


def _not_found() -> HTTPException:
    """404, never 403.

    A 403 on a resource that exists confirms it exists. Distinguishing "no such
    project" from "somebody else's project" hands an enumerator the ability to
    map the database one id at a time. Both answer the same way.
    """
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "message": "Not found.",
            "remedy": "Open it from the projects table.",
        },
    )


# --------------------------------------------------------------------------- #
# Resolving an id to the project that owns it
# --------------------------------------------------------------------------- #
#
# Most tables carry `project_id` directly, so most of these are one hop. The
# three that are not — a constraint and a variant hang off a target, a
# measurement hangs off an experiment — are two.


Resolver = Callable[[Session, uuid.UUID], uuid.UUID | None]


def _via(model: type, attribute: str = "project_id") -> Resolver:
    def resolve(session: Session, entity_id: uuid.UUID) -> uuid.UUID | None:
        entity = session.get(model, entity_id)
        return None if entity is None else getattr(entity, attribute)

    return resolve


def _target_project(session: Session, target_id: uuid.UUID) -> uuid.UUID | None:
    target = session.get(Target, target_id)
    return None if target is None else target.project_id


def _constraint_project(session: Session, constraint_id: uuid.UUID) -> uuid.UUID | None:
    constraint = session.get(Constraint, constraint_id)
    return None if constraint is None else _target_project(session, constraint.target_id)


def _variant_project(session: Session, variant_id: uuid.UUID) -> uuid.UUID | None:
    variant = session.get(Variant, variant_id)
    return None if variant is None else _target_project(session, variant.target_id)


def _measurement_project(session: Session, measurement_id: uuid.UUID) -> uuid.UUID | None:
    measurement = session.get(Measurement, measurement_id)
    if measurement is None:
        return None
    return _via(Experiment)(session, measurement.experiment_id)


#: Path parameter name -> the function that finds its owning project.
RESOLVERS: dict[str, Resolver] = {
    "project_id": lambda _session, project_id: project_id,
    "target_id": _target_project,
    "goal_id": _via(Goal),
    "run_id": _via(Run),
    "design_set_id": _via(DesignSet),
    "experiment_id": _via(Experiment),
    "constraint_id": _constraint_project,
    "measurement_id": _measurement_project,
    "variant_id": _variant_project,
}


def owns(session: Session, *, project_id: uuid.UUID, user: User) -> bool:
    """Whether this user may act on this project.

    An unowned project — one written before authentication existed — belongs to
    nobody. It is readable only when the API is running unauthenticated, which
    `config` refuses to do once CORS names a non-local origin. See migration
    `0006_ownership` for why those rows were not backfilled to somebody.
    """
    project = session.get(Project, project_id)
    if project is None:
        return False
    if project.owner_id is None:
        return not get_settings_auth_required()
    return project.owner_id == user.id


def get_settings_auth_required() -> bool:
    # Imported through a function so tests can vary the mode without the module
    # having captured a value at import time.
    from codonlab.config import get_settings

    return get_settings().auth_required


def enforce(
    request: Request,
    user: CurrentUser,
    session: Session = Depends(get_session),
) -> None:
    """Refuse the request unless the caller owns everything it names.

    Every owned path parameter is checked, not just the first. A path like
    ``/design-sets/{design_set_id}/members/{variant_id}`` names two resources
    that could belong to different people, and checking only one of them is how
    a variant from somebody else's target gets added to your design set.
    """
    for name, raw in request.path_params.items():
        if name in PUBLIC_PARAMS:
            continue
        resolve = RESOLVERS.get(name)
        if resolve is None:
            # An unrecognised parameter is not silently allowed: failing closed
            # here is what makes the "forgot to add a resolver" case loud.
            raise _not_found()
        try:
            entity_id = uuid.UUID(str(raw))
        except ValueError as error:
            raise _not_found() from error
        project_id = resolve(session, entity_id)
        if project_id is None or not owns(session, project_id=project_id, user=user):
            raise _not_found()


#: Attach to a router: ``APIRouter(..., dependencies=[OWNERSHIP])``.
OWNERSHIP = Depends(enforce)
