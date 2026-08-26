"""Design sets: select variants, stack them, and say what that assumes.

Specification §5.7. This service is the orchestration half; the arithmetic and the
rules are in `domain/epistasis` and `domain/costing`, which are pure.

Four things here are load-bearing.

**A design set belongs to one run.** Every number on the screen — each single's
score, each additive total — comes from that run, so "which model produced this"
has one answer. `DesignSet.run_id` is NOT NULL (migration 0004).

**A constrained position needs an explicit override, and the override is logged.**
Specification §7: "Never propose mutations at constrained positions without an
explicit override, and log the override." Adding such a variant without
`override=True` is refused with the constraint named; adding it with one writes a
`CONSTRAINT_OVERRIDDEN` provenance event carrying the reason the user typed.

**The 8A pair flag is measured, or it is unknown.** Never absent-and-therefore-
fine. When there is no structure, no reconciled author numbering, or the residue
is unresolved in the coordinates, the pair reports `Proximity.UNKNOWN` with the
reason. `domain/epistasis.Proximity` has three values precisely so this cannot
collapse into "not flagged".

**Stacked totals are derived on read and never stored.** Same rule as the
consensus in `domain/aggregate`: an additive sum is not a model output, and
writing it as a `Score` would require inventing a `ModelVersion` that produced
it. See ARCHITECTURE.md §4.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlmodel import Session, col, select

from catalyst.domain import costing
from catalyst.domain import epistasis as epistasis_domain
from catalyst.domain.variants import hgvs_of
from catalyst.features import structure as structure_features
from catalyst.models import (
    DesignSet,
    DesignSetMember,
    NumberingScheme,
    ProvenanceEvent,
    ProvenanceEventKind,
    Structure,
    Target,
    Variant,
)
from catalyst.models.enums import NumberingKind
from catalyst.providers import MetricSpec
from catalyst.services import constraints as constraint_service
from catalyst.services import runs as run_service
from catalyst.services.targets import (
    ServiceError,
    canonical_scheme,
    labels_of,
    refetch_structure,
    require_project,
    require_target,
    structures_for,
)
from catalyst.services.targets import schemes_for as service_schemes

#: How many combinations the stacking builder will enumerate in one request.
#: An interface guard, not a scientific one: C(n, k) grows fast enough that an
#: unbounded builder would hang rather than answer. Always reported when reached
#: — see `domain/epistasis.enumerate_stacks`.
DEFAULT_STACK_LIMIT = 500

#: A cap on how many mutations may be stacked into one construct in a single
#: request, for the same reason. Not a claim about what is biologically sensible.
MAX_STACK_SIZE = 8


@dataclass(frozen=True, slots=True)
class MemberView:
    """One design in a set, single or stacked."""

    variant_id: uuid.UUID
    code: str
    hgvs: str
    #: Component mutation codes. Length 1 for a single-point design.
    mutations: tuple[str, ...]
    sequence_positions: tuple[int, ...]
    is_stacked: bool
    included_via_override: bool
    override_reason: str | None
    #: Pair flags, only for stacked designs. Empty for singles by definition.
    pairs: tuple[epistasis_domain.PairFlag, ...] = ()
    #: Per-metric additive totals, only for stacked designs.
    additive: tuple[epistasis_domain.AdditiveEstimate, ...] = ()


@dataclass(frozen=True, slots=True)
class DesignSetView:
    design_set_id: uuid.UUID
    project_id: uuid.UUID
    run_id: uuid.UUID
    name: str
    note: str | None
    scheme_label: str
    members: tuple[MemberView, ...]
    #: The epistasis warning, as data. Rendered whenever `stacked_designs` > 0.
    warning: Mapping[str, Any]
    cost: costing.CostEstimate
    #: How the pair separations were measured, or why they were not.
    geometry_manifest: Mapping[str, Any] = field(default_factory=dict)
    geometry_note: str | None = None
    is_demo: bool = False


# --------------------------------------------------------------------------- #
# Reading the run a set is built on
# --------------------------------------------------------------------------- #


def require_set(session: Session, design_set_id: uuid.UUID) -> DesignSet:
    found = session.get(DesignSet, design_set_id)
    if found is None:
        raise ServiceError(
            "That design set does not exist.",
            "Open the workbench and build one from a run's ranking.",
        )
    return found


def _variants_by_code(session: Session, target_id: uuid.UUID) -> dict[str, Variant]:
    rows = session.exec(select(Variant).where(col(Variant.target_id) == target_id)).all()
    return {row.code: row for row in rows}


def _author_scheme(
    session: Session, target_id: uuid.UUID, structure: Structure
) -> NumberingScheme | None:
    """The reconciled PDB-author scheme for a structure, or None.

    Mirrors `services/runs._author_scheme` rather than importing it, because that
    one is private to the run pipeline; the matching rule is the same and is
    asserted by a test so the two cannot drift apart unnoticed.
    """
    schemes = [
        scheme
        for scheme in service_schemes(session, target_id)
        if scheme.kind is NumberingKind.PDB_AUTHOR
    ]
    exact = f"{structure.identifier} chain {structure.chain}, author numbering"
    for scheme in schemes:
        if scheme.label == exact:
            return scheme
    for scheme in schemes:
        if structure.identifier and scheme.label.startswith(str(structure.identifier)):
            return scheme
    return None


@dataclass(frozen=True, slots=True)
class _Geometry:
    separations: dict[tuple[int, int], float]
    manifest: dict[str, Any]
    #: Why a pair may be unknown. Always a complete sentence — it is shown to the
    #: user on the pair itself, not only in a footnote.
    unknown_reason: str
    note: str | None = None


def _measure_pairs(
    session: Session, target: Target, positions: Sequence[int]
) -> _Geometry:
    """Minimum non-hydrogen atom separations between the mutated positions.

    Every failure path returns a reason rather than an empty result that reads as
    "nothing was close". The reason travels onto each unmeasured pair.
    """
    if len(set(positions)) < 2:
        return _Geometry(
            separations={},
            manifest={},
            unknown_reason="No pair to measure.",
        )

    structures = structures_for(session, target.id)
    if not structures:
        reason = (
            "No structure is attached to this target, so the separation between "
            "these positions was not measured."
        )
        return _Geometry(separations={}, manifest={}, unknown_reason=reason, note=reason)

    structure = structures[-1]
    scheme = _author_scheme(session, target.id, structure)
    if scheme is None:
        reason = (
            "This structure's numbering has not been reconciled to the sequence, so "
            "no residue could be located in it without guessing."
        )
        return _Geometry(separations={}, manifest={}, unknown_reason=reason, note=reason)

    try:
        fetched = refetch_structure(structure)
    except ServiceError as error:
        reason = f"The structure could not be read: {error}"
        return _Geometry(separations={}, manifest={}, unknown_reason=reason, note=reason)

    try:
        measured = structure_features.pairwise_min_distances(
            structure_text=fetched.text,
            chain_id=structure.chain or "A",
            author_labels=labels_of(scheme),
            positions=positions,
        )
    except structure_features.StructureFeatureError as error:
        reason = f"Geometry could not be measured: {error}"
        return _Geometry(separations={}, manifest={}, unknown_reason=reason, note=reason)

    manifest = dict(measured.manifest)
    manifest["cutoff_angstrom"] = epistasis_domain.PAIR_PROXIMITY_ANGSTROM
    manifest["convention"] = epistasis_domain.PAIR_DISTANCE_CONVENTION
    manifest["structure"] = f"{structure.source.value} {structure.identifier}"
    manifest["structure_content_hash"] = structure.content_hash

    note = None
    if measured.unresolved:
        note = (
            f"{len(measured.unresolved)} position(s) are not resolved in these "
            "coordinates, so pairs involving them read as unknown rather than as "
            "far apart."
        )

    return _Geometry(
        separations=measured.separations,
        manifest=manifest,
        unknown_reason=(
            "This residue is not resolved in the loaded coordinates, so the "
            "separation could not be measured."
        ),
        note=note,
    )


# --------------------------------------------------------------------------- #
# Building
# --------------------------------------------------------------------------- #


def create(
    session: Session,
    *,
    run_id: uuid.UUID,
    name: str,
    note: str | None = None,
    budget_amount: float | None = None,
    budget_currency: str | None = None,
    actor: str | None = None,
) -> DesignSet:
    """Start a design set from a run's ranking."""
    run = run_service.require_run(session, run_id)
    label = name.strip()
    if not label:
        raise ServiceError(
            "A design set needs a name.",
            "Name it after the experiment you intend to run.",
        )

    design_set = DesignSet(
        project_id=run.project_id,
        run_id=run.id,
        name=label,
        note=note,
        budget_amount=budget_amount,
        budget_currency=budget_currency,
    )
    session.add(design_set)
    session.flush()

    session.add(
        ProvenanceEvent(
            kind=ProvenanceEventKind.DESIGN_SET_CREATED,
            project_id=run.project_id,
            run_id=run.id,
            subject_type="design_set",
            subject_id=design_set.id,
            actor=actor,
            payload={"name": label, "run_id": str(run.id)},
        )
    )
    session.commit()
    session.refresh(design_set)
    return design_set


def _constrained(session: Session, target_id: uuid.UUID) -> dict[int, list[str]]:
    return constraint_service.constrained_positions(session, target_id)


def add_members(
    session: Session,
    *,
    design_set_id: uuid.UUID,
    codes: Sequence[str],
    override: bool = False,
    override_reason: str | None = None,
    actor: str | None = None,
) -> DesignSet:
    """Add existing variants to a set, by their canonical mutation codes.

    Refuses any variant sitting at a constrained position unless `override` is
    true and a reason is given, and logs every override. Specification §7 makes
    the logging mandatory, so it happens here rather than at a call site that
    could forget.
    """
    design_set = require_set(session, design_set_id)
    run = run_service.require_run(session, design_set.run_id)
    target = require_target(session, run.target_id)

    known = _variants_by_code(session, target.id)
    missing = [code for code in codes if code not in known]
    if missing:
        raise ServiceError(
            f"No variant on this target is called {', '.join(sorted(missing)[:5])}.",
            "Add designs from this run's ranking, where the codes are written in "
            "the confirmed numbering scheme.",
        )

    constrained = _constrained(session, target.id)
    blocked: dict[str, list[str]] = {}
    for code in codes:
        variant = known[code]
        hits = sorted(
            {
                kind
                for position in _positions_of(variant)
                for kind in constrained.get(position, [])
            }
        )
        if hits:
            blocked[code] = hits

    if blocked and not override:
        listed = "; ".join(f"{code} ({', '.join(kinds)})" for code, kinds in blocked.items())
        raise ServiceError(
            f"These designs sit at constrained positions: {listed}.",
            "Override the constraint explicitly and state why — the override is "
            "recorded on the design set.",
        )
    if blocked and not (override_reason or "").strip():
        raise ServiceError(
            "An override needs a stated reason.",
            "Say why this constrained position may be mutated. It is recorded.",
        )

    existing = {
        member.variant_id
        for member in session.exec(
            select(DesignSetMember).where(
                col(DesignSetMember.design_set_id) == design_set.id
            )
        ).all()
    }

    for code in codes:
        variant = known[code]
        if variant.id in existing:
            continue
        was_overridden = code in blocked
        session.add(
            DesignSetMember(
                design_set_id=design_set.id,
                variant_id=variant.id,
                included_via_override=was_overridden,
                override_reason=override_reason if was_overridden else None,
            )
        )
        existing.add(variant.id)

        if was_overridden:
            session.add(
                ProvenanceEvent(
                    kind=ProvenanceEventKind.CONSTRAINT_OVERRIDDEN,
                    project_id=design_set.project_id,
                    run_id=design_set.run_id,
                    subject_type="design_set_member",
                    subject_id=design_set.id,
                    actor=actor,
                    payload={
                        "code": code,
                        "constraints": blocked[code],
                        "reason": override_reason,
                    },
                )
            )

    session.commit()
    session.refresh(design_set)
    return design_set


def remove_member(
    session: Session, *, design_set_id: uuid.UUID, variant_id: uuid.UUID
) -> None:
    member = session.exec(
        select(DesignSetMember).where(
            col(DesignSetMember.design_set_id) == design_set_id,
            col(DesignSetMember.variant_id) == variant_id,
        )
    ).first()
    if member is None:
        raise ServiceError(
            "That design is not in this set.",
            "Reload the design set and try again.",
        )
    session.delete(member)
    session.commit()


def _positions_of(variant: Variant) -> tuple[int, ...]:
    """The 1-based sequence indices a variant's mutations sit at.

    A single-point variant carries `position`; a stacked one does not, because
    the column is scalar. Stacked positions are recorded in `features` at build
    time rather than re-derived from the code — the code is written in the
    canonical scheme, and converting a canonical label back to a sequence index
    by arithmetic is exactly what ARCHITECTURE.md §9 forbids.
    """
    if variant.position is not None:
        return (int(variant.position),)
    stored = (variant.features or {}).get("sequence_positions")
    if isinstance(stored, list):
        return tuple(int(value) for value in stored)
    return ()


def stack_members(
    session: Session,
    *,
    design_set_id: uuid.UUID,
    codes: Sequence[str],
    size: int,
    limit: int = DEFAULT_STACK_LIMIT,
    actor: str | None = None,
) -> tuple[DesignSet, tuple[str, ...]]:
    """Build every combination of `size` mutations from `codes` into the set.

    Returns the set and the notes describing what was left out — combinations
    that place two mutations at one position, and the cap if it was reached.
    """
    if size > MAX_STACK_SIZE:
        raise ServiceError(
            f"This builder stacks at most {MAX_STACK_SIZE} mutations into one construct.",
            "Build the smaller combinations first, or add the construct by hand.",
        )

    design_set = require_set(session, design_set_id)
    run = run_service.require_run(session, design_set.run_id)
    target = require_target(session, run.target_id)

    known = _variants_by_code(session, target.id)
    missing = [code for code in codes if code not in known]
    if missing:
        raise ServiceError(
            f"No variant on this target is called {', '.join(sorted(missing)[:5])}.",
            "Stack designs drawn from this run's ranking.",
        )

    positions: dict[str, int] = {}
    for code in codes:
        found = _positions_of(known[code])
        if len(found) != 1:
            raise ServiceError(
                f"{code} is not a single-point design and cannot be stacked here.",
                "Stack single substitutions; a stacked design is already a combination.",
            )
        positions[code] = found[0]

    try:
        designs, notes = epistasis_domain.enumerate_stacks(
            codes, positions, size=size, limit=limit
        )
    except epistasis_domain.StackError as error:
        raise ServiceError(str(error), error.remedy) from error

    constrained = _constrained(session, target.id)
    existing_codes = _variants_by_code(session, target.id)
    members = {
        member.variant_id
        for member in session.exec(
            select(DesignSetMember).where(
                col(DesignSetMember.design_set_id) == design_set.id
            )
        ).all()
    }

    blocked_designs = 0
    for design in designs:
        touched = sorted({kind for p in design.positions for kind in constrained.get(p, [])})
        if touched:
            # A stacked design inherits its components' constraints. Adding it
            # silently would route around the override rule, so it is skipped and
            # counted rather than included.
            blocked_designs += 1
            continue

        variant = existing_codes.get(design.code)
        if variant is None:
            variant = Variant(
                target_id=target.id,
                mutations=list(design.codes),
                code=design.code,
                # Scalar and therefore meaningless for a combination. The
                # positions live in `features`, keyed explicitly.
                position=None,
                region=None,
                features={"sequence_positions": list(design.positions)},
            )
            session.add(variant)
            session.flush()
            existing_codes[design.code] = variant

        if variant.id not in members:
            session.add(
                DesignSetMember(design_set_id=design_set.id, variant_id=variant.id)
            )
            members.add(variant.id)

    all_notes = list(notes)
    if blocked_designs:
        all_notes.append(
            f"{blocked_designs:,} combination(s) were not added because they touch a "
            "constrained position. Add them individually with an explicit override."
        )

    session.add(
        ProvenanceEvent(
            kind=ProvenanceEventKind.DESIGN_SET_CREATED,
            project_id=design_set.project_id,
            run_id=design_set.run_id,
            subject_type="design_set_stack",
            subject_id=design_set.id,
            actor=actor,
            payload={
                "from_codes": list(codes),
                "size": size,
                "built": len(designs) - blocked_designs,
                "notes": all_notes,
            },
        )
    )
    session.commit()
    session.refresh(design_set)
    return design_set, tuple(all_notes)


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #


def _score_values(
    session: Session, run_id: uuid.UUID
) -> tuple[dict[str, dict[str, float]], dict[str, MetricSpec]]:
    """Every score in the run, as {mutation code: {metric: value}}.

    Read from the run the set belongs to and from no other, so an additive total
    cannot silently draw on a different run's numbers.
    """
    ranking = run_service.ranking(session, run_id=run_id, limit=None, include_filtered=True)
    values: dict[str, dict[str, float]] = {}
    for row in ranking.rows:
        values[row.code] = {cell.metric: cell.value for cell in row.cells}
    metrics = {metric.id: metric for metric in ranking.metrics}
    return values, metrics


def view(session: Session, *, design_set_id: uuid.UUID) -> DesignSetView:
    """The whole design set: members, pair flags, additive totals, cost."""
    design_set = require_set(session, design_set_id)
    run = run_service.require_run(session, design_set.run_id)
    target = require_target(session, run.target_id)
    project = require_project(session, design_set.project_id)
    scheme = canonical_scheme(session, target.id)

    rows = session.exec(
        select(DesignSetMember, Variant)
        .where(col(DesignSetMember.design_set_id) == design_set.id)
        .join(Variant, col(DesignSetMember.variant_id) == col(Variant.id))
        .order_by(col(DesignSetMember.created_at))
    ).all()

    positions: set[int] = set()
    for _, variant in rows:
        if len(_positions_of(variant)) > 1:
            positions.update(_positions_of(variant))

    geometry = _measure_pairs(session, target, sorted(positions))
    values, metrics = _score_values(session, run.id)

    members: list[MemberView] = []
    all_flags: list[epistasis_domain.PairFlag] = []
    stacked_designs: list[epistasis_domain.StackedDesign] = []

    for member, variant in rows:
        component_codes = tuple(str(code) for code in (variant.mutations or [variant.code]))
        member_positions = _positions_of(variant)
        is_stacked = len(component_codes) > 1

        pairs: tuple[epistasis_domain.PairFlag, ...] = ()
        additive: tuple[epistasis_domain.AdditiveEstimate, ...] = ()

        if is_stacked and len(member_positions) == len(component_codes):
            design = epistasis_domain.StackedDesign(
                codes=component_codes,
                code=variant.code,
                positions=member_positions,
            )
            stacked_designs.append(design)
            pairs = epistasis_domain.pair_flags(
                design, geometry.separations, unknown_reason=geometry.unknown_reason
            )
            all_flags.extend(pairs)
            additive = tuple(
                epistasis_domain.additive(
                    metric=metric_id,
                    label=spec.label,
                    unit=spec.unit,
                    sign_convention=spec.sign_convention,
                    codes=component_codes,
                    values={
                        code: values[code][metric_id]
                        for code in component_codes
                        if metric_id in values.get(code, {})
                    },
                )
                for metric_id, spec in metrics.items()
            )

        members.append(
            MemberView(
                variant_id=variant.id,
                code=variant.code,
                # Specification §7: both forms are rendered, always. A stacked
                # design is each component in three-letter form, joined the same
                # way the code is, rather than the short code repeated.
                hgvs="/".join(hgvs_of(code) for code in component_codes),
                mutations=component_codes,
                sequence_positions=member_positions,
                is_stacked=is_stacked,
                included_via_override=member.included_via_override,
                override_reason=member.override_reason,
                pairs=pairs,
                additive=additive,
            )
        )

    basis = costing.CostBasis.from_settings(project.settings)
    cost = costing.total_of(
        basis,
        # Nothing is orderable until the wet-lab handoff turns these designs into
        # primers or gene fragments, so the set on its own has no lines to cost.
        # Saying so beats reporting a total of zero, which would read as free.
        [],
        budget_amount=design_set.budget_amount,
        budget_currency=design_set.budget_currency,
        no_lines_reason=(
            "This design set is empty, so there is nothing to cost."
            if not members
            else (
                f"{len(members)} design(s) selected. A cost needs orderable items: "
                "generate the wet-lab handoff to price the primers or gene fragments."
            )
        ),
    )

    versions = run_service.model_versions_of(session, run.id)

    return DesignSetView(
        design_set_id=design_set.id,
        project_id=design_set.project_id,
        run_id=run.id,
        name=design_set.name,
        note=design_set.note,
        scheme_label=scheme.label if scheme else "",
        members=tuple(members),
        warning=epistasis_domain.warning_for(stacked_designs, all_flags),
        cost=cost,
        geometry_manifest=geometry.manifest,
        geometry_note=geometry.note,
        is_demo=any(version.is_mock for version in versions.values()),
    )


def for_run(session: Session, run_id: uuid.UUID) -> list[DesignSet]:
    return list(
        session.exec(
            select(DesignSet)
            .where(col(DesignSet.run_id) == run_id)
            .order_by(col(DesignSet.created_at).desc())
        ).all()
    )
