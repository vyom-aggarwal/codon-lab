"""Database engine and session.

Synchronous by choice — see ARCHITECTURE.md §3. Routes, RQ workers, Alembic and
pytest all use this one engine and this one session idiom.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine
from sqlmodel import Session, create_engine

from codonlab.config import get_settings

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_settings().database_url,
            # Verify a pooled connection before handing it out. Workers hold
            # connections across long jobs and Postgres may have closed them.
            pool_pre_ping=True,
            # Without this, a database that is simply not running leaves the
            # request hanging for minutes on psycopg's default timeout. The web
            # app has an error state that names the fix; it can only show it if
            # the failure arrives promptly.
            connect_args={"connect_timeout": 5},
        )
    return _engine


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a scoped session."""
    with Session(get_engine()) as session:
        yield session
