"""Tests for strict JSON parsing and invocation."""

from somni_graph_quiz.llm.client import FakeLLMProvider
from somni_graph_quiz.llm.invocation import invoke_json
from somni_graph_quiz.llm.parsers import parse_json_object


def test_parse_json_object_accepts_object_payload() -> None:
    parsed = parse_json_object('{"main_branch": "content"}')

    assert parsed == {"main_branch": "content"}


def test_parse_json_object_rejects_non_object_payload() -> None:
    try:
        parse_json_object('["content"]')
    except ValueError as exc:
        assert "JSON object" in str(exc)
    else:
        raise AssertionError("Expected ValueError for non-object JSON payload")


def test_invoke_json_uses_provider_and_parser() -> None:
    provider = FakeLLMProvider(
        responses={"turn-classify": '{"main_branch": "non_content", "normalized_input": "下一题"}'}
    )

    result = invoke_json(provider, prompt_key="turn-classify", prompt_text="prompt")

    assert result["main_branch"] == "non_content"
