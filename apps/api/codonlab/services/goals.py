"""Goals: parse, edit, confirm.

The Phase 3 gate lives in `require_confirmed`. A run cannot start from a parse
the user has not confirmed, and that is enforced here rather than in the UI —
a check that only exists on a screen is a check the API does not have.

Confirmation is bound to the exact spec that was on screen. Editing a chip
after confirming clears the confirmation, because what the user agreed to was
that objective, not that row in the database.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlmodel import Session, col, select

from codonlab.domain.goal import GoalSpec, ParsedGoal, restate, spec_from_json, spec_to_json
from codonlab.models import Goal, ProvenanceEvent, ProvenanceEventKind
from codonlab.models.base import utcnow
from codonlab.parsers import parse as parse_goal
from codonlab.services.targets import ServiceError, canonical_scheme, require_target


def _record(
    session: Session,
    *,
    kind: ProvenanceEventKind,
    goal: Goal,
    actor: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    session.add(
        ProvenanceEvent(
            kind=kind,
            project_id=goal.project_id,
            subject_type="goal",
            subject_id=goal.id,
            actor=actor,
            payload=payload or {},
        )
    )


def _store(goal: Goal, parsed: ParsedGoal) -> None:
    goal.parsed_spec = {
        **spec_to_json(parsed.spec),
        "method": parsed.method.value,
        "note": parsed.note,
        "matched_phrases": list(parsed.matched_phrases),
        "restatement": restate(parsed.spec),
    }


def create(session: Session, *, target_id: uuid.UUID, text: str) -> Goal:
    """Parse a free-text goal into an unconfirmed structured objective."""
    if not text.strip():
        raise ServiceError(
            "The goal is empty.",
            "Describe what you want to change about this protein, in your own words.",
        )

    target = require_target(session, target_id)
    if canonical_scheme(session, target.id) is None:
        # Ordering matters: a goal parsed against a target whose numbering is
        # unsettled would produce constraints and mutation codes that mean
        # something different once a scheme is confirmed.
        raise ServiceError(
            "This target has no canonical numbering scheme.",
            "Reconcile numbering and confirm a scheme before setting a goal.",
        )

    parsed = parse_goal(text)
    goal = Goal(project_id=target.project_id, target_id=target.id, raw_text=text, parsed_spec={})
    _store(goal, parsed)
    session.add(goal)
    session.flush()

    _record(
        session,
        kind=ProvenanceEventKind.GOAL_PARSED,
        goal=goal,
        payload={"method": parsed.method.value, "raw_text": text},
    )
    session.commit()
    session.refresh(goal)
    return goal


def require_goal(session: Session, goal_id: uuid.UUID) -> Goal:
    goal = session.get(Goal, goal_id)
    if goal is None:
        raise ServiceError("That goal does not exist.", "Open it from the project page.")
    return goal


def update_spec(session: Session, *, goal_id: uuid.UUID, spec: GoalSpec) -> Goal:
    """Replace the parsed objective with the user's edited chips.

    Any edit clears confirmation. The user confirmed a specific objective, not
    a database row, so a changed objective is by definition unconfirmed again.
    """
    goal = require_goal(session, goal_id)
    previous = dict(goal.parsed_spec)

    goal.parsed_spec = {
        **spec_to_json(spec),
        # Edited by hand, so no longer attributable to either parser.
        "method": "edited",
        "note": "Edited by hand.",
        "matched_phrases": [],
        "restatement": restate(spec),
    }
    was_confirmed = goal.confirmed_at is not None
    goal.confirmed_at = None
    session.add(goal)

    _record(
        session,
        kind=ProvenanceEventKind.GOAL_PARSED,
        goal=goal,
        payload={
            "action": "edited",
            "cleared_confirmation": was_confirmed,
            "before": previous,
            "after": goal.parsed_spec,
        },
    )
    session.commit()
    session.refresh(goal)
    return goal


def confirm(session: Session, *, goal_id: uuid.UUID, actor: str | None = None) -> Goal:
    """Confirm the parse. The only thing that makes a goal runnable."""
    goal = require_goal(session, goal_id)
    spec = spec_from_json(goal.parsed_spec)

    if not spec.is_runnable:
        raise ServiceError(
            f"This objective is incomplete: {', '.join(spec.missing_required)} not set.",
            "Set an objective chip, then confirm.",
        )

    goal.confirmed_at = utcnow()
    session.add(goal)
    _record(
        session,
        kind=ProvenanceEventKind.GOAL_CONFIRMED,
        goal=goal,
        actor=actor,
        # The confirmed spec is recorded in full: what was agreed to is part of
        # the provenance trail, not just that agreement happened.
        payload={"confirmed_spec": goal.parsed_spec},
    )
    session.commit()
    session.refresh(goal)
    return goal


def require_confirmed(session: Session, goal_id: uuid.UUID) -> Goal:
    """The Phase 3 gate. Every run-starting path must pass through this.

    Enforced in the service layer so that no route, worker, or future caller
    can start a run from an objective the user never agreed to.
    """
    goal = require_goal(session, goal_id)
    if goal.confirmed_at is None:
        raise ServiceError(
            "This objective has not been confirmed.",
            "Review the parsed objective and confirm it before starting a run.",
        )
    return goal


def goals_for(session: Session, target_id: uuid.UUID) -> list[Goal]:
    return list(
        session.exec(
            select(Goal)
            .where(col(Goal.target_id) == target_id)
            .order_by(col(Goal.created_at).desc())
        ).all()
    )
