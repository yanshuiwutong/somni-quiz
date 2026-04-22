"""Helpers for parsing provider outputs."""

from __future__ import annotations

import json
import re


_JSON_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def parse_json_object(raw_text: str) -> dict:
    """Parse a strict JSON object from provider output."""
    candidate = raw_text.strip()
    fence_match = _JSON_FENCE_PATTERN.search(candidate)
    if fence_match:
        candidate = fence_match.group(1)
    elif "{" in candidate and "}" in candidate:
        candidate = candidate[candidate.find("{") : candidate.rfind("}") + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM output is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("LLM output must be a JSON object")
    return parsed
