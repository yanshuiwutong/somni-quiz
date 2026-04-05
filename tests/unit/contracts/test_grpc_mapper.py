"""Tests for gRPC mapping helpers."""

from somni_quiz_ai.grpc.generated import somni_quiz_pb2

from somni_graph_quiz.adapters.grpc.mapper import (
    build_pending_question_message,
    map_chat_request_to_turn_input,
    map_questionnaire_to_catalog,
)


def test_map_questionnaire_to_catalog_preserves_order() -> None:
    questionnaire = [
        somni_quiz_pb2.BusinessQuestion(question_id="question-01", title="Q1", input_type="text"),
        somni_quiz_pb2.BusinessQuestion(question_id="question-02", title="Q2", input_type="time_range"),
    ]

    catalog = map_questionnaire_to_catalog(questionnaire)

    assert catalog["question_order"] == ["question-01", "question-02"]
    assert catalog["question_index"]["question-02"]["title"] == "Q2"


def test_map_chat_request_to_turn_input_supports_direct_answer() -> None:
    request = somni_quiz_pb2.ChatQuizRequest(
        session_id="session-1",
        direct_answer=somni_quiz_pb2.DirectAnswer(
            question_id="question-01",
            input_value="22",
        ),
    )

    turn_input = map_chat_request_to_turn_input(request, language_preference="en")

    assert turn_input.input_mode == "direct_answer"
    assert turn_input.raw_input == "22"


def test_build_pending_question_message_returns_proto_message() -> None:
    pending = build_pending_question_message(
        {
            "question_id": "question-01",
            "title": "Q1",
            "input_type": "text",
            "tags": ["profile"],
            "options": [],
        }
    )

    assert isinstance(pending, somni_quiz_pb2.PendingQuestion)
    assert pending.question_id == "question-01"
