"""Helpers for state transitions."""

from __future__ import annotations

from somni_graph_quiz.contracts.graph_state import merge_graph_state


def apply_branch_state_patch(graph_state: dict, branch_result: dict) -> dict:
    """Apply a branch state patch to a graph state."""
    return merge_graph_state(graph_state, branch_result.get("state_patch", {}))
