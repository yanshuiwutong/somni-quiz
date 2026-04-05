"""Finalized turn context contract."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class FinalizedTurnContext:
    """Canonical handoff from finalize to response composition."""

    turn_outcome: str
    updated_answer_record: dict
    updated_question_states: dict
    current_question_id: str | None
    next_question: dict | None
    finalized: bool
    response_language: str
    response_facts: dict
    raw_input: str = ""
    input_mode: str = "message"
    main_branch: str = "content"
    non_content_intent: str = "none"
    current_question: dict | None = None

    def to_response_payload(self) -> dict[str, str]:
        """Return the public response payload contract shape."""
        return {"assistant_message": ""}


def create_finalized_turn_context(
    *,
    turn_outcome: str,
    updated_answer_record: dict,
    updated_question_states: dict,
    current_question_id: str | None,
    next_question: dict | None,
    finalized: bool,
    response_language: str,
    response_facts: dict,
    raw_input: str = "",
    input_mode: str = "message",
    main_branch: str = "content",
    non_content_intent: str = "none",
    current_question: dict | None = None,
) -> FinalizedTurnContext:
    """Build a finalized turn context."""
    return FinalizedTurnContext(
        turn_outcome=turn_outcome,
        updated_answer_record=updated_answer_record,
        updated_question_states=updated_question_states,
        current_question_id=current_question_id,
        next_question=next_question,
        finalized=finalized,
        response_language=response_language,
        response_facts=response_facts,
        raw_input=raw_input,
        input_mode=input_mode,
        main_branch=main_branch,
        non_content_intent=non_content_intent,
        current_question=current_question,
    )
