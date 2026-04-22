"""Focused tests for mixed-input content apply behavior."""

from somni_graph_quiz.contracts.graph_state import create_graph_state
from somni_graph_quiz.nodes.layer2.content.apply import ContentApplyNode


def _question_catalog() -> dict:
    return {
        "question_order": ["question-01", "question-02"],
        "question_index": {
            "question-01": {
                "question_id": "question-01",
                "title": "您的年龄段？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "18-24 岁", "aliases": []},
                    {"option_id": "B", "label": "25-34 岁", "aliases": []},
                ],
                "tags": ["基础信息"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["年龄"],
                },
            },
            "question-02": {
                "question_id": "question-02",
                "title": "您平时通常的作息？",
                "description": "",
                "input_type": "time_range",
                "options": [],
                "tags": ["作息"],
                "metadata": {
                    "allow_partial": True,
                    "structured_kind": "time_range",
                    "response_style": "followup",
                    "matching_hints": ["作息"],
                },
            },
        },
    }


def test_content_apply_records_resolved_schedule_even_when_tail_still_needs_clarification() -> None:
    graph_state = create_graph_state(
        session_id="session-mixed-apply-schedule-tail",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=_question_catalog(),
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["answered_records"]["question-01"] = {
        "question_id": "question-01",
        "selected_options": ["A"],
        "input_value": "",
        "field_updates": {},
    }
    graph_state["session_memory"]["answered_question_ids"] = ["question-01"]
    graph_state["session_memory"]["unanswered_question_ids"] = ["question-02"]
    graph_state["session_memory"]["pending_question_ids"] = ["question-02"]
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["question_states"]["question-01"] = {
        "status": "answered",
        "attempt_count": 0,
        "last_action_mode": "answer",
    }

    result = ContentApplyNode().run(
        graph_state,
        [
            {
                "unit_id": "unit-1",
                "unit_text": "早七晚十",
                "action_mode": "answer",
                "candidate_question_ids": ["question-02"],
                "winner_question_id": "question-02",
                "needs_attribution": False,
                "raw_extracted_value": {"bedtime": "22:00", "wake_time": "07:00"},
                "selected_options": [],
                "input_value": "22:00-07:00",
                "field_updates": {"bedtime": "22:00", "wake_time": "07:00"},
                "missing_fields": [],
            },
            {
                "unit_id": "unit-2",
                "unit_text": "你是谁",
                "action_mode": "answer",
                "candidate_question_ids": ["question-02"],
                "winner_question_id": None,
                "needs_attribution": False,
                "raw_extracted_value": "你是谁",
                "selected_options": [],
                "input_value": "你是谁",
                "field_updates": {},
                "missing_fields": [],
            },
        ],
        clarification_needed=True,
        clarification_details={
            "clarification_reason": "content_understand",
            "clarification_question_id": "question-02",
            "clarification_question_title": "您平时通常的作息？",
            "clarification_kind": "content_understand",
        },
    )

    answers = result["state_patch"]["session_memory"]["answered_records"]
    assert result["applied_question_ids"] == ["question-02"]
    assert answers["question-02"]["field_updates"] == {"bedtime": "22:00", "wake_time": "07:00"}
    assert result["clarification_needed"] is False


def test_content_apply_keeps_current_short_circuit_when_no_resolved_units_exist() -> None:
    graph_state = create_graph_state(
        session_id="session-mixed-apply-no-closed-units",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=_question_catalog(),
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02"]

    result = ContentApplyNode().run(
        graph_state,
        [
            {
                "unit_id": "unit-1",
                "unit_text": "你是谁",
                "action_mode": "answer",
                "candidate_question_ids": ["question-02"],
                "winner_question_id": None,
                "needs_attribution": False,
                "raw_extracted_value": "你是谁",
                "selected_options": [],
                "input_value": "你是谁",
                "field_updates": {},
                "missing_fields": [],
            }
        ],
        clarification_needed=True,
        clarification_details={
            "clarification_reason": "content_understand",
            "clarification_question_id": "question-02",
            "clarification_question_title": "您平时通常的作息？",
            "clarification_kind": "content_understand",
        },
    )

    assert result["clarification_needed"] is True
    assert result["applied_question_ids"] == []
    assert result["state_patch"]["session_memory"]["answered_records"] == {}
