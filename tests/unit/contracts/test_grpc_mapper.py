"""Tests for gRPC mapping helpers."""

from somni_quiz_ai.grpc.generated import somni_quiz_pb2

from somni_graph_quiz.adapters.grpc.mapper import (
    build_pending_question_message,
    derive_answer_status_code,
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


def test_map_questionnaire_to_catalog_preserves_question_config() -> None:
    questionnaire = [
        somni_quiz_pb2.BusinessQuestion(
            question_id="question-02",
            title="Q2",
            input_type="time_range",
            config=somni_quiz_pb2.PendingQuestionConfig(
                items=[
                    somni_quiz_pb2.PendingQuestionConfigItem(index=0, label="上床时间：", format="HH:mm"),
                    somni_quiz_pb2.PendingQuestionConfigItem(index=1, label="起床时间：", format="HH:mm"),
                ]
            ),
        )
    ]

    catalog = map_questionnaire_to_catalog(questionnaire)

    assert catalog["question_index"]["question-02"]["config"] == {
        "items": [
            {"index": 0, "label": "上床时间：", "format": "HH:mm"},
            {"index": 1, "label": "起床时间：", "format": "HH:mm"},
        ]
    }


def test_build_pending_question_message_preserves_config() -> None:
    pending = build_pending_question_message(
        {
            "question_id": "question-02",
            "title": "Q2",
            "input_type": "time_range",
            "tags": ["profile"],
            "options": [],
            "config": {
                "items": [
                    {"index": 0, "label": "上床时间：", "format": "HH:mm"},
                    {"index": 1, "label": "起床时间：", "format": "HH:mm"},
                ]
            },
        }
    )

    assert pending.config.items[0].index == 0
    assert pending.config.items[0].label == "上床时间："
    assert pending.config.items[0].format == "HH:mm"
    assert pending.config.items[1].index == 1
    assert pending.config.items[1].label == "起床时间："


def test_derive_answer_status_code_returns_recorded_for_applied_answers() -> None:
    status_code = derive_answer_status_code(
        {
            "recorded_question_ids": ["question-01"],
            "modified_question_ids": [],
            "partial_question_ids": [],
        }
    )

    assert status_code == "RECORDED"


def test_derive_answer_status_code_returns_partial_when_answer_is_incomplete() -> None:
    status_code = derive_answer_status_code(
        {
            "recorded_question_ids": [],
            "modified_question_ids": [],
            "partial_question_ids": ["question-02"],
        }
    )

    assert status_code == "PARTIAL"


def test_derive_answer_status_code_returns_updated_for_modified_answers() -> None:
    status_code = derive_answer_status_code(
        {
            "recorded_question_ids": [],
            "modified_question_ids": ["question-01"],
            "partial_question_ids": [],
        }
    )

    assert status_code == "UPDATED"


def test_derive_answer_status_code_returns_not_recorded_without_answer_changes() -> None:
    status_code = derive_answer_status_code(
        {
            "recorded_question_ids": [],
            "modified_question_ids": [],
            "partial_question_ids": [],
        }
    )

    assert status_code == "NOT_RECORDED"


def test_derive_answer_status_code_falls_back_to_answer_record_when_turn_metadata_is_missing() -> None:
    status_code = derive_answer_status_code(
        {},
        {
            "answers": [
                {
                    "question_id": "question-01",
                    "selected_options": ["A"],
                    "input_value": "",
                }
            ]
        },
    )

    assert status_code == "RECORDED"
