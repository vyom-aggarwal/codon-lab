"""Solvent accessibility, burial class, and distance to the active site.

Everything here is computed from the coordinate set the user loaded, with every
parameter stated rather than defaulted. Four decisions are load-bearing, and all
four are recorded in the manifest that goes into the run's provenance record:

**The van der Waals radii set.** The hidden parameter in a solvent-accessibility
calculation is not the probe radius, it is the radii. On TEM-1 (PDB 1BTL),
switching from ProtOr to a uniform radius moves 8 of 263 residues across a
region boundary — while *improving* correlation with published DSSP output. A
test that only checks agreement with DSSP would wave that through, so
`tests/test_sasa.py` pins the radii set with a golden table as well.

**The normalisation table.** `domain/constants/max_asa` holds it, once, with its
DOI. Switching it to Miller 1987 moves 27 of those 263 residues.

**Whether ligands are present.** They are excluded from the reported number,
because a cofactor is not part of the protein — but a second pass includes them,
and a residue that becomes buried when the cofactor is there is flagged. Without
that flag the apo calculation makes active-site residues look solvent-exposed,
which is the most misleading thing this column can say.

**Which coordinates.** A dimer-interface residue is buried in the assembly and
exposed in the monomer, and that difference decides the mutation. The manifest
records what was actually loaded; it never claims a biological assembly it was
not given.

The calculation itself is Biotite's Shrake-Rupley (`biotite.structure.sasa`),
not an implementation of our own: an unvalidated radii table is precisely the
failure this module exists to avoid.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from importlib.metadata import version as package_version
from io import StringIO
from itertools import pairwise
from typing import Any, Literal

import biotite.structure as struc
import numpy as np
from biotite.structure.io.pdb import PDBFile

from catalyst.domain.aminoacid import three_to_one
from catalyst.domain.constants.max_asa import CITATION, CITATION_DOI, REFERENCE_SET, max_asa
from catalyst.domain.regions import RegionCutoffs
from catalyst.domain.schemes import (
    SchemeResolutionError,
    author_label_at,
    positions_by_label,
)
from catalyst.models.enums import Region

#: Recorded in every manifest: which implementation produced the numbers.
BIOTITE_VERSION = package_version("biotite")

#: Biotite's AtomArray is generic over its shape; nothing here depends on that.
AtomArray = struc.AtomArray[Any]

#: The radii sets biotite offers. Named as a type so a third value cannot be
#: introduced without the type checker noticing — this is the parameter that
#: silently moves residues across the core/surface boundary.
VdwRadii = Literal["ProtOr", "Single"]
PointDistribution = Literal["Fibonacci"]

#: Residue names that are solvent, not structure. Stripped before anything else.
WATER = frozenset({"HOH", "DOD", "WAT", "TIP", "TIP3", "SOL"})

#: An RSA drop of more than this when cofactors are included marks a residue as
#: buried by the cofactor rather than by the protein. The owner's threshold.
LIGAND_BURIAL_DROP = 0.10


class StructureFeatureError(RuntimeError):
    """Features could not be computed, with the reason and the way forward."""

    def __init__(self, message: str, remedy: str) -> None:
        super().__init__(message)
        self.remedy = remedy


@dataclass(frozen=True, slots=True)
class SasaParameters:
    """Stated, never defaulted to whatever the library happens to prefer."""

    probe_radius: float = 1.4
    point_number: int = 1000
    #: Tsai et al. 1999. See the module docstring for why this is pinned.
    vdw_radii: VdwRadii = "ProtOr"
    point_distribution: PointDistribution = "Fibonacci"

    def as_manifest(self) -> dict[str, Any]:
        return {
            "probe_radius_angstrom": self.probe_radius,
            "point_number": self.point_number,
            "vdw_radii": f"{self.vdw_radii} (Tsai et al. 1999)",
            "point_distribution": self.point_distribution,
            "atoms": "heavy atoms only; hydrogens, waters and monoatomic ions stripped",
            "implementation": f"biotite.structure.sasa {BIOTITE_VERSION} (Shrake-Rupley)",
        }


@dataclass(frozen=True, slots=True)
class ResidueFeature:
    """What geometry says about one residue. Any field may be None."""

    sequence_position: int
    residue: str
    #: How the structure file numbers this residue. Kept because the viewer
    #: addresses residues in author numbering and the canonical scheme may be a
    #: different one entirely — on the seeded lipase, sequence index 108 is
    #: author 108 and canonical Ser77. Converting between them by arithmetic in
    #: the viewer is exactly what ARCHITECTURE.md §9 forbids.
    author_label: str | None = None
    #: Absolute solvent accessible surface area, square angstroms.
    asa: float | None = None
    #: ASA over the published maximum for this residue type.
    rsa: float | None = None
    region: Region | None = None
    #: True when including cofactors drops this residue's RSA by more than
    #: LIGAND_BURIAL_DROP. It is exposed in the apo calculation and buried in
    #: reality, which is the opposite of what the number alone would suggest.
    buried_by_ligand: bool = False
    rsa_with_ligands: float | None = None
    #: Minimum non-hydrogen atom distance to the user-marked active site, in
    #: angstroms. None when no active site has been annotated.
    distance_to_active_site: float | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "author_label": self.author_label,
            "asa": self.asa,
            "rsa": self.rsa,
            "region": self.region.value if self.region else None,
            "buried_by_ligand": self.buried_by_ligand,
            "rsa_with_ligands": self.rsa_with_ligands,
            "distance_to_active_site": self.distance_to_active_site,
        }


@dataclass(frozen=True, slots=True)
class FeatureSet:
    residues: dict[int, ResidueFeature]
    #: Everything needed to reproduce these numbers. Goes into provenance whole.
    manifest: dict[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "manifest": self.manifest,
            "notes": list(self.notes),
            "positions": {
                str(position): feature.to_json()
                for position, feature in sorted(self.residues.items())
            },
        }


def _residue_key(chain_id: str, res_id: int, ins_code: str) -> tuple[str, str]:
    return chain_id, f"{res_id}{ins_code}".strip()


def _load(text: str) -> AtomArray:
    try:
        parsed = PDBFile.read(StringIO(text))
        atoms = parsed.get_structure(model=1, altloc="first")
    except Exception as error:  # biotite raises a variety of types
        raise StructureFeatureError(
            f"That structure could not be read for geometry: {error}",
            "Re-attach the structure, or use a different entry.",
        ) from error

    if atoms.array_length() == 0:
        raise StructureFeatureError(
            "The structure contains no atoms.",
            "Re-attach the structure, or use a different entry.",
        )

    # Hydrogens are excluded: ProtOr radii are heavy-atom radii, and DSSP — the
    # reference this calculation is validated against — is heavy-atom too.
    keep = (atoms.element != "H") & (atoms.element != "D")
    keep &= ~np.isin(atoms.res_name, list(WATER))
    return atoms[keep]


def _per_residue(atoms: AtomArray, per_atom: Any) -> dict[tuple[str, str], float]:
    totals = struc.apply_residue_wise(atoms, np.nan_to_num(per_atom, nan=0.0), np.sum)
    starts: list[int] = [int(index) for index in struc.get_residue_starts(atoms)]
    return {
        _residue_key(
            str(atoms.chain_id[index]),
            int(atoms.res_id[index]),
            str(atoms.ins_code[index]),
        ): float(value)
        for index, value in zip(starts, totals, strict=True)
    }


def compute(
    *,
    structure_text: str,
    chain_id: str,
    sequence: str,
    author_labels: Sequence[str | None],
    active_site_positions: Collection[int] = (),
    cutoffs: RegionCutoffs | None = None,
    parameters: SasaParameters | None = None,
    coordinate_source: str = "unknown",
) -> FeatureSet:
    """Derive per-residue features for one chain of a loaded structure.

    `author_labels` is the reconciled PDB-author label for each 1-based sequence
    index — the mapping the user confirmed in Phase 2. Features are keyed by
    sequence index on the way out, so nothing downstream has to convert between
    numbering schemes, which ARCHITECTURE.md §9 forbids doing implicitly.
    """
    cutoffs = cutoffs or RegionCutoffs()
    parameters = parameters or SasaParameters()
    notes: list[str] = []

    atoms = _load(structure_text)
    protein_mask = struc.filter_amino_acids(atoms)
    if not protein_mask.any():
        raise StructureFeatureError(
            "No amino acid residues were found in that structure.",
            "Check the file, or attach a different structure.",
        )

    protein = atoms[protein_mask]
    hetero_names = sorted(set(atoms.res_name[~protein_mask].tolist()))

    def solvent_accessibility(array: AtomArray, atom_filter: Any = None) -> Any:
        # Every argument is passed explicitly. A library default here is a
        # scientific parameter nobody chose.
        return struc.sasa(
            array,
            probe_radius=parameters.probe_radius,
            atom_filter=atom_filter,
            # Monoatomic ions are not part of the surface a solvent sees.
            ignore_ions=True,
            point_number=parameters.point_number,
            point_distr=parameters.point_distribution,
            vdw_radii=parameters.vdw_radii,
        )

    # The reported number: the protein by itself. A cofactor is not the protein.
    apo = _per_residue(protein, solvent_accessibility(protein))

    # The check: the same residues in the presence of everything else that was
    # in the file. Only the difference is used, and only to raise a flag.
    if hetero_names:
        holo_all = solvent_accessibility(atoms, atom_filter=protein_mask)
        holo = _per_residue(protein, holo_all[protein_mask])
    else:
        holo = dict(apo)

    chains = sorted(set(protein.chain_id.tolist()))
    if chain_id not in chains:
        raise StructureFeatureError(
            f"Chain {chain_id} is not in the loaded coordinates.",
            f"Chains present: {', '.join(chains)}.",
        )

    # Refuses a scheme that labels two residues the same way, rather than
    # silently keeping the last — see domain/schemes.
    try:
        label_to_position = positions_by_label(author_labels)
    except SchemeResolutionError as error:
        raise StructureFeatureError(str(error), error.remedy) from error

    active_keys: set[tuple[str, str]] = set()
    for position in active_site_positions:
        label = author_label_at(author_labels, position)
        if label is not None:
            active_keys.add((chain_id, label))
    distances = _active_site_distances(protein, active_keys)

    residues: dict[int, ResidueFeature] = {}
    unlisted: set[str] = set()

    for index in (int(start) for start in struc.get_residue_starts(protein)):
        key = _residue_key(
            str(protein.chain_id[index]),
            int(protein.res_id[index]),
            str(protein.ins_code[index]),
        )
        if key[0] != chain_id:
            continue
        sequence_position = label_to_position.get(key[1])
        if sequence_position is None:
            continue

        name = str(protein.res_name[index])
        maximum = max_asa(name)
        asa = apo.get(key)
        rsa = None if (maximum is None or asa is None) else round(asa / maximum, 4)
        holo_rsa = (
            None if (maximum is None or key not in holo) else round(holo[key] / maximum, 4)
        )
        if maximum is None:
            unlisted.add(name)

        residues[sequence_position] = ResidueFeature(
            sequence_position=sequence_position,
            residue=three_to_one(name),
            author_label=key[1],
            asa=None if asa is None else round(asa, 2),
            rsa=rsa,
            region=cutoffs.classify(rsa),
            buried_by_ligand=bool(
                rsa is not None and holo_rsa is not None and (rsa - holo_rsa) > LIGAND_BURIAL_DROP
            ),
            rsa_with_ligands=holo_rsa,
            distance_to_active_site=distances.get(key),
        )

    if unlisted:
        notes.append(
            f"{len(unlisted)} residue type(s) have no published maximum ASA "
            f"({', '.join(sorted(unlisted))}); their RSA and region read as unavailable."
        )
    if not active_keys:
        notes.append(
            "No catalytic or ligand-contacting residue is annotated on this target, "
            "so distance to the active site was not computed."
        )
    flagged = sum(1 for feature in residues.values() if feature.buried_by_ligand)
    if flagged:
        notes.append(
            f"{flagged} residue(s) are exposed in the protein alone but buried once "
            f"cofactors are included ({', '.join(hetero_names[:6])})."
        )

    assembly = (
        "monomer — one protein chain in the loaded coordinates"
        if len(chains) == 1
        else f"{len(chains)} protein chains as loaded ({', '.join(chains)})"
    )

    manifest: dict[str, Any] = {
        "reference_set": REFERENCE_SET,
        "reference_doi": CITATION_DOI,
        "reference_citation": CITATION,
        "cutoffs": cutoffs.as_manifest(),
        "sasa": parameters.as_manifest(),
        "coordinate_source": coordinate_source,
        "assembly": assembly,
        "chain_measured": chain_id,
        "chains_present": chains,
        "ligand_handling": (
            "excluded from the reported ASA; a second pass including them flags any "
            f"residue whose RSA drops by more than {LIGAND_BURIAL_DROP}"
        ),
        "hetero_residues_present": hetero_names,
        "residues_measured": len(residues),
        "sequence_length": len(sequence),
    }

    return FeatureSet(residues=residues, manifest=manifest, notes=tuple(notes))


def _active_site_distances(
    protein: AtomArray, active_keys: Collection[tuple[str, str]]
) -> dict[tuple[str, str], float]:
    """Minimum non-hydrogen atom distance from each residue to the active site.

    Not alpha-carbon distance. An arginine side chain reaches roughly 7 A past
    its own CA, so a CA measurement would report a residue as clear of the pocket
    while its side chain sits inside it.
    """
    if not active_keys:
        return {}

    keys = np.array(
        [
            _residue_key(str(chain), int(res_id), str(ins))
            for chain, res_id, ins in zip(
                protein.chain_id, protein.res_id, protein.ins_code, strict=True
            )
        ],
        dtype=object,
    )
    active_mask = np.array([tuple(key) in active_keys for key in keys], dtype=bool)
    if not active_mask.any():
        return {}

    active_coords = protein.coord[active_mask]
    distances: dict[tuple[str, str], float] = {}

    starts: list[int] = [int(start) for start in struc.get_residue_starts(protein)]
    starts.append(protein.array_length())
    for begin, end in pairwise(starts):
        key = _residue_key(
            str(protein.chain_id[begin]),
            int(protein.res_id[begin]),
            str(protein.ins_code[begin]),
        )
        deltas = protein.coord[begin:end, None, :] - active_coords[None, :, :]
        distances[key] = round(float(np.sqrt((deltas**2).sum(axis=-1)).min()), 1)
    return distances
