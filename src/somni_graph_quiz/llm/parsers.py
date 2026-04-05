"""Helpers for parsing provider outputs."""

from __future__ import annotations

import json


def parse_json_object(raw_text: str) -> dict:
    """Parse a strict JSON object from provider output."""
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM output is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("LLM output must be a JSON object")
    return parsed
