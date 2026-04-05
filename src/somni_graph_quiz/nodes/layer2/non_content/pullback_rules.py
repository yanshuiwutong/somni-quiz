"""Rule helpers for pullback detection."""

from __future__ import annotations


def is_pullback_input(raw_input: str) -> bool:
    """Return whether the input should be treated as pullback."""
    normalized = raw_input.strip().lower()
    if not normalized:
        return True
    return any(
        keyword in normalized
        for keyword in ("谢谢", "你是谁", "哈哈", "thank", "hello", "hi")
    )
