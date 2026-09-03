"""Runtime configuration, and the one transformation it performs.

`normalise_database_url` exists because of a deployment failure that happens
before the application serves a single request, with an error message that names
a package nobody chose to depend on. It is a small function guarding a step that
is easy to get wrong exactly once and then never think about again.
"""

from __future__ import annotations

import pytest

from codonlab.config import normalise_database_url

# The connection strings the managed Postgres services actually hand out. These
# are the shapes, with the credentials replaced — the scheme is the whole point.
MANAGED_URLS = [
    # Render, Heroku and Fly issue the bare `postgres://` scheme.
    ("postgres://codonlab:secret@dpg-abc123.oregon-postgres.render.com/codonlab_db"),
    # Neon and Supabase issue `postgresql://`, usually with query parameters.
    ("postgresql://codonlab:secret@ep-cool-name.eu-central-1.aws.neon.tech/codonlab?sslmode=require"),
]


@pytest.mark.parametrize("url", MANAGED_URLS)
def test_a_managed_connection_string_is_given_the_psycopg_driver(url: str) -> None:
    """SQLAlchemy reads a URL's scheme as dialect+driver.

    `postgres://` and `postgresql://` both resolve to psycopg **2**, which this
    project does not install — it uses psycopg 3. Without this rewrite the
    engine raises at construction time on every managed host.
    """
    normalised = normalise_database_url(url)
    assert normalised.startswith("postgresql+psycopg://")


@pytest.mark.parametrize("url", MANAGED_URLS)
def test_everything_after_the_scheme_survives_untouched(url: str) -> None:
    """The rewrite replaces a prefix and nothing else.

    Credentials, host, port, database name and query parameters all carry
    meaning — `?sslmode=require` in particular is not optional on Neon. A
    normaliser that dropped the query string would produce a URL that connects
    locally and is refused in production.
    """
    normalised = normalise_database_url(url)
    assert normalised.split("://", 1)[1] == url.split("://", 1)[1]


def test_an_explicit_driver_is_never_overridden() -> None:
    """A deliberate choice wins. If someone has pinned a driver, that is a
    decision, and silently rewriting it would be the same class of bug this
    function exists to prevent — a connection string changed behind the
    operator's back."""
    pinned = "postgresql+asyncpg://user:pw@host/db"
    assert normalise_database_url(pinned) == pinned


def test_a_non_postgres_url_is_left_alone() -> None:
    """The function matches on prefix, so it must not touch anything else.
    SQLite is what the test suite itself runs on."""
    assert normalise_database_url("sqlite:///./test.db") == "sqlite:///./test.db"


def test_the_local_default_is_already_correct() -> None:
    """The compose and local defaults carry the driver already, so normalising
    them is a no-op. Asserted so that a change to the default cannot quietly
    start depending on the rewrite."""
    from codonlab.config import DEFAULT_DATABASE_URL

    assert DEFAULT_DATABASE_URL.startswith("postgresql+psycopg://")
    assert normalise_database_url(DEFAULT_DATABASE_URL) == DEFAULT_DATABASE_URL
