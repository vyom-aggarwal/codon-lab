"""Content addressing has to be stable, or the cache is worse than no cache.

A hash that varies with dictionary insertion order would miss every time, which
is merely slow. A hash that *collides* across different inputs would serve one
model's numbers as another's, which is the failure this product cannot have.
"""

from __future__ import annotations

import pytest

from codonlab.domain.hashing import (
    UnhashableInputError,
    canonical_json,
    content_hash,
    digest_of,
    short,
)


def test_key_order_does_not_change_the_address() -> None:
    assert content_hash({"a": 1, "b": 2}) == content_hash({"b": 2, "a": 1})


def test_nesting_order_does_not_change_the_address() -> None:
    left = {"model": {"id": "x", "version": "1"}, "inputs": [1, 2]}
    right = {"inputs": [1, 2], "model": {"version": "1", "id": "x"}}
    assert content_hash(left) == content_hash(right)


def test_list_order_does_change_the_address() -> None:
    """Order is content for a list. A caller that wants order-insensitivity
    sorts before hashing, visibly, rather than the hash deciding for it."""
    assert content_hash([1, 2]) != content_hash([2, 1])


def test_a_different_model_version_is_a_different_address() -> None:
    base = {"model": {"id": "esm", "version": "1", "weights_hash": "abc"}}
    bumped = {"model": {"id": "esm", "version": "2", "weights_hash": "abc"}}
    reweighted = {"model": {"id": "esm", "version": "1", "weights_hash": "def"}}
    assert len({content_hash(base), content_hash(bumped), content_hash(reweighted)}) == 3


def test_none_is_not_the_string_none() -> None:
    assert content_hash({"structure": None}) != content_hash({"structure": "None"})


def test_int_and_float_are_different_content() -> None:
    assert content_hash({"target": 65}) != content_hash({"target": 65.0})


def test_floats_round_trip_through_the_address() -> None:
    """A stated target value is a float. Rejecting it outright would refuse a
    legitimate goal; formatting it loosely would collide two different values."""
    assert content_hash({"value": 65.0}) == content_hash({"value": 65.0})
    assert content_hash({"value": 65.0}) != content_hash({"value": 65.1})
    assert content_hash({"value": 0.1 + 0.2}) != content_hash({"value": 0.3})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_are_refused(value: float) -> None:
    with pytest.raises(UnhashableInputError):
        content_hash({"value": value})


def test_unicode_is_not_escaped() -> None:
    """`°C` must hash as itself, not as an escape whose spelling could change."""
    assert "°C" in canonical_json({"unit": "°C"})


def test_the_algorithm_is_named_in_the_address() -> None:
    assert content_hash({}).startswith("sha256:")
    assert digest_of("").startswith("sha256:")


def test_short_drops_the_algorithm_prefix() -> None:
    assert short(content_hash({"a": 1}), 8) == content_hash({"a": 1})[len("sha256:") :][:8]
