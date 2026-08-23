"""ThermoMPNN — predicted change in folding free energy.

Vendored, not depended on: ThermoMPNN is not packaged. The source sits in
`_vendor/thermompnn` pinned to an exact commit, and the weights are fetched from
that same commit and hashed. ARCHITECTURE.md §14.3 has the decision.

Two things here need care.

**The position mapping.** ThermoMPNN indexes mutations by position within the
*parsed chain* — the residues actually present in the coordinates — which is not
the sequence index, and not the author numbering either. A structure with an
unresolved loop makes all three disagree. Every mutation is therefore checked
against the residue ThermoMPNN itself reports at that index before it is scored,
and a mismatch refuses rather than scores. This is the same class of check as the
ESM tokenizer alignment, and it exists for the same reason: a wrong-residue ΔΔG
looks entirely reasonable.

**The interval.** `BRIEF.md` §7 requires a ΔΔG to carry a confidence interval and
says a bare point estimate is not acceptable output. ThermoMPNN emits a point
estimate and no per-variant uncertainty. Rather than invent one — a fabricated
interval on a real number is worse than an absent one — this provider reports
`reports_interval=False` with the reason stated, and the conflict is flagged in
HANDOFF.md for the owner. Reporting a benchmark RMSE as though it were a
per-variant interval would be the same fabrication wearing a citation.
"""

from __future__ import annotations

import hashlib
import tempfile
import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from catalyst.domain.goal import Objective
from catalyst.domain.variants import VariantInput
from catalyst.models.enums import Modality
from catalyst.providers.base import (
    Capabilities,
    MetricSpec,
    PredictorUnavailableError,
    ScoreValue,
    TargetContext,
)

#: The pinned commit. Weights and source both come from here; changing it is a
#: new `ModelVersion`, never an edit to an existing one.
COMMIT = "2b04fd370e399911b1fa5848112cc9013f084110"
RAW = f"https://raw.githubusercontent.com/Kuhlman-Lab/ThermoMPNN/{COMMIT}"

WEIGHT_FILES = {
    "thermompnn": f"{RAW}/models/thermoMPNN_default.pt",
    # ThermoMPNN is a head on frozen ProteinMPNN embeddings, so the ProteinMPNN
    # weights are part of what produces the number and part of the hash.
    "proteinmpnn": f"{RAW}/vanilla_model_weights/v_48_020.pt",
}

#: ThermoMPNN's alphabet. Position indices are into the parsed chain.
ALPHABET = "ACDEFGHIKLMNPQRSTVWYX"

CITATION = (
    "Dieckhaus H, Brocidiacono M, Randolph NZ, Kuhlman B (2024). Transfer learning "
    "to leverage larger datasets for improved prediction of protein stability "
    "changes. PNAS 121(6):e2314853121. https://doi.org/10.1073/pnas.2314853121 — "
    f"weights and source pinned to commit {COMMIT[:12]}, MIT licence."
)

DDG = MetricSpec(
    id="ddg_kcal_per_mol",
    label="ThermoMPNN ΔΔG",
    unit="kcal/mol",
    # Specification §7 fixes this and it never changes.
    sign_convention="destabilizing positive",
    higher_is_better=False,
    # See the module docstring: a point estimate, reported as one.
    reports_interval=False,
)


def _torch_missing() -> str | None:
    try:
        import torch  # noqa: F401
    except ImportError as error:
        return (
            f"ThermoMPNN needs PyTorch, which is not installed ({error}). Install the "
            "optional model dependencies with `pip install -e '.[models]'` in apps/api, "
            "or leave this predictor out of CATALYST_PROVIDERS."
        )
    return None


def _cache_dir() -> Path:
    root = Path.home() / ".cache" / "catalyst" / "thermompnn" / COMMIT[:12]
    root.mkdir(parents=True, exist_ok=True)
    return root


@dataclass
class _Mutation:
    """What `TransferModel.forward` expects: a chain index and two residues."""

    position: int
    wildtype: str
    mutation: str


@dataclass
class _Loaded:
    model: Any
    weights_hash: str


@dataclass(eq=False)
class ThermoMPNNPredictor:
    """ThermoMPNN, loaded from a pinned commit and hashed."""

    id: str = "thermompnn"
    name: str = "ThermoMPNN"
    version: str = f"default@{COMMIT[:12]}"
    modality: Modality = Modality.STABILITY
    citation: str = CITATION
    is_mock: bool = False
    metrics: tuple[MetricSpec, ...] = (DDG,)
    requires: Capabilities = field(
        default_factory=lambda: Capabilities(
            # It reads structure embeddings; without coordinates there is nothing
            # to embed.
            needs_structure=True,
            needs_msa=False,
            max_length=None,
            needs_gpu=False,
        )
    )
    #: ARCHITECTURE.md §14.4: thermostability only. It predicts the free energy
    #: change of folding, and offering it for solvent tolerance would invite the
    #: reading that a stable protein is a solvent-tolerant one.
    objectives: frozenset[Objective] = field(
        default_factory=lambda: frozenset({Objective.THERMOSTABILITY})
    )

    _loaded: _Loaded | None = field(default=None, repr=False, compare=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    # ----------------------------------------------------------------- loading

    def available(self) -> str | None:
        missing = _torch_missing()
        if missing is not None:
            return missing
        try:
            self._weight_paths()
        except PredictorUnavailableError as error:
            return str(error)
        return None

    def _weight_paths(self) -> dict[str, Path]:
        """Fetch the pinned weights once, into a local cache."""
        import urllib.error
        import urllib.request

        paths: dict[str, Path] = {}
        for name, url in WEIGHT_FILES.items():
            local = _cache_dir() / f"{name}.pt"
            if not local.exists():
                try:
                    with urllib.request.urlopen(url, timeout=300) as response:
                        local.write_bytes(response.read())
                except (OSError, urllib.error.URLError) as error:
                    local.unlink(missing_ok=True)
                    raise PredictorUnavailableError(
                        f"The ThermoMPNN weights ({name}) could not be fetched from the "
                        f"pinned commit ({error}). Pre-fetch them where the worker can "
                        "reach them, or leave this predictor out of CATALYST_PROVIDERS."
                    ) from error
            paths[name] = local
        return paths

    @property
    def weights_hash(self) -> str:
        """SHA-256 over both checkpoints, in a fixed order.

        Both, because ThermoMPNN is a head on frozen ProteinMPNN embeddings: the
        ProteinMPNN weights are part of what produces the number. A hash of the
        bytes actually loaded, never a placeholder.
        """
        loaded = self._loaded
        if loaded is not None:
            return loaded.weights_hash
        return self._hash(self._weight_paths())

    @staticmethod
    def _hash(paths: dict[str, Path]) -> str:
        digest = hashlib.sha256()
        for name in sorted(paths):
            digest.update(name.encode("utf-8"))
            digest.update(paths[name].read_bytes())
        return f"sha256:{digest.hexdigest()}"

    def _load(self) -> _Loaded:
        with self._lock:
            if self._loaded is not None:
                return self._loaded

            missing = _torch_missing()
            if missing is not None:
                raise PredictorUnavailableError(missing)

            import torch

            paths = self._weight_paths()
            weights_hash = self._hash(paths)

            # The upstream model reads its ProteinMPNN weights from a directory
            # named by config. Point it at the cache rather than editing the
            # vendored source.
            weights_dir = _cache_dir() / "vanilla_model_weights"
            weights_dir.mkdir(exist_ok=True)
            target = weights_dir / "v_48_020.pt"
            if not target.exists():
                target.write_bytes(paths["proteinmpnn"].read_bytes())

            config = _inference_config()

            from catalyst.providers._vendor.thermompnn.transfer_model import TransferModel

            model = TransferModel(config)  # type: ignore[no-untyped-call]
            checkpoint = torch.load(paths["thermompnn"], map_location="cpu", weights_only=False)
            state = checkpoint.get("state_dict", checkpoint)
            # A Lightning checkpoint prefixes every key with `model.`; the module
            # underneath is a plain TransferModel. Stripping the prefix is what
            # lets this load without pulling in a training framework.
            stripped = {
                key.removeprefix("model."): value
                for key, value in state.items()
                if key.startswith("model.")
            }
            missing_keys, _unexpected = model.load_state_dict(stripped, strict=False)
            if missing_keys:
                raise PredictorUnavailableError(
                    "The ThermoMPNN checkpoint does not fit the vendored model "
                    f"({len(missing_keys)} parameters missing, e.g. {missing_keys[:3]}). "
                    "Refusing to score with a partially loaded model."
                )
            model.eval()

            self._loaded = _Loaded(model=model, weights_hash=weights_hash)
            return self._loaded

    # ----------------------------------------------------------------- scoring

    def score(
        self, variants: Sequence[VariantInput], ctx: TargetContext
    ) -> list[ScoreValue]:
        if not variants:
            return []
        if ctx.structure is None or ctx.structure_text is None:
            raise PredictorUnavailableError(
                "ThermoMPNN needs the structure's coordinates, and this run did not "
                "provide them."
            )

        import torch

        loaded = self._load()
        from catalyst.providers._vendor.thermompnn.protein_mpnn_utils import alt_parse_PDB

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "target.pdb"
            path.write_text(ctx.structure_text, encoding="utf-8")
            chain = ctx.structure.chain
            parsed = alt_parse_PDB(  # type: ignore[no-untyped-call]
                str(path), input_chain_list=[chain] if chain else None
            )

        if not parsed:
            raise PredictorUnavailableError(
                "ThermoMPNN could not parse the structure for this target."
            )

        chain_key = f"seq_chain_{chain}" if chain else None
        chain_sequence = (
            parsed[0].get(chain_key) if chain_key and chain_key in parsed[0] else parsed[0]["seq"]
        )

        # Chain index for each sequence position, checked residue by residue.
        # ThermoMPNN indexes into the *parsed* chain, which is neither the
        # sequence index nor the author numbering when a loop is unresolved.
        mutations: list[_Mutation] = []
        kept: list[VariantInput] = []
        for variant in variants:
            index = self._chain_index(variant, chain_sequence, ctx)
            if index is None:
                continue
            observed = chain_sequence[index]
            if observed != variant.wild:
                raise PredictorUnavailableError(
                    f"Residue mismatch for {variant.code}: the structure has {observed!r} "
                    f"at chain index {index} where the variant expects {variant.wild!r}. "
                    "Refusing to score rather than scoring the wrong residue."
                )
            if variant.mutant not in ALPHABET:
                continue
            mutations.append(
                _Mutation(position=index, wildtype=variant.wild, mutation=variant.mutant)
            )
            kept.append(variant)

        if not mutations:
            return []

        with torch.no_grad():
            # Upstream returns (predictions, None); each prediction is a dict
            # carrying a one-element ddG tensor.
            predictions, _ = loaded.model(parsed, mutations)

        results: list[ScoreValue] = []
        for variant, prediction in zip(kept, predictions, strict=True):
            if prediction is None:
                continue
            # ThermoMPNN reports destabilizing-positive, the same convention
            # specification §7 fixes — established from upstream's own
            # `retrieve_best_mutants`, which selects the *minimum* predicted ddG
            # as the best substitution at a position. No sign flip is applied,
            # and none may be added without evidence of the same kind.
            value = float(prediction["ddG"].detach().reshape(-1)[0])
            results.append(
                ScoreValue(
                    variant_code=variant.code,
                    metric=DDG.id,
                    value=round(value, 4),
                    # No per-variant uncertainty exists. See the module docstring.
                    uncertainty=None,
                    ci_low=None,
                    ci_high=None,
                    detail={"commit": COMMIT, "chain": ctx.structure.chain},
                )
            )
        return results

    @staticmethod
    def _chain_index(
        variant: VariantInput, chain_sequence: str, ctx: TargetContext
    ) -> int | None:
        """Where this variant sits in the parsed chain.

        The parsed chain covers the residues present in the coordinates. When the
        structure covers the sequence completely the two indices coincide; when it
        does not, this returns None rather than an approximation, and the caller
        leaves the cell empty.
        """
        index = variant.sequence_position - 1
        if 0 <= index < len(chain_sequence) and len(chain_sequence) == len(ctx.sequence):
            return index
        return None


class _Namespace:
    """Attribute access plus `in`, which is what the vendored model expects.

    Upstream reads its settings off an OmegaConf node and tests membership with
    `'lightattn' in cfg.model`. A plain dataclass does not support that. This is
    the smallest object that satisfies both, and it keeps the vendored source
    unedited — which is what makes the commit pin auditable.
    """

    def __init__(self, **values: Any) -> None:
        self.__dict__.update(values)

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and key in self.__dict__


def _inference_config() -> _Namespace:
    """The settings the upstream model reads at inference time.

    Taken from ThermoMPNN's own `analysis/custom_inference.py` at the pinned
    commit, so this is the configuration the published weights were trained and
    released under — not one chosen here.
    """
    return _Namespace(
        platform=_Namespace(thermompnn_dir=str(_cache_dir())),
        model=_Namespace(
            hidden_dims=[64, 32],
            subtract_mut=True,
            num_final_layers=2,
            freeze_weights=True,
            load_pretrained=True,
            lightattn=True,
        ),
    )


#: The registered instance. Constructing it loads nothing.
THERMOMPNN = ThermoMPNNPredictor()
