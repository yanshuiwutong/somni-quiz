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
    progress_percent: float,
) -> dict:
    """Return the public turn result shape."""
    return {
        "updated_graph_state": updated_graph_state,
        "answer_record": answer_record,
        "pending_question": pending_question,
        "assistant_message": assistant_message,
        "finalized": finalized,
        "final_result": final_result,
        "progress_percent": progress_percent,
    }


def calculate_progress_percent(
    *,
    answered_question_ids: list[str],
    partial_question_ids: list[str],
    question_count: int,
    finalized: bool,
) -> float:
    """Calculate completion percentage across answered and partial questions."""
    if finalized:
        return 100.0
    if question_count <= 0:
        return 0.0

    answered = {str(question_id) for question_id in answered_question_ids if str(question_id)}
    partial = {
        str(question_id)
        for question_id in partial_question_ids
        if str(question_id) and str(question_id) not in answered
    }
    completed_units = len(answered) + (len(partial) * 0.5)
    return (completed_units / question_count) * 100.0
