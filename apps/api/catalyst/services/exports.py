"""What may be exported from a design set, and what may not — with the reason.

Specification §6 states one of this product's non-negotiables: a fabricating
provider "must ... watermark PDF exports and **refuse to generate primers**".
That refusal is built here, deliberately **before** the export path that would
need it. An honesty invariant added after the feature it constrains is an
invariant that was absent for however long the feature shipped without it.

Two things are refused, and both are refusals rather than degraded output:

**Primers, while any provider in the run fabricates.** A synthetic ΔΔG is
recognisable as synthetic on screen because it is badged. An oligo sequence
ordered off the back of one is not recognisable as anything — it is 30 bases of
DNA that costs real money and produces a real, meaningless result. Read from the
stored `ModelVersion.is_mock` rows of the run the set belongs to, never from the
`CATALYST_PROVIDERS` string, so a run recorded months ago still reports what
actually produced it (ARCHITECTURE.md §4).

**Primers, when the target has no coding DNA sequence.** A site-directed
mutagenesis primer anneals to the user's actual template. `Target` carries a
one-letter amino acid sequence and nothing else, so there is no template to
design against. Back-translating the protein would produce a plausible DNA
sequence that is *not* the plasmid on the bench, and primers against it would
simply fail to anneal — a fabrication that costs a synthesis order and a week.
This is stated as a refusal with a remedy, exactly as an unavailable model score
is, rather than silently emitting something orderable.

What is *not* refused is the design set itself: the codes, the pair flags, the
assumed-additive totals and their provenance are real records of what the run
said, and they export freely — watermarked when the run was synthetic.
"""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass
from typing import Any

from sqlmodel import Session

from catalyst.domain.epistasis import PAIR_PROXIMITY_ANGSTROM
from catalyst.models import ProvenanceEvent, ProvenanceEventKind, Target
from catalyst.services import design_sets as design_service
from catalyst.services import runs as run_service
from catalyst.services.targets import ServiceError, require_target

#: Rendered on any export produced from a run in which something fabricated.
#: Specification §6 requires PDF exports to be watermarked; the same sentence is
#: carried by every other format, because a CSV opened in Excel loses whatever
#: context the screen had.
DEMO_WATERMARK = (
    "DEMO DATA — NOT MODEL OUTPUT. Numbers in this file were produced by a "
    "provider that fabricates them. Not a prediction. Do not order from this file."
)


@dataclass(frozen=True, slots=True)
class Refusal:
    """Something this design set cannot produce, and what would fix it."""

    what: str
    reason: str
    remedy: str

    def to_json(self) -> dict[str, str]:
        return {"what": self.what, "reason": self.reason, "remedy": self.remedy}


@dataclass(frozen=True, slots=True)
class Preflight:
    """What the wet-lab handoff can and cannot emit for this set, before it tries."""

    design_set_id: uuid.UUID
    is_demo: bool
    watermark: str | None
    #: Formats that will produce a file.
    available: tuple[str, ...]
    #: Formats that will not, each with the reason and the remedy.
    refused: tuple[Refusal, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "design_set_id": str(self.design_set_id),
            "is_demo": self.is_demo,
            "watermark": self.watermark,
            "available": list(self.available),
            "refused": [refusal.to_json() for refusal in self.refused],
        }


def primer_refusals(session: Session, *, design_set_id: uuid.UUID) -> tuple[Refusal, ...]:
    """Every reason primers may not be generated for this set. Empty means they may.

    Returns *all* applicable reasons rather than the first. Fixing one and being
    handed the next is how a user concludes the feature is broken; being told
    both up front is how they decide whether it is worth doing at all.
    """
    design_set = design_service.require_set(session, design_set_id)
    run = run_service.require_run(session, design_set.run_id)
    target = require_target(session, run.target_id)

    refusals: list[Refusal] = []

    versions = run_service.model_versions_of(session, run.id)
    fabricating = sorted(
        version.name for version in versions.values() if version.is_mock
    )
    if fabricating:
        refusals.append(
            Refusal(
                what="primers",
                reason=(
                    "This run's numbers came from a provider that fabricates them "
                    f"({', '.join(fabricating)}). Specification §6 refuses primers "
                    "from synthetic scores: an ordered oligo carries no badge."
                ),
                remedy=(
                    "Re-run with CATALYST_PROVIDERS=real so the ranking comes from "
                    "a real model, then export from that run."
                ),
            )
        )

    if not _coding_sequence(target):
        refusals.append(
            Refusal(
                what="primers",
                reason=(
                    "No coding DNA sequence is attached to this target. A "
                    "mutagenesis primer anneals to the template actually on the "
                    "bench, and this target carries only its amino acid sequence."
                ),
                remedy=(
                    "Attach the construct's coding sequence to the target. It is "
                    "not back-translated from the protein: a codon-optimised guess "
                    "would not match the plasmid and the primers would not anneal."
                ),
            )
        )

    return tuple(refusals)


def _coding_sequence(target: Target) -> str | None:
    """The construct's DNA, if the user has attached one.

    Reads through an attribute that does not exist on `Target` yet, on purpose:
    the refusal above is the specified behaviour today, and this is the single
    place that changes when a coding sequence becomes attachable. Written as a
    lookup rather than a hard `return None` so that adding the column is a
    one-line change with a test already pointing at it.
    """
    return getattr(target, "coding_sequence", None)


def preflight(session: Session, *, design_set_id: uuid.UUID) -> Preflight:
    """What this set can export, asked before anything is generated."""
    view = design_service.view(session, design_set_id=design_set_id)
    refused = primer_refusals(session, design_set_id=design_set_id)

    available = ["design_set_csv"]
    if not refused:
        available.append("primers_csv")

    return Preflight(
        design_set_id=view.design_set_id,
        is_demo=view.is_demo,
        watermark=DEMO_WATERMARK if view.is_demo else None,
        available=tuple(available),
        refused=refused,
    )


def design_set_csv(session: Session, *, design_set_id: uuid.UUID) -> str:
    """The design set as an orderable-adjacent table. Carries no primer sequences.

    Every column is a record of what the run said. The pair-flag column uses the
    three-state vocabulary rather than a boolean, so "not measured" survives the
    trip into a spreadsheet — which is precisely where a blank would be read as
    "fine".
    """
    view = design_service.view(session, design_set_id=design_set_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")

    if view.is_demo:
        writer.writerow([DEMO_WATERMARK])

    writer.writerow([f"Design set: {view.name}"])
    writer.writerow([f"Run: {view.run_id}"])
    writer.writerow([f"Numbering scheme: {view.scheme_label or 'not confirmed'}"])
    writer.writerow(
        [
            f"Pair flag: {PAIR_PROXIMITY_ANGSTROM} A, "
            "minimum non-hydrogen atom separation"
        ]
    )
    if view.warning["stacked_designs"]:
        writer.writerow([str(view.warning["assumption"])])
    writer.writerow([])

    writer.writerow(
        [
            "code",
            "hgvs",
            "kind",
            "mutations",
            "constraint_override",
            "override_reason",
            "pairs_within_cutoff",
            "pairs_not_measured",
            "pair_detail",
            "assumed_additive",
        ]
    )

    for member in view.members:
        within = sum(1 for pair in member.pairs if pair.proximity.value == "within")
        unknown = sum(1 for pair in member.pairs if pair.proximity.value == "unknown")
        detail = "; ".join(
            f"{pair.a_code}+{pair.b_code}="
            + (
                f"{pair.separation_angstrom} A"
                if pair.separation_angstrom is not None
                else "not measured"
            )
            for pair in member.pairs
        )
        additive = "; ".join(
            f"{estimate.label}="
            + (
                "no total"
                if estimate.total is None
                else f"{estimate.total}{f' {estimate.unit}' if estimate.unit else ''}"
            )
            for estimate in member.additive
        )
        writer.writerow(
            [
                member.code,
                member.hgvs,
                "stacked" if member.is_stacked else "single",
                "/".join(member.mutations),
                "yes" if member.included_via_override else "no",
                member.override_reason or "",
                within if member.is_stacked else "",
                unknown if member.is_stacked else "",
                detail,
                additive,
            ]
        )

    _record_export(session, design_set_id=design_set_id, fmt="design_set_csv")
    return buffer.getvalue()


def primers_csv(session: Session, *, design_set_id: uuid.UUID) -> str:
    """Refuses, today, for every design set in this build.

    Kept as the single entry point so that the refusal is impossible to route
    around: anything wanting primers comes through here and gets the reasons.
    """
    refused = primer_refusals(session, design_set_id=design_set_id)
    if refused:
        raise ServiceError(
            "Primers cannot be generated for this design set. "
            + " ".join(refusal.reason for refusal in refused),
            " ".join(refusal.remedy for refusal in refused),
        )
    raise ServiceError(
        "Primer design is not implemented in this build.",
        "The refusal rules that guard it are in place; the designer itself lands "
        "with the wet-lab handoff.",
    )


def _record_export(session: Session, *, design_set_id: uuid.UUID, fmt: str) -> None:
    design_set = design_service.require_set(session, design_set_id)
    session.add(
        ProvenanceEvent(
            kind=ProvenanceEventKind.EXPORT_GENERATED,
            project_id=design_set.project_id,
            run_id=design_set.run_id,
            subject_type="design_set_export",
            subject_id=design_set.id,
            payload={"format": fmt},
        )
    )
    session.commit()
