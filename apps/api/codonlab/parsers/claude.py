"""Goal parsing with Claude.

Structured extraction: free text in, the typed objective of `domain.goal` out,
enforced by a JSON schema rather than by hoping the model returns valid JSON.

Scope boundary, and it is narrow: this reads a sentence a scientist wrote and
records what it says. It has **no scientific authority**. It never supplies a
threshold, a temperature, a host, or an assay the user did not state, and the
schema gives it `null` for every field so that "not stated" is always available
and never harder to express than a guess.

Nothing here can start a run. The parse is a proposal; the user confirms it.
"""

from __future__ import annotations

import json
import os
from typing import Any

import anthropic

from codonlab.domain.goal import ParsedGoal, ParseMethod, spec_from_json

#: Per the Anthropic API skill, Opus 5 is the default. Overridable for cost.
DEFAULT_MODEL = "claude-opus-5"

#: Short structured extraction with a human confirming the result — this does
#: not need deep reasoning, and low effort keeps the composer responsive.
EFFORT = "low"

#: Generous because on Opus 5 thinking is on by default and `max_tokens` caps
#: thinking and response text together; a tight budget truncates the JSON.
MAX_TOKENS = 8000

SYSTEM = """\
You extract a structured objective from a protein engineer's free-text goal.

You are a reading instrument, not an advisor. Record what the sentence says.

Rules, in order of importance:
1. Never supply a value the user did not state. If they did not name a target
   temperature, a budget, an expression host, or an assay, those fields are
   null. A plausible default is worse than null here, because the person
   reading your output cannot tell the two apart.
2. Never convert units, normalise numbers, or infer a value from another. If
   they wrote 65 C, the value is 65 and the unit is "C".
3. Put the user's own words in objective_detail and in preserve. Do not
   paraphrase into technical vocabulary they did not use.
4. Anything you could not place goes in unparsed, verbatim. A clause you drop
   is a clause the user believes you understood.
5. Choose exactly one objective, the one the sentence is primarily about. If
   the sentence is not about improving a protein property, use "other".
"""

#: Constrained to what structured outputs support: no numeric or length
#: constraints, every object closed with additionalProperties false.
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "objective": {
            "type": ["string", "null"],
            "enum": [
                "thermostability",
                "activity",
                "expression",
                "solubility",
                "binding_affinity",
                "specificity",
                "solvent_tolerance",
                "other",
                None,
            ],
            "description": "The single property the user wants to improve.",
        },
        "objective_detail": {
            "type": ["string", "null"],
            "description": "The user's own words for the objective.",
        },
        "target_value": {
            "type": ["object", "null"],
            "properties": {
                "value": {"type": "number"},
                "unit": {"type": "string", "description": "As written, e.g. '°C'."},
            },
            "required": ["value", "unit"],
            "additionalProperties": False,
            "description": "A target the user stated. Null if they stated none.",
        },
        "preserve": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Properties to hold constant, in the user's words.",
        },
        "budget": {
            "type": "object",
            "properties": {
                "variants": {"type": ["integer", "null"]},
                "amount": {"type": ["number", "null"]},
                "currency": {"type": ["string", "null"], "description": "ISO code."},
            },
            "required": ["variants", "amount", "currency"],
            "additionalProperties": False,
        },
        "expression_host": {"type": ["string", "null"]},
        "assay": {"type": ["string", "null"]},
        "unparsed": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Clauses you could not place, verbatim.",
        },
    },
    "required": [
        "objective",
        "objective_detail",
        "target_value",
        "preserve",
        "budget",
        "expression_host",
        "assay",
        "unparsed",
    ],
    "additionalProperties": False,
}


class ParserUnavailableError(RuntimeError):
    """Claude could not produce a parse. The caller falls back to the rules."""


def is_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def _model() -> str:
    return os.environ.get("CODONLAB_PARSER_MODEL", "").strip() or DEFAULT_MODEL


def parse(text: str, *, client: anthropic.Anthropic | None = None) -> ParsedGoal:
    """Parse a goal with Claude. Raises ParserUnavailableError on any failure."""
    if not is_configured() and client is None:
        raise ParserUnavailableError("No ANTHROPIC_API_KEY is configured.")

    api = client or anthropic.Anthropic()

    # Typed as Any at this one boundary: the SDK's TypedDict for output_config
    # is narrower than the documented shape, and widening it here is preferable
    # to reshaping a request the API accepts.
    output_config: Any = {
        "effort": EFFORT,
        "format": {"type": "json_schema", "schema": SCHEMA},
    }

    try:
        response = api.messages.create(
            model=_model(),
            max_tokens=MAX_TOKENS,
            system=SYSTEM,
            output_config=output_config,
            messages=[{"role": "user", "content": text}],
        )
    except anthropic.APIStatusError as error:
        raise ParserUnavailableError(f"The parser API returned {error.status_code}.") from error
    except anthropic.APIConnectionError as error:
        raise ParserUnavailableError("The parser API could not be reached.") from error

    # Safety classifiers can decline a request and still return HTTP 200. Check
    # the stop reason before touching content — this is a live path for a
    # protein tool, and indexing content[0] on a refusal raises.
    if response.stop_reason == "refusal":
        category = getattr(response.stop_details, "category", None)
        raise ParserUnavailableError(
            f"The parser declined this goal{f' ({category})' if category else ''}."
        )
    if response.stop_reason == "max_tokens":
        raise ParserUnavailableError("The parse was truncated before it was complete.")

    payload = _first_text(response)
    if payload is None:
        raise ParserUnavailableError("The parser returned no text to read.")

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ParserUnavailableError("The parser returned output that was not JSON.") from error

    return ParsedGoal(
        raw_text=text,
        spec=spec_from_json(parsed),
        method=ParseMethod.CLAUDE,
        note=f"Parsed by {response.model}. Check every chip before confirming.",
    )


def _first_text(response: anthropic.types.Message) -> str | None:
    for block in response.content:
        if block.type == "text":
            return block.text
    return None
