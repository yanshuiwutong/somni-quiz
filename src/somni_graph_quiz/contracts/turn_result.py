"""Turn result helpers."""

from __future__ import annotations


def create_turn_result(
    *,
    updated_graph_state: dict,
    answer_record: dict,
    pending_question: dict | None,
    assistant_message: str,
    finalized: bool,
    final_result: dict | None,
) -> dict:
    """Return the public turn result shape."""
    return {
        "updated_graph_state": updated_graph_state,
        "answer_record": answer_record,
        "pending_question": pending_question,
        "assistant_message": assistant_message,
        "finalized": finalized,
        "final_result": final_result,
    }
