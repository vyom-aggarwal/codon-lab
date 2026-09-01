"""ESM-2, scored by masked marginals.

A real model with real weights. Everything in here that could make a number mean
something different is pinned and recorded: the checkpoint, the scoring scheme,
and a `weights_hash` computed from the bytes actually loaded.

**The scoring scheme.** Masked marginals, as `BRIEF.md` §6 specifies: for each
position, mask it, run a forward pass, and score a substitution as
`log P(mutant | context) - log P(wild-type | context)`. That is one forward pass
per position — on this machine, 3.4s each, so 12 minutes for a 212-residue target
and 31 for a 550-residue one. The cheaper alternative (wt-marginal, a single pass
over the unmasked sequence) is a different and generally weaker scheme, and is
deliberately not offered: see ARCHITECTURE.md §14.2.

The cost does not recur. `services/runs._reuse_scores` keys on the model version,
the target, the context and the candidate set, so a scored target is reused across
goals and projects.

**What this metric is, and is not.** A log-likelihood ratio from a protein
language model is an *evolutionary-plausibility prior*: it says how much the model
expects to see this residue here, given everything it learned from natural
sequences. It is not evidence about any particular objective. The column is
labelled that way, and the label lives on `MetricSpec` so it travels with the
provider rather than being restated by a screen.

That is also why this predictor is not offered for specificity or solvent
tolerance — ARCHITECTURE.md §14.4 has the reasoning.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codonlab.domain.goal import Objective
from codonlab.domain.variants import VariantInput
from codonlab.models.enums import Modality
from codonlab.providers.base import (
    Capabilities,
    MetricSpec,
    PredictorUnavailableError,
    ScoreValue,
    TargetContext,
)

#: The checkpoint, pinned. Changing it is a different `ModelVersion`, never an
#: edit to an existing one — see ARCHITECTURE.md §14.1.
CHECKPOINT = "facebook/esm2_t33_650M_UR50D"

#: ESM-2 carries learned positional embeddings up to 1024 tokens, two of which
#: are the start and end tokens. A longer target is refused with that stated,
#: rather than silently truncated — a truncated protein is a different protein.
MAX_RESIDUES = 1022

CITATION = (
    "Lin Z, Akin H, Rao R, Hie B, Zhu Z, Lu W, et al. (2023). Evolutionary-scale "
    "prediction of atomic-level protein structure with a language model. Science "
    "379(6637):1123-1130. https://doi.org/10.1126/science.ade2574 — scoring scheme "
    "from Meier J, Rao R, Verkuil R, Liu J, Sercu T, Rives A (2021), Language models "
    "enable zero-shot prediction of the effects of mutations on protein function, "
    "NeurIPS 34."
)

#: An evolutionary-plausibility prior, named as one. Higher is more plausible.
LLR = MetricSpec(
    id="fitness_llr",
    label="ESM-2 log-likelihood ratio",
    unit=None,
    sign_convention=(
        "mutant minus wild type, natural log; higher is more evolutionarily "
        "plausible. An evolutionary-plausibility prior, not evidence for the "
        "objective in question."
    ),
    higher_is_better=True,
    # A masked marginal is a point estimate by construction. Reported without an
    # interval rather than with an invented one.
    reports_interval=False,
)


def _torch_missing() -> str | None:
    """Whether the runtime this predictor needs is installed."""
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError as error:
        return (
            f"ESM-2 needs PyTorch and transformers, which are not installed ({error}). "
            "Install the optional model dependencies with `pip install -e '.[models]'` "
            "in apps/api, or leave this predictor out of CODONLAB_PROVIDERS."
        )
    return None


@dataclass
class _Loaded:
    """The model, its tokenizer, and the hash of the bytes behind them."""

    model: Any
    tokenizer: Any
    weights_hash: str


@dataclass(eq=False)
class ESMScorer:
    """ESM-2 650M, masked-marginal scoring.

    Not frozen, because the loaded model is memoised on the instance. Its
    *identity* is still immutable — id, version, checkpoint and the weights hash
    are never reassigned once resolved.
    """

    id: str = "esm2_t33_650m"
    name: str = "ESM-2 650M"
    version: str = "t33_650M_UR50D"
    modality: Modality = Modality.FITNESS
    citation: str = CITATION
    is_mock: bool = False
    metrics: tuple[MetricSpec, ...] = (LLR,)
    requires: Capabilities = field(
        default_factory=lambda: Capabilities(
            needs_structure=False,
            needs_msa=False,
            max_length=MAX_RESIDUES,
            # It runs on CPU. Slowly, but it runs, and claiming otherwise would
            # make the pipeline refuse a predictor that works.
            needs_gpu=False,
        )
    )
    #: ARCHITECTURE.md §14.4. Deliberately excludes specificity and solvent
    #: tolerance: an evolutionary prior cannot distinguish substrate selectivity,
    #: and nothing in the training distribution was selected for tolerance of a
    #: non-natural solvent.
    objectives: frozenset[Objective] = field(
        default_factory=lambda: frozenset(
            {
                Objective.THERMOSTABILITY,
                Objective.ACTIVITY,
                Objective.EXPRESSION,
                Objective.SOLUBILITY,
                Objective.BINDING_AFFINITY,
            }
        )
    )

    _loaded: _Loaded | None = field(default=None, repr=False, compare=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    # ----------------------------------------------------------------- loading

    def available(self) -> str | None:
        missing = _torch_missing()
        if missing is not None:
            return missing
        try:
            self._checkpoint_files()
        except PredictorUnavailableError as error:
            return str(error)
        return None

    def _checkpoint_files(self) -> list[Path]:
        """Resolve the checkpoint locally, downloading it once if needed.

        Returns the weight files themselves. Hashing these is what makes
        `weights_hash` a statement about the bytes that get loaded rather than a
        label someone typed.
        """
        try:
            from huggingface_hub import snapshot_download
        except ImportError as error:  # pragma: no cover - covered by available()
            raise PredictorUnavailableError(str(error)) from error

        try:
            local = snapshot_download(
                CHECKPOINT,
                allow_patterns=["*.json", "*.txt", "*.safetensors", "*.bin"],
            )
        except Exception as error:
            raise PredictorUnavailableError(
                f"The ESM-2 checkpoint {CHECKPOINT} is not available locally and could "
                f"not be downloaded ({type(error).__name__}: {error}). It is roughly "
                "2.6 GB. Pre-fetch it where the worker can reach it, or leave this "
                "predictor out of CODONLAB_PROVIDERS."
            ) from error

        root = Path(local)
        weights = sorted(
            [*root.glob("*.safetensors"), *root.glob("*.bin")],
            key=lambda path: path.name,
        )
        if not weights:
            raise PredictorUnavailableError(
                f"The ESM-2 checkpoint at {root} contains no weight file."
            )
        return weights

    @property
    def weights_hash(self) -> str:
        """SHA-256 over the checkpoint's weight files, in a fixed order.

        A hash of the weights actually loaded. Never a placeholder: a made-up
        hash here would be indistinguishable from a real one in the provenance
        trail, which turns the whole traceability claim into a lie.

        Resolved lazily and memoised — computing it downloads the checkpoint on
        first use, so it is deliberately not done at import time.
        """
        loaded = self._loaded
        if loaded is not None:
            return loaded.weights_hash
        return self._hash_files(self._checkpoint_files())

    @staticmethod
    def _hash_files(paths: Sequence[Path]) -> str:
        digest = hashlib.sha256()
        for path in paths:
            # The name is part of the hash: a checkpoint sharded differently is a
            # different checkpoint even if the concatenated bytes match.
            digest.update(path.name.encode("utf-8"))
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(chunk)
        return f"sha256:{digest.hexdigest()}"

    def _load(self) -> _Loaded:
        with self._lock:
            if self._loaded is not None:
                return self._loaded

            missing = _torch_missing()
            if missing is not None:
                raise PredictorUnavailableError(missing)

            import torch
            from transformers import AutoModelForMaskedLM, AutoTokenizer

            files = self._checkpoint_files()
            weights_hash = self._hash_files(files)

            tokenizer = AutoTokenizer.from_pretrained(CHECKPOINT)
            model = AutoModelForMaskedLM.from_pretrained(CHECKPOINT)
            model.eval()
            torch.set_grad_enabled(False)

            self._loaded = _Loaded(model=model, tokenizer=tokenizer, weights_hash=weights_hash)
            return self._loaded

    # ----------------------------------------------------------------- scoring

    def score(
        self, variants: Sequence[VariantInput], ctx: TargetContext
    ) -> list[ScoreValue]:
        """Masked-marginal log-odds for every requested substitution.

        One forward pass per *position*, not per variant: a single masked pass
        yields the distribution over all twenty residues at that position, so all
        19 substitutions there are scored together.
        """
        if not variants:
            return []

        import torch

        loaded = self._load()
        tokenizer = loaded.tokenizer
        model = loaded.model

        sequence = ctx.sequence
        if len(sequence) > MAX_RESIDUES:
            raise PredictorUnavailableError(
                f"ESM-2 accepts at most {MAX_RESIDUES} residues and this target is "
                f"{len(sequence)}. It is refused rather than truncated: a truncated "
                "protein is a different protein."
            )

        encoded = tokenizer(sequence, return_tensors="pt")
        input_ids = encoded["input_ids"]
        # Token index holding sequence position 1. Verified against the actual
        # tokens rather than assumed, because an off-by-one here scores every
        # substitution against its neighbour and produces numbers that look
        # entirely reasonable.
        start = self._residue_token_start(tokenizer, sequence, input_ids)

        by_position: dict[int, list[VariantInput]] = {}
        for variant in variants:
            by_position.setdefault(variant.sequence_position, []).append(variant)

        results: list[ScoreValue] = []
        mask_id = tokenizer.mask_token_id

        for position in sorted(by_position):
            index = start + position - 1
            if not 0 <= index < input_ids.shape[1]:
                continue
            # The residue about to be masked must be the one the variant names.
            # Cheap, and it turns a silent off-by-one into a loud failure.
            token = tokenizer.convert_ids_to_tokens(int(input_ids[0, index]))
            expected = sequence[position - 1]
            if token != expected:
                raise PredictorUnavailableError(
                    f"Token/sequence mismatch at position {position}: the tokenizer "
                    f"has {token!r} where the sequence has {expected!r}. Refusing to "
                    "score rather than score the wrong residue."
                )

            masked = input_ids.clone()
            masked[0, index] = mask_id
            logits = model(input_ids=masked, attention_mask=encoded["attention_mask"]).logits
            log_probs = torch.log_softmax(logits[0, index], dim=-1)

            for variant in by_position[position]:
                wild_id = tokenizer.convert_tokens_to_ids(variant.wild)
                mutant_id = tokenizer.convert_tokens_to_ids(variant.mutant)
                if wild_id is None or mutant_id is None:
                    continue
                value = float(log_probs[mutant_id] - log_probs[wild_id])
                results.append(
                    ScoreValue(
                        variant_code=variant.code,
                        metric=LLR.id,
                        value=round(value, 4),
                        uncertainty=None,
                        ci_low=None,
                        ci_high=None,
                        detail={
                            "scheme": "masked-marginal",
                            "checkpoint": CHECKPOINT,
                        },
                    )
                )

        return results

    @staticmethod
    def _residue_token_start(tokenizer: Any, sequence: str, input_ids: Any) -> int:
        """The token index holding sequence position 1.

        ESM tokenizers prepend a start token, so this is normally 1 — but it is
        established by comparing tokens against the sequence at several positions
        rather than assumed, and it is the *index of the first residue*, not an
        additive offset. Conflating those two is an off-by-one that scores every
        substitution against its neighbour while producing entirely plausible
        numbers, which is the failure this codebase spends the most effort
        refusing.
        """
        ids = input_ids[0]
        # Sample across the sequence: matching only the first residue would be
        # satisfied by a tokenizer that merged or inserted anything later on.
        step = max(1, len(sequence) // 8)
        probes = list(range(0, len(sequence), step))

        for start in (1, 0):
            if start + len(sequence) > len(ids):
                continue
            if all(
                tokenizer.convert_ids_to_tokens(int(ids[start + offset])) == sequence[offset]
                for offset in probes
            ):
                return start

        raise PredictorUnavailableError(
            "The ESM-2 tokenizer did not lay the sequence out as one token per "
            "residue, so sequence positions cannot be mapped to tokens safely. "
            "Refusing to score rather than guessing at the alignment."
        )


#: The registered instance. Constructing it loads nothing.
ESM2_650M = ESMScorer()
