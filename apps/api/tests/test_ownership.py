"""Ownership: nobody reads anybody else's data.

The tests here are the ones that still matter in a year.

Behaviour — a caller who does not own a project gets nothing, and gets it as a
404 rather than a 403 — is asserted in `scripts/verify_gates.py`, over HTTP
against real Postgres, because this suite is hermetic by design.

What lives here is *coverage*. `ownership.enforce` resolves entities out of
`request.path_params`, so its correctness depends on a mapping being complete.
A test that only exercised today's routes would pass forever while the mapping
silently fell behind the application. Instead it walks the real route table and
fails when the application grows a path parameter nobody has classified.
"""

from __future__ import annotations

from fastapi.routing import APIRoute

from codonlab.main import app
from codonlab.ownership import PUBLIC_PARAMS, RESOLVERS

# --------------------------------------------------------------------------- #
# Coverage: the mapping keeps up with the application
# --------------------------------------------------------------------------- #


def _api_routes() -> list[APIRoute]:
    """Every APIRoute the application serves, including included routers.

    Walks recursively rather than reading `app.routes` directly. This FastAPI
    version does not flatten `include_router` into `app.routes` — it wraps each
    one in a private `_IncludedRouter` whose real routes hang off
    `original_router`. Iterating `app.routes` alone finds four documentation
    endpoints and no path parameters at all, which makes every assertion below
    pass by looking at nothing.

    That is not hypothetical: this helper originally did exactly that, and the
    tests passed while resolvers were deleted out from under them. The recursion
    handles both shapes, so a FastAPI that changes its mind either way keeps
    working.
    """
    found: list[APIRoute] = []
    seen: set[int] = set()

    def walk(routes: object) -> None:
        for route in routes or ():  # type: ignore[union-attr]
            if id(route) in seen:
                continue
            seen.add(id(route))
            if isinstance(route, APIRoute):
                found.append(route)
            inner = getattr(route, "original_router", None)
            if inner is not None:
                walk(getattr(inner, "routes", ()))
            walk(getattr(route, "routes", ()))

    walk(app.routes)
    return found


def _served_path_params() -> set[str]:
    """Every path parameter the application actually serves."""
    found: set[str] = set()
    for route in _api_routes():
        found.update(param.alias or param.name for param in route.dependant.path_params)
    return found


def test_the_route_walk_actually_finds_the_application() -> None:
    """Guards the guard.

    Every assertion in this file is a set difference over the served routes, and
    a set difference against an empty set is vacuously true. If the walk ever
    stops finding routes — a FastAPI upgrade changing how routers are
    included — these tests would go green while checking nothing. This is the
    one that goes red instead.
    """
    routes = _api_routes()
    assert len(routes) > 40, f"only found {len(routes)} routes; the walk is not reaching them"
    assert "target_id" in _served_path_params()


def test_every_path_parameter_is_either_resolvable_or_declared_public() -> None:
    """The guard fails closed on an unknown parameter, so an unclassified one is
    a 404 on a working endpoint rather than a hole. Either way it is a bug, and
    this is the test that catches it at the moment the route is added rather
    than when somebody reports a broken screen.
    """
    unclassified = _served_path_params() - set(RESOLVERS) - PUBLIC_PARAMS
    assert not unclassified, (
        f"These path parameters are neither resolvable to a project nor declared "
        f"public: {sorted(unclassified)}. Add a resolver to ownership.RESOLVERS, or "
        f"add the name to ownership.PUBLIC_PARAMS with a comment saying why it "
        f"identifies nothing ownable."
    )


def test_the_public_list_is_not_quietly_absorbing_real_parameters() -> None:
    """`PUBLIC_PARAMS` is an escape hatch, so it is kept small and explicit.

    Anything ending in `_id` names a row somewhere. If one ever appears on the
    public list it is far more likely to be a mistake than a considered
    exemption, and the mistake is invisible — the endpoint keeps working, just
    without a check.
    """
    id_shaped = {name for name in PUBLIC_PARAMS if name.endswith("_id")}
    assert not id_shaped, (
        f"{sorted(id_shaped)} look like row identifiers but are declared public. "
        f"An `_id` parameter almost certainly needs a resolver instead."
    )


def test_every_owned_router_carries_the_dependency() -> None:
    """Ownership is attached per router, so a router added without it would
    serve its whole surface unguarded. This asserts the property directly: any
    route with a resolvable path parameter must have the guard in its
    dependency chain.
    """
    from codonlab.ownership import enforce

    unguarded: list[str] = []
    for route in _api_routes():
        names = {param.alias or param.name for param in route.dependant.path_params}
        if not (names & set(RESOLVERS)):
            continue
        calls = {dependency.call for dependency in route.dependant.dependencies}
        if enforce not in calls:
            unguarded.append(f"{sorted(route.methods)} {route.path}")

    assert not unguarded, (
        "These routes name an owned resource but do not enforce ownership: "
        f"{unguarded}. Add `dependencies=[OWNERSHIP]` to their router."
    )


# Behaviour — who may see what — is asserted in `scripts/verify_gates.py`
# instead, over HTTP against real Postgres. Two users, two projects, and one
# asking for the other's. It cannot live here: this suite is hermetic and never
# touches a database, and `Project.settings` is a JSONB column, so SQLite is not
# a substitute. See the "Deployment" section of the gate.


def test_health_and_meta_stay_open_to_an_unauthenticated_caller() -> None:
    """Two endpoints must answer without a token, for different reasons.

    `/health` is what the platform polls to decide whether a deploy succeeded.
    Behind authentication it fails every check, the deploy is rolled back, and
    the reported cause is an unhealthy service rather than a 401.

    `/meta` is fetched by the root layout to decide whether to show the demo
    banner. Behind authentication, a signed-out visitor's very first page render
    throws — including on the landing page, which has no session by design.

    Both are easy to break by adding a router-level dependency for consistency,
    and neither failure looks like an auth problem when it happens.
    """
    from codonlab.auth import current_user
    from codonlab.ownership import enforce

    for route in _api_routes():
        if route.path not in {"/health", "/meta"}:
            continue
        calls = {dependency.call for dependency in route.dependant.dependencies}
        assert enforce not in calls, f"{route.path} must not enforce ownership"
        assert current_user not in calls, f"{route.path} must not require a caller"
