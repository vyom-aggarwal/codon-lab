"""Content addressing.

ARCHITECTURE.md §6: results are cached on ``hash(model_version + inputs)``. That
only works if the same inputs hash the same way every time, on every machine, so
the encoding is pinned here rather than left to whatever ``json.dumps`` defaults
to at the call site:

* keys sorted, so a dict built in a different order is the same content;
* no whitespace, so a formatting change is not a cache miss;
* ``ensure_ascii`` off, so a degree sign is itself rather than an escape whose
  spelling could change;
* floats written as ``repr``, the shortest string that round-trips to the same
  double, rather than left to a formatter that might round. Two values that are
  not the same double hash differently — which is what a cache key over a
  measured quantity has to do. NaN and the infinities are refused outright: they
  are not values a goal or a parameter can legitimately hold, and JSON has no
  spelling for them that survives a round trip.

The prefix on the digest names the algorithm. A bare hex string in a database
column is unreadable in five years when the algorithm has moved on.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

ALGORITHM = "sha256"


class UnhashableInputError(TypeError):
    """Raised when a value cannot be content-addressed reproducibly."""


def _canonical(value: Any) -> Any:
    """Rewrite a value into a form whose text is stable across machines."""
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise UnhashableInputError(
                f"{value!r} cannot be content-addressed. A goal, a parameter or a "
                "score that is not a finite number is a bug upstream of here."
            )
        # repr is the shortest representation that round-trips to the same
        # double, and has been since Python 3.1 — so `65.0` addresses as "65.0"
        # on every machine rather than as whatever a formatter chose.
        return repr(value)
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_canonical(item) for item in value]
    if isinstance(value, str | int | bool) or value is None:
        return value
    # UUIDs, enums, datetimes: str() is stable for all three.
    return str(value)


def canonical_json(payload: Any) -> str:
    return json.dumps(
        _canonical(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def content_hash(payload: Any) -> str:
    """A stable address for a structured value, e.g. ``sha256:1a2b...``."""
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return f"{ALGORITHM}:{digest}"


def digest_of(text: str) -> str:
    """The address of a blob of text — a sequence, a structure file."""
    return f"{ALGORITHM}:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def short(address: str, length: int = 12) -> str:
    """The leading characters of a digest, for display beside a full value."""
    _, _, digest = address.partition(":")
    return digest[:length] or address[:length]
