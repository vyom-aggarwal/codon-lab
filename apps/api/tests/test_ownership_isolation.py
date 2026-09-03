"""Two researchers, two projects, and neither can see the other's.

This is the claim the whole ownership change exists to make, so it is asserted
against a **real Postgres** rather than a stub. `Project.settings` is a JSONB
column, so SQLite is not a substitute and there is no in-memory shortcut here.

The rest of this suite is hermetic and runs anywhere. This module needs the
database, so it skips when there is not one — which is the case on a developer's
host — and runs inside the api container, where `docker compose` has one:

    docker compose exec -T api sh -c "cd /app && python -m pytest -q"

That is the documented way to run the suite (`HANDOFF.md` §5), so this is not an
optional extra that nobody executes.
"""

from __future__ import annotations

import uuid

import pytest
from sqlmodel import Session, create_engine

from codonlab.config import get_settings
from codonlab.models import Project, User
from codonlab.ownership import owns

#: Seconds to wait for Postgres before deciding there is not one.
#:
#: Short on purpose. Without it, a host with no database sits through libpq's
#: default connect timeout on every one of these tests — measured at 135 seconds
#: to skip six of them, which is longer than the rest of the suite takes to run
#: and is exactly how a skip-guard turns into something people disable.
CONNECT_TIMEOUT_SECONDS = 2


def _engine() -> object | None:
    """A connected engine, or None if there is no database to talk to."""
    try:
        engine = create_engine(
            get_settings().database_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
        )
        with engine.connect():
            return engine
    except Exception:
        return None


ENGINE = _engine()

pytestmark = pytest.mark.skipif(
    ENGINE is None,
    reason="needs a live Postgres; run inside the api container",
)


@pytest.fixture
def session() -> Session:
    """A session that rolls everything back.

    The gate and the seed both use this database, so a test that committed rows
    would leave two users and two projects behind on every run — visible in the
    project list of whoever looks next.
    """
    with Session(ENGINE) as session:  # type: ignore[arg-type]
        transaction = session.begin_nested() if session.in_transaction() else None
        try:
            yield session
        finally:
            if transaction is not None and transaction.is_active:
                transaction.rollback()
            session.rollback()


@pytest.fixture
def two_labs(session: Session) -> tuple[User, User, Project, Project]:
    """Alice and Bob, each with a project the other must not see."""
    stamp = uuid.uuid4().hex[:8]
    alice = User(subject=f"test|alice-{stamp}", email="alice@lab.example")
    bob = User(subject=f"test|bob-{stamp}", email="bob@lab.example")
    session.add(alice)
    session.add(bob)
    session.flush()

    hers = Project(name=f"Alice lipase {stamp}", owner_id=alice.id)
    his = Project(name=f"Bob luciferase {stamp}", owner_id=bob.id)
    session.add(hers)
    session.add(his)
    session.flush()
    return alice, bob, hers, his


def test_an_owner_reaches_their_own_project(
    session: Session, two_labs: tuple[User, User, Project, Project]
) -> None:
    alice, _, hers, _ = two_labs
    assert owns(session, project_id=hers.id, user=alice) is True


def test_a_stranger_does_not(
    session: Session, two_labs: tuple[User, User, Project, Project]
) -> None:
    """The point of the exercise. Bob holds a perfectly valid token; it does not
    make Alice's unpublished sequences his."""
    _, bob, hers, _ = two_labs
    assert owns(session, project_id=hers.id, user=bob) is False


def test_the_refusal_is_mutual(
    session: Session, two_labs: tuple[User, User, Project, Project]
) -> None:
    """Asserted in both directions so that a check accidentally comparing a
    constant — or always returning the first user's answer — cannot pass."""
    alice, bob, _hers, his = two_labs
    assert owns(session, project_id=his.id, user=bob) is True
    assert owns(session, project_id=his.id, user=alice) is False


def test_a_project_that_does_not_exist_is_refused(
    session: Session, two_labs: tuple[User, User, Project, Project]
) -> None:
    """Fail closed: a missing row must not read as "unowned, therefore anyone"."""
    alice, _, _, _ = two_labs
    assert owns(session, project_id=uuid.uuid4(), user=alice) is False


def test_an_unowned_project_is_hidden_once_authentication_is_on(
    session: Session,
    two_labs: tuple[User, User, Project, Project],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rows written before authentication existed belong to nobody.

    Migration 0006 deliberately does not backfill them: nothing records who
    created them, and assigning them to whoever signs in first would be
    inventing a claim about authorship. Under `jwt` they are served to no one.
    """
    alice, _, _, _ = two_labs
    orphan = Project(name=f"Legacy {uuid.uuid4().hex[:8]}", owner_id=None)
    session.add(orphan)
    session.flush()

    monkeypatch.setenv("CODONLAB_AUTH", "jwt")
    monkeypatch.setenv("CODONLAB_JWKS_URL", "https://example.test/.well-known/jwks.json")
    monkeypatch.setenv("CORS_ORIGINS", "https://codon-lab.example.app")
    get_settings.cache_clear()
    try:
        assert owns(session, project_id=orphan.id, user=alice) is False
    finally:
        get_settings.cache_clear()


def test_an_unowned_project_stays_visible_to_a_local_instance(
    session: Session, two_labs: tuple[User, User, Project, Project]
) -> None:
    """The other half of the same decision.

    Running unauthenticated is a single-user local machine, and a developer's
    existing work must not vanish on upgrade. `config` refuses to start in this
    mode once CORS names a non-local origin, which is what keeps this branch off
    a deployment.
    """
    alice, _, _, _ = two_labs
    orphan = Project(name=f"Legacy {uuid.uuid4().hex[:8]}", owner_id=None)
    session.add(orphan)
    session.flush()

    get_settings.cache_clear()
    assert get_settings().auth_required is False, "this test assumes the local default"
    assert owns(session, project_id=orphan.id, user=alice) is True
