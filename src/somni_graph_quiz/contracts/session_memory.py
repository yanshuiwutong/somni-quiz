"""Session memory helpers."""

from __future__ import annotations


def create_session_memory(question_catalog: dict) -> dict:
    """Create empty session memory from the static question catalog."""
    question_order = list(question_catalog["question_order"])
    current_question_id = question_order[0] if question_order else None
    return {
        "current_question_id": current_question_id,
        "pending_question_ids": question_order[:],
        "question_states": {
            question_id: {
                "status": "unanswered",
                "attempt_count": 0,
                "last_action_mode": None,
            }
            for question_id in question_order
        },
        "answered_records": {},
        "pending_partial_answers": {},
        "pending_modify_context": None,
        "skipped_question_ids": [],
        "previous_answer_record": None,
        "recent_turns": [],
        "unanswered_question_ids": question_order[:],
        "answered_question_ids": [],
        "partial_question_ids": [],
        "clarification_context": None,
    }
