"""Features derived from geometry, not from a model.

A layer of its own, beside `providers/`, because these numbers are neither model
output nor a download. They come from a deterministic calculation over
coordinates the user loaded, and specification §2.2 applies to them exactly as it
applies to a model score: every one of them traces to the parameters that
produced it.

`providers/` needs weights and a citation for a model. This package needs a
citation for a *reference table* and a full parameter manifest. Both are recorded
per run; neither is allowed to be implicit.
"""

from codonlab.domain.regions import RegionCutoffs
from codonlab.features.structure import (
    FeatureSet,
    ResidueFeature,
    SasaParameters,
    StructureFeatureError,
    compute,
)

__all__ = [
    "FeatureSet",
    "RegionCutoffs",
    "ResidueFeature",
    "SasaParameters",
    "StructureFeatureError",
    "compute",
]
