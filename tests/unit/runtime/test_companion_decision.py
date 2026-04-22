"""Tests for companion decision validation."""

from somni_graph_quiz.runtime.companion_decision import CompanionDecisionEngine


def test_validate_accepts_continue_chat_intent() -> None:
    result = CompanionDecisionEngine()._validate(
        {
            "companion_action": "stay",
            "companion_mode": "supportive",
            "continue_chat_intent": "strong",
            "answer_status_override": "NOT_RECORDED",
            "reason": "user still wants to continue chatting",
        }
    )

    assert result is not None
    assert result["continue_chat_intent"] == "strong"


def test_validate_rejects_invalid_continue_chat_intent() -> None:
    result = CompanionDecisionEngine()._validate(
        {
            "companion_action": "stay",
            "companion_mode": "supportive",
            "continue_chat_intent": "maybe",
            "answer_status_override": "NOT_RECORDED",
            "reason": "invalid enum",
        }
    )

    assert result is None
