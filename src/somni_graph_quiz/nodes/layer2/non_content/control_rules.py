"""Rule helpers for non-content control actions."""

from __future__ import annotations


def detect_control_action(raw_input: str) -> str | None:
    """Detect a simple control action from user input."""
    normalized = raw_input.strip().lower()
    if not normalized:
        return None
    if "查看上一题记录" in raw_input:
        return "view_previous"
    if "查看当前题记录" in raw_input or "查看这题记录" in raw_input:
        return "view_current"
    if "查看下一题" in raw_input:
        return "view_next"
    if "改上一题" in raw_input or "修改上一题" in raw_input or "previous answer" in normalized:
        return "modify_previous"
    if "上一题" in raw_input or "previous question" in normalized:
        return "navigate_previous"
    if "下一题" in raw_input or "next" in normalized:
        return "navigate_next"
    if "跳过" in raw_input or "skip" in normalized:
        return "skip"
    if "撤回" in raw_input or "undo" in normalized:
        return "undo"
    if "查看" in raw_input or "view" in normalized:
        return "view_all"
    return None
