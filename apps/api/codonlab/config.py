"""Runtime configuration, read from the environment.

Deliberately plain ``os.environ`` rather than pydantic-settings: that would be a
dependency beyond the agreed stack, and this module needs to do very little.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

# Host port 5433, matching docker-compose.yml. Inside the compose network the
# api service is given an explicit DATABASE_URL pointing at postgres:5432.
DEFAULT_DATABASE_URL = "postgresql+psycopg://codonlab:codonlab@localhost:5433/codonlab"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"


def _split(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def normalise_database_url(url: str) -> str:
    """Force the psycopg 3 driver onto a Postgres URL.

    Every managed Postgres hands out a URL the standard library and libpq
    understand — ``postgres://`` on Render, Heroku and Fly, ``postgresql://`` on
    Neon and Supabase. SQLAlchemy reads the scheme as a *dialect+driver* name,
    so it takes both of those to mean psycopg **2**, which is not installed. The
    failure is at engine construction, before any request, and the message names
    a package nobody chose to depend on.

    Rewriting the scheme here rather than asking the operator to hand-edit a
    generated connection string: the string is regenerated whenever the database
    is rotated, so a hand-edit is a step that has to be remembered forever and
    silently breaks the deploy the one time it is not.

    Anything already carrying an explicit driver is returned untouched, so a
    deliberate choice is never overridden.
    """
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


class AuthConfigurationError(RuntimeError):
    """Raised at import time when the configuration would expose the API.

    Deliberately fatal. The alternative is a service that starts, serves, and
    lets anyone read every project in the database — a failure with no symptom
    until it matters.
    """


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    redis_url: str
    cors_origins: tuple[str, ...]
    providers: tuple[str, ...]
    # Defaulted so that constructing Settings for a test stays a statement about
    # the thing under test. A test asserting demo-mode behaviour should not have
    # to name an audience claim, and adding a field here should not break every
    # such test. The defaults are the safe local ones: no authentication, which
    # `_guard` then refuses to combine with a non-local CORS origin.
    auth_mode: str = "disabled"
    jwks_url: str | None = None
    jwt_issuer: str | None = None
    jwt_audience: str | None = None
    max_runs_in_flight: int = 3

    @property
    def demo_mode(self) -> bool:
        """True when any configured provider fabricates numbers.

        When this is set the product must render the persistent amber
        'Demo data — not model output' bar on every screen, badge every number the
        mock produced, watermark exports, and refuse to generate primers.
        """
        return "mock" in self.providers

    @property
    def auth_required(self) -> bool:
        return self.auth_mode == "jwt"


#: Local development runs with no identity provider, which is the only reason
#: `disabled` exists. These are the origins that may not be reached from anyone
#: else's machine, so an unauthenticated API behind them is a single-user tool
#: rather than an open one.
LOCAL_ORIGINS = ("localhost", "127.0.0.1", "[::1]", "0.0.0.0")


def _is_local(origin: str) -> bool:
    host = origin.split("://", 1)[-1].split("/", 1)[0]
    host = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
    return host in LOCAL_ORIGINS


def _guard(settings: Settings) -> Settings:
    """Refuse to start in a configuration that would serve the world anonymously.

    The failure this prevents is the ordinary one: deploy the API, point the web
    app at it, forget that `CODONLAB_AUTH` was never set. Nothing breaks. The
    instance simply lets anybody read every project and queue an hour of compute
    per request, and there is no symptom to notice.

    The guard hangs off `CORS_ORIGINS` because that is the setting a deployment
    *must* change — the browser cannot call the API until it names the front
    end's real origin. So the moment the API becomes reachable from a real
    domain, this check has something to fire on.
    """
    if settings.auth_mode not in {"disabled", "jwt"}:
        raise AuthConfigurationError(
            f"CODONLAB_AUTH={settings.auth_mode!r} is not a mode. "
            "Use 'jwt' for a deployed instance, or 'disabled' for local development."
        )

    if settings.auth_mode == "jwt" and not settings.jwks_url:
        raise AuthConfigurationError(
            "CODONLAB_AUTH=jwt needs CODONLAB_JWKS_URL — the JWKS endpoint of your "
            "identity provider, which is where the keys that verify a token are "
            "published. See DEPLOYMENT.md."
        )

    remote = [origin for origin in settings.cors_origins if not _is_local(origin)]
    if settings.auth_mode == "disabled" and remote:
        raise AuthConfigurationError(
            "Refusing to start: CODONLAB_AUTH is 'disabled' while CORS_ORIGINS allows "
            f"{', '.join(remote)}. That combination serves every project in the database "
            "to anyone who finds the URL, and lets them queue a design run per request. "
            "Set CODONLAB_AUTH=jwt with CODONLAB_JWKS_URL, or keep CORS_ORIGINS on "
            "localhost only."
        )
    return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return _guard(
        Settings(
            database_url=normalise_database_url(
                os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
            ),
            redis_url=os.environ.get("REDIS_URL", DEFAULT_REDIS_URL),
            cors_origins=_split(os.environ.get("CORS_ORIGINS", "http://localhost:3000")),
            providers=_split(os.environ.get("CODONLAB_PROVIDERS", "mock")),
            auth_mode=os.environ.get("CODONLAB_AUTH", "disabled").strip().lower(),
            jwks_url=os.environ.get("CODONLAB_JWKS_URL") or None,
            jwt_issuer=os.environ.get("CODONLAB_JWT_ISSUER") or None,
            jwt_audience=os.environ.get("CODONLAB_JWT_AUDIENCE") or None,
            #: One worker runs one job at a time and a run can take an hour, so
            #: a queue deeper than this is already a day's backlog for whoever
            #: is behind it. Not a rate — a ceiling on work *in flight*, which
            #: is the quantity the single worker actually rations.
            max_runs_in_flight=int(os.environ.get("CODONLAB_MAX_RUNS_IN_FLIGHT", "3")),
        )
    )
