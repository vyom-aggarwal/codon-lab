"""Burial class from relative solvent accessibility.

The cutoffs are a scientific decision, not a constant of nature, so they live in
a value object that travels with the run rather than as literals inside the
calculation. The defaults below were set by the project owner; a project may
override them, and whatever is in force when a run executes is copied into that
run's provenance record.

Pure: no coordinates, no library, no I/O. The accessibility calculation that
feeds this lives in `features/structure.py`, which is where the dependency on a
structure library belongs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from codonlab.models.enums import Region

#: Owner-set defaults. Engineering strategy differs by region — core packing
#: versus surface charge — so these decide what the product recommends.
DEFAULT_CORE_MAX = 0.25
DEFAULT_SURFACE_MIN = 0.40


class CutoffError(ValueError):
    """Cutoffs that do not describe an ordered partition of [0, 1]."""

    def __init__(self, message: str, remedy: str) -> None:
        super().__init__(message)
        self.remedy = remedy


@dataclass(frozen=True, slots=True)
class RegionCutoffs:
    """Where core stops and surface starts, in RSA."""

    core_max: float = DEFAULT_CORE_MAX
    surface_min: float = DEFAULT_SURFACE_MIN

    def __post_init__(self) -> None:
        if not 0.0 <= self.core_max <= self.surface_min <= 1.0:
            raise CutoffError(
                f"RSA cutoffs are out of order: core < {self.core_max}, "
                f"surface > {self.surface_min}.",
                "Core must not exceed surface, and both sit between 0 and 1.",
            )

    def classify(self, rsa: float | None) -> Region | None:
        """Null RSA classifies as nothing. It is not quietly called surface."""
        if rsa is None:
            return None
        if rsa < self.core_max:
            return Region.CORE
        if rsa > self.surface_min:
            return Region.SURFACE
        return Region.BOUNDARY

    def as_manifest(self) -> dict[str, Any]:
        return {
            "core_rsa_below": self.core_max,
            "surface_rsa_above": self.surface_min,
            "boundary_rsa_between": [self.core_max, self.surface_min],
        }

    @classmethod
    def from_settings(cls, settings: dict[str, Any] | None) -> RegionCutoffs:
        """Read a project's stored setting, falling back to the defaults.

        An absent setting means the defaults are in force — which is different
        from an invented value, because the defaults are recorded in the run's
        provenance exactly as an override would be.
        """
        stored = (settings or {}).get("rsa_cutoffs") or {}
        return cls(
            core_max=float(stored.get("core_max", DEFAULT_CORE_MAX)),
            surface_min=float(stored.get("surface_min", DEFAULT_SURFACE_MIN)),
        )

    def to_settings(self) -> dict[str, Any]:
        return {"rsa_cutoffs": {"core_max": self.core_max, "surface_min": self.surface_min}}
