"""ESM-2: the alignment, the labelling, and what it refuses to answer.

Hermetic by default. The real checkpoint is 2.6 GB and one forward pass is
several seconds, so the tests that load it are opt-in:

    CATALYST_TEST_REAL_MODELS=1 pytest tests/test_esm.py

The alignment tests below are the important ones, and they run without the model.
They exist because a real off-by-one shipped in this file during development:
`_token_offset` returned the *index* of the first residue and the caller used it
as an *additive offset*, so every substitution was scored against its neighbour.
Nothing looked wrong — the numbers were plausible, ordered, and completely
untethered from the residues they claimed to be about.
"""

from __future__ import annotations

import os
import uuid

import pytest

from catalyst.domain.goal import Objective
from catalyst.providers.base import PredictorUnavailableError, TargetContext
from catalyst.providers.esm import CHECKPOINT, ESM2_650M, MAX_RESIDUES, ESMScorer

REAL = os.environ.get("CATALYST_TEST_REAL_MODELS") == "1"
requires_model = pytest.mark.skipif(
    not REAL, reason="needs the 2.6 GB ESM-2 checkpoint; set CATALYST_TEST_REAL_MODELS=1"
)


class StubTokenizer:
    """A tokenizer that lays a sequence out one token per residue.

    `prefix` is what it puts before the first residue — the real ESM tokenizer
    uses a start token, but the alignment must be established rather than
    assumed, so both layouts are exercised.
    """

    def __init__(self, prefix: list[str], suffix: list[str] | None = None) -> None:
        self.prefix = prefix
        self.suffix = suffix or []

    def tokens_for(self, sequence: str) -> list[str]:
        return [*self.prefix, *sequence, *self.suffix]

    def convert_ids_to_tokens(self, identifier: int) -> str:
        return self._table[identifier]

    def encode(self, sequence: str) -> list[int]:
        self._table = dict(enumerate(self.tokens_for(sequence)))
        return list(range(len(self._table)))


def ids_for(tokenizer: StubTokenizer, sequence: str) -> list[list[int]]:
    return [tokenizer.encode(sequence)]


SEQ = "MKFVKRRIIALVTILMLSVTS"


def test_the_first_residue_is_found_after_a_start_token() -> None:
    tokenizer = StubTokenizer(prefix=["<cls>"], suffix=["<eos>"])
    start = ESMScorer._residue_token_start(tokenizer, SEQ, ids_for(tokenizer, SEQ))
    assert start == 1


def test_a_tokenizer_with_no_start_token_is_handled() -> None:
    """The alignment is established, not hard-coded to 1."""
    tokenizer = StubTokenizer(prefix=[])
    start = ESMScorer._residue_token_start(tokenizer, SEQ, ids_for(tokenizer, SEQ))
    assert start == 0


def test_the_start_is_an_index_not_an_offset() -> None:
    """The exact bug that shipped.

    With a start token the first residue sits at index 1, so sequence position
    `p` is at index `start + p - 1` — not `p + start`, which lands one residue
    late and scores every substitution against its neighbour.
    """
    tokenizer = StubTokenizer(prefix=["<cls>"], suffix=["<eos>"])
    ids = ids_for(tokenizer, SEQ)
    start = ESMScorer._residue_token_start(tokenizer, SEQ, ids)

    for position in (1, 2, 10, len(SEQ)):
        index = start + position - 1
        assert tokenizer.convert_ids_to_tokens(ids[0][index]) == SEQ[position - 1]

    # And the formula that was wrong stays wrong, so this test would fail if the
    # implementation drifted back to it.
    wrong = start + 1
    assert tokenizer.convert_ids_to_tokens(ids[0][wrong]) != SEQ[0]


def test_a_tokenizer_that_does_not_lay_out_one_token_per_residue_is_refused() -> None:
    """Refusing beats guessing at the alignment."""

    class Merging(StubTokenizer):
        def tokens_for(self, sequence: str) -> list[str]:
            # Drops a residue in the middle, as a BPE-style tokenizer would.
            return ["<cls>", *sequence[:5], *sequence[6:], "<eos>"]

    tokenizer = Merging(prefix=["<cls>"])
    with pytest.raises(PredictorUnavailableError) as error:
        ESMScorer._residue_token_start(tokenizer, SEQ, ids_for(tokenizer, SEQ))
    assert "one token per" in str(error.value)


def test_the_alignment_is_checked_across_the_sequence_not_just_the_first_residue() -> None:
    """A single-residue check passes for a tokenizer that diverges later."""

    class DivergesLate(StubTokenizer):
        def tokens_for(self, sequence: str) -> list[str]:
            return ["<cls>", sequence[0], *("X" * (len(sequence) - 1)), "<eos>"]

    tokenizer = DivergesLate(prefix=["<cls>"])
    with pytest.raises(PredictorUnavailableError):
        ESMScorer._residue_token_start(tokenizer, SEQ, ids_for(tokenizer, SEQ))


# --------------------------------------------------------------------------- #
# What it says about itself
# --------------------------------------------------------------------------- #


def test_it_does_not_claim_to_be_a_mock() -> None:
    assert ESM2_650M.is_mock is False


def test_the_metric_is_labelled_a_prior_not_evidence() -> None:
    """ARCHITECTURE.md §14.4. The label travels with the provider so a screen
    cannot quietly restate it as evidence for the objective."""
    metric = ESM2_650M.metrics[0]
    assert "plausibilit" in metric.sign_convention.lower()
    assert "not evidence" in metric.sign_convention.lower()
    # Never "confidence" — §13.
    assert "confidence" not in metric.label.lower()
    assert "confidence" not in metric.sign_convention.lower()


def test_a_masked_marginal_reports_no_interval_rather_than_an_invented_one() -> None:
    assert ESM2_650M.metrics[0].reports_interval is False


def test_it_is_not_offered_for_specificity_or_solvent_tolerance() -> None:
    """The owner's decision, ARCHITECTURE.md §14.4: an evolutionary prior cannot
    distinguish substrate selectivity, and nothing in the training distribution
    was selected for tolerance of a non-natural solvent."""
    assert Objective.SPECIFICITY not in ESM2_650M.objectives
    assert Objective.SOLVENT_TOLERANCE not in ESM2_650M.objectives


def test_it_is_offered_for_exactly_the_five_agreed_objectives() -> None:
    assert ESM2_650M.objectives == frozenset(
        {
            Objective.THERMOSTABILITY,
            Objective.ACTIVITY,
            Objective.EXPRESSION,
            Objective.SOLUBILITY,
            Objective.BINDING_AFFINITY,
        }
    )


def test_it_did_not_inherit_the_mocks_objectives() -> None:
    from catalyst.providers.mock import MOCK_FITNESS

    assert ESM2_650M.objectives != MOCK_FITNESS.objectives


def test_a_sequence_longer_than_the_context_is_refused_not_truncated() -> None:
    context = TargetContext(
        target_id=uuid.uuid4(),
        sequence="A" * (MAX_RESIDUES + 1),
        scheme_label="test",
    )
    reason = ESM2_650M.requires.unmet(context)
    assert reason is not None
    assert str(MAX_RESIDUES) in reason


def test_the_citation_names_the_model_and_the_scoring_scheme() -> None:
    assert "Lin" in ESM2_650M.citation
    assert "Meier" in ESM2_650M.citation


# --------------------------------------------------------------------------- #
# With the real checkpoint
# --------------------------------------------------------------------------- #


@requires_model
def test_the_weights_hash_is_of_the_weights_actually_loaded() -> None:
    """Not a placeholder. A made-up hash here is indistinguishable from a real
    one in the provenance trail, which turns traceability into a lie."""
    import hashlib
    from pathlib import Path

    assert ESM2_650M.available() is None
    reported = ESM2_650M.weights_hash
    assert reported.startswith("sha256:")

    files = ESM2_650M._checkpoint_files()
    digest = hashlib.sha256()
    for path in files:
        digest.update(Path(path).name.encode())
        digest.update(Path(path).read_bytes())
    assert reported == f"sha256:{digest.hexdigest()}"


@requires_model
def test_scores_match_an_independent_masked_marginal_computation() -> None:
    """The check that caught the off-by-one: compare against the model directly."""
    import torch
    from transformers import AutoModelForMaskedLM, AutoTokenizer

    from catalyst.domain.variants import enumerate_single_substitutions

    sequence = "MKFVKRRIIALVTILMLSVTSLFALQPSAKAAEHNPVVMVHGIGG"
    labels: list[str | None] = [str(index + 1) for index in range(len(sequence))]
    candidates = [
        candidate
        for candidate in enumerate_single_substitutions(sequence, labels).candidates
        if candidate.sequence_position in (1, 12, len(sequence))
    ]
    context = TargetContext(target_id=uuid.uuid4(), sequence=sequence, scheme_label="test")
    scored = {value.variant_code: value.value for value in ESM2_650M.score(candidates, context)}

    tokenizer = AutoTokenizer.from_pretrained(CHECKPOINT)
    model = AutoModelForMaskedLM.from_pretrained(CHECKPOINT)
    model.eval()
    encoded = tokenizer(sequence, return_tensors="pt")
    ids = encoded["input_ids"]
    start = ESM2_650M._residue_token_start(tokenizer, sequence, ids)

    for position in (1, 12, len(sequence)):
        index = start + position - 1
        masked = ids.clone()
        masked[0, index] = tokenizer.mask_token_id
        with torch.no_grad():
            logits = model(input_ids=masked, attention_mask=encoded["attention_mask"]).logits
        log_probs = torch.log_softmax(logits[0, index], dim=-1)
        wild = sequence[position - 1]
        for mutant in ("A", "W", "G"):
            if mutant == wild:
                continue
            expected = round(
                float(
                    log_probs[tokenizer.convert_tokens_to_ids(mutant)]
                    - log_probs[tokenizer.convert_tokens_to_ids(wild)]
                ),
                4,
            )
            assert scored[f"{wild}{position}{mutant}"] == expected
