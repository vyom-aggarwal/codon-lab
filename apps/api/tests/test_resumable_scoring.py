"""Chunking, and the guarantee it exists to provide.

The claim being tested is narrow and worth stating exactly: **a scoring run that
is killed part-way through leaves usable work behind, and a later run under the
same input hash does not recompute it.**

That is what makes a 550-residue target runnable. It needs roughly 142 minutes
and `JOB_TIMEOUT_SECONDS` is 3600, so before this every attempt computed an
hour of numbers, persisted none of them, and started again from nothing.

Chunk *boundaries* are tested here hermetically. Chunk *persistence* — that a
commit really did survive — is asserted in `scripts/verify_gates.py` against
real Postgres, because a rollback that leaves nothing behind is exactly the
failure a stubbed session cannot show.
"""

from __future__ import annotations

from codonlab.domain.variants import VariantInput
from codonlab.services.runs import SCORING_CHUNK_POSITIONS, _positions_in_chunks


def _candidates(positions: int, per_position: int = 19) -> list[VariantInput]:
    """A candidate set shaped like a real one: every substitution at every position."""
    alphabet = "ACDEFGHIKLMNPQRSTVWY"
    return [
        VariantInput(
            wild="A",
            label=str(position),
            mutant=alphabet[index % len(alphabet)],
            sequence_position=position,
        )
        for position in range(1, positions + 1)
        for index in range(per_position)
    ]


def test_every_candidate_is_scored_exactly_once() -> None:
    """The property that makes chunking safe to introduce at all.

    A chunker that dropped a position would silently produce a run with missing
    scores — which reads as a smaller design space, not as an error.
    """
    candidates = _candidates(positions=50)
    chunks = list(_positions_in_chunks(candidates, SCORING_CHUNK_POSITIONS))

    seen = [candidate for chunk in chunks for candidate in chunk]
    assert len(seen) == len(candidates), "a candidate was dropped or duplicated"
    assert {c.code for c in seen} == {c.code for c in candidates}


def test_a_position_is_never_split_across_chunks() -> None:
    """The reason chunks are measured in positions rather than candidates.

    ESM-2 does one masked forward pass per position and reads every substitution
    at that position from it. A position split across two chunks would repeat
    the expensive half of the work — the chunking would cost time rather than
    save it.
    """
    # Positions carry *unequal* numbers of candidates here, and that is the
    # whole point of the fixture. Constraints remove individual substitutions
    # before scoring, so real positions are ragged. With a uniform 19 per
    # position a flat slice of the candidate list happens to land on position
    # boundaries anyway — a chunker that ignored positions entirely would pass
    # this test. Mutation testing showed exactly that, so the fixture is ragged.
    ragged: list[VariantInput] = []
    for position in range(1, 41):
        for index in range(1 + position % 5):
            ragged.append(
                VariantInput(
                    wild="A",
                    label=str(position),
                    mutant="ACDEFG"[index],
                    sequence_position=position,
                )
            )

    # Two positions per chunk, against ~120 candidates: small enough that a
    # candidate-counting chunker must cut through the middle of a position.
    chunks = list(_positions_in_chunks(ragged, 2))

    seen: set[int] = set()
    for chunk in chunks:
        here = {candidate.sequence_position for candidate in chunk}
        assert not (here & seen), f"positions {here & seen} appear in two chunks"
        seen |= here
    assert seen == set(range(1, 41)), "every position must appear somewhere"


def test_chunks_are_the_requested_size_in_positions() -> None:
    chunks = list(_positions_in_chunks(_candidates(positions=50), 7))
    sizes = [len({c.sequence_position for c in chunk}) for chunk in chunks]

    assert sizes[:-1] == [7] * (len(chunks) - 1), sizes
    assert sizes[-1] == 50 % 7, "the last chunk carries the remainder"


def test_positions_are_scored_in_order() -> None:
    """Not cosmetic. A run killed at the timeout has scored a prefix of the
    sequence, and a prefix is something a person can reason about — "it got as
    far as residue 300" — where an arbitrary scattered subset is not."""
    chunks = list(_positions_in_chunks(_candidates(positions=40), 6))
    order = [candidate.sequence_position for chunk in chunks for candidate in chunk]

    assert order == sorted(order)


def test_a_sparse_candidate_set_still_chunks_by_position() -> None:
    """Constraints can remove whole positions before scoring, so the positions
    arriving here are not necessarily contiguous or 1-based."""
    sparse = [
        VariantInput(wild="A", label=str(p), mutant="G", sequence_position=p)
        for p in (5, 5, 9, 40, 41, 900)
    ]
    chunks = list(_positions_in_chunks(sparse, 2))

    assert [sorted({c.sequence_position for c in chunk}) for chunk in chunks] == [
        [5, 9],
        [40, 41],
        [900],
    ]


def test_an_empty_candidate_set_yields_no_chunks() -> None:
    """A predictor is never called with nothing: `_score_in_chunks` returns
    early, and this keeps the generator honest about why that is safe."""
    assert list(_positions_in_chunks([], SCORING_CHUNK_POSITIONS)) == []


def test_the_chunk_size_is_small_against_the_job_timeout() -> None:
    """The size is a measured trade-off, not a preference, so its basis is
    asserted rather than left in a comment.

    At the slowest rate this project has measured — 4,028 candidates in 93% of
    the 3600s timeout, so about 16 s per 19-substitution position — a chunk must
    stay well inside the timeout, or a kill loses most of the work it was meant
    to protect.
    """
    from codonlab.queue import JOB_TIMEOUT_SECONDS

    seconds_per_position = 16.0
    chunk_seconds = SCORING_CHUNK_POSITIONS * seconds_per_position

    assert chunk_seconds < JOB_TIMEOUT_SECONDS * 0.1, (
        f"a chunk costs about {chunk_seconds:.0f}s against a {JOB_TIMEOUT_SECONDS}s "
        f"timeout; losing one to a kill defeats the point of chunking"
    )
    assert SCORING_CHUNK_POSITIONS >= 1
