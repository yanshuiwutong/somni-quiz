"""Prompt invocation helpers."""

from __future__ import annotations

from somni_graph_quiz.llm.parsers import parse_json_object


def invoke_json(provider: object, *, prompt_key: str, prompt_text: str) -> dict:
    """Invoke a provider and parse a strict JSON object response."""
    raw_output = provider.generate(prompt_key, prompt_text)
    return parse_json_object(raw_output)
