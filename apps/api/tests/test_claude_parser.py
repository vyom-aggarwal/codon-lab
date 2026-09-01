"""The Claude goal parser, driven by a fake client.

Hermetic on purpose. These assert what happens when the API misbehaves —
refuses, truncates, returns something that is not JSON — and that behaviour
must not depend on a network call or on an API key being present.

The refusal branch matters most here. Safety classifiers return a normal
HTTP 200 with `stop_reason: "refusal"`, so code that reads `content[0]`
without checking raises on a path a protein tool will genuinely hit.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import pytest

from codonlab.domain.goal import Objective, ParseMethod
from codonlab.parsers import claude, parse


def block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def response(
    *,
    payload: dict[str, Any] | None = None,
    text: str | None = None,
    stop_reason: str = "end_turn",
    category: str | None = None,
) -> SimpleNamespace:
    body = text if text is not None else json.dumps(payload or {})
    return SimpleNamespace(
        stop_reason=stop_reason,
        stop_details=SimpleNamespace(category=category) if category else None,
        content=[block(body)] if body else [],
        model="claude-opus-5",
    )


class FakeClient:
    """Minimal stand-in exposing only what the parser touches."""

    def __init__(self, result: Any) -> None:
        self._result = result
        self.calls: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


COMPLETE = {
    "objective": "thermostability",
    "objective_detail": "survive 65 C",
    "target_value": {"value": 65, "unit": "°C"},
    "preserve": ["catalytic activity"],
    "budget": {"variants": 96, "amount": 4000, "currency": "USD"},
    "expression_host": "Escherichia coli",
    "assay": "Differential scanning fluorimetry",
    "unparsed": [],
}


class TestHappyPath:
    def test_builds_a_spec_from_the_response(self) -> None:
        client = FakeClient(response(payload=COMPLETE))
        result = claude.parse("make it survive 65 C", client=client)

        assert result.method is ParseMethod.CLAUDE
        assert result.spec.objective is Objective.THERMOSTABILITY
        assert result.spec.target_value is not None
        assert result.spec.target_value.value == 65.0
        assert result.spec.preserve == ("catalytic activity",)
        assert result.spec.budget.variants == 96

    def test_names_the_model_that_produced_it(self) -> None:
        client = FakeClient(response(payload=COMPLETE))
        assert "claude-opus-5" in claude.parse("x", client=client).note

    def test_nulls_stay_null_rather_than_becoming_defaults(self) -> None:
        """The whole point. An unstated field must survive as unstated."""
        sparse = {
            "objective": "thermostability",
            "objective_detail": None,
            "target_value": None,
            "preserve": [],
            "budget": {"variants": None, "amount": None, "currency": None},
            "expression_host": None,
            "assay": None,
            "unparsed": [],
        }
        spec = claude.parse("more thermostable", client=FakeClient(response(payload=sparse))).spec
        assert spec.target_value is None
        assert spec.expression_host is None
        assert spec.assay is None
        assert spec.budget.is_empty
        assert spec.is_runnable is True


class TestRequestShape:
    def test_requests_a_schema_constrained_response(self) -> None:
        client = FakeClient(response(payload=COMPLETE))
        claude.parse("x", client=client)
        sent = client.calls[0]["output_config"]
        assert sent["format"]["type"] == "json_schema"
        assert sent["format"]["schema"]["additionalProperties"] is False

    def test_leaves_room_for_thinking_plus_the_json(self) -> None:
        """On Opus 5 thinking is on by default and max_tokens caps thinking and
        response text together — a tight budget truncates the JSON."""
        client = FakeClient(response(payload=COMPLETE))
        claude.parse("x", client=client)
        assert client.calls[0]["max_tokens"] >= 4000

    def test_the_system_prompt_forbids_inventing_values(self) -> None:
        assert "null" in claude.SYSTEM
        assert "never supply" in claude.SYSTEM.lower()


class TestSchema:
    def test_every_field_is_required_so_none_can_be_silently_omitted(self) -> None:
        properties = set(claude.SCHEMA["properties"])
        assert set(claude.SCHEMA["required"]) == properties

    def test_every_optional_field_admits_null(self) -> None:
        """If null is harder to express than a value, a guess becomes the path
        of least resistance."""
        for name in ("objective", "target_value", "expression_host", "assay"):
            assert "null" in claude.SCHEMA["properties"][name]["type"]

    def test_uses_no_unsupported_json_schema_constraints(self) -> None:
        """Structured outputs reject numeric and length constraints."""
        banned = {"minimum", "maximum", "minLength", "maxLength", "multipleOf", "pattern"}
        serialised = json.dumps(claude.SCHEMA)
        for keyword in banned:
            assert f'"{keyword}"' not in serialised


class TestFailurePaths:
    def test_a_refusal_is_not_read_as_content(self) -> None:
        """HTTP 200 with stop_reason refusal. Indexing content here raises."""
        client = FakeClient(response(text="", stop_reason="refusal", category="bio"))
        with pytest.raises(claude.ParserUnavailableError, match="declined"):
            claude.parse("x", client=client)

    def test_a_refusal_reports_its_category(self) -> None:
        client = FakeClient(response(text="", stop_reason="refusal", category="cyber"))
        with pytest.raises(claude.ParserUnavailableError, match="cyber"):
            claude.parse("x", client=client)

    def test_a_truncated_parse_is_refused_not_half_read(self) -> None:
        client = FakeClient(response(text='{"objective": "thermo', stop_reason="max_tokens"))
        with pytest.raises(claude.ParserUnavailableError, match="truncated"):
            claude.parse("x", client=client)

    def test_non_json_output_is_refused(self) -> None:
        client = FakeClient(response(text="I think you want thermostability!"))
        with pytest.raises(claude.ParserUnavailableError, match="not JSON"):
            claude.parse("x", client=client)

    def test_an_api_error_becomes_parser_unavailable(self) -> None:
        error = anthropic.APIStatusError(
            "boom",
            response=httpx.Response(503, request=httpx.Request("POST", "https://x")),
            body=None,
        )
        with pytest.raises(claude.ParserUnavailableError, match="503"):
            claude.parse("x", client=FakeClient(error))

    def test_no_key_and_no_client_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(claude.ParserUnavailableError, match="No ANTHROPIC_API_KEY"):
            claude.parse("x")


class TestFallback:
    def test_falls_back_to_rules_when_no_key_is_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = parse("make this enzyme survive 65 C without killing activity")

        assert result.method is ParseMethod.RULES
        assert result.needs_review_badge is True
        assert result.spec.objective is Objective.THERMOSTABILITY

    def test_an_empty_goal_never_reaches_the_api(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-a-real-key")
        result = parse("   ")
        assert result.method is ParseMethod.RULES
        assert result.spec.objective is None
