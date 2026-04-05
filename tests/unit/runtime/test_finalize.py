"""Tests for finalize helpers."""

from somni_graph_quiz.contracts.graph_state import create_graph_state
from somni_graph_quiz.contracts.node_contracts import create_branch_result
from somni_graph_quiz.nodes.layer3.finalize import TurnFinalizeNode


def test_finalize_prefers_next_pending_question(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-1",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    branch_result = {
        "branch_type": "content",
        "state_patch": {
            "session_memory": {
                "answered_records": {
                    "question-01": {
                        "question_id": "question-01",
                        "selected_options": [],
                        "input_value": "22",
                        "field_updates": {},
                    }
                },
                "answered_question_ids": ["question-01"],
                "pending_question_ids": ["question-02"],
                "current_question_id": "question-02",
                "question_states": {
                    "question-01": {
                        "status": "answered",
                        "attempt_count": 0,
                        "last_action_mode": "answer",
                    }
                },
            }
        },
        "applied_question_ids": ["question-01"],
        "modified_question_ids": [],
        "partial_question_ids": [],
        "skipped_question_ids": [],
        "rejected_unit_ids": [],
        "clarification_needed": False,
        "response_facts": {"recorded_question_ids": ["question-01"]},
    }

    finalized = TurnFinalizeNode().run(graph_state, branch_result)

    assert finalized.turn_outcome == "answered"
    assert finalized.next_question == {
        "question_id": "question-02",
        "title": question_catalog["question_index"]["question-02"]["title"],
        "input_type": question_catalog["question_index"]["question-02"]["input_type"],
    }
    assert finalized.response_facts["next_question_id"] == "question-02"


def test_finalize_marks_completed_when_all_questions_answered(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-1",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="en",
    )
    branch_result = {
        "branch_type": "content",
        "state_patch": {
                "session_memory": {
                    "answered_question_ids": [
                        "question-01",
                        "question-02",
                        "question-03",
                        "question-04",
                    ],
                    "pending_question_ids": [],
                    "unanswered_question_ids": [],
                    "current_question_id": None,
            }
        },
        "applied_question_ids": ["question-02"],
        "modified_question_ids": [],
        "partial_question_ids": [],
        "skipped_question_ids": [],
        "rejected_unit_ids": [],
        "clarification_needed": False,
        "response_facts": {},
    }

    finalized = TurnFinalizeNode().run(graph_state, branch_result)

    assert finalized.turn_outcome == "completed"
    assert finalized.finalized is True
    assert finalized.next_question is None


def test_finalize_marks_view_previous_as_view_only(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-finalize-view",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    branch_result = create_branch_result(
        branch_type="non_content",
        response_facts={
            "non_content_mode": "view",
            "non_content_action": "view_previous",
            "view_target_question_id": "question-01",
            "view_records": [{"question_id": "question-01", "selected_options": ["B"], "input_value": ""}],
        },
    )

    finalized = TurnFinalizeNode().run(graph_state, branch_result)

    assert finalized.turn_outcome == "view_only"
    assert finalized.response_facts["non_content_action"] == "view_previous"
    assert finalized.response_facts["view_target_question_id"] == "question-01"


def test_finalize_marks_navigate_previous_as_navigation(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-finalize-previous",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    branch_result = create_branch_result(
        branch_type="non_content",
        state_patch={"session_memory": {"current_question_id": "question-01"}},
        response_facts={
            "non_content_mode": "control",
            "control_action": "navigate_previous",
            "non_content_action": "navigate_previous",
            "next_question_id": "question-01",
        },
    )

    finalized = TurnFinalizeNode().run(graph_state, branch_result)

    assert finalized.turn_outcome == "navigate"
    assert finalized.next_question == {
        "question_id": "question-01",
        "title": question_catalog["question_index"]["question-01"]["title"],
        "input_type": question_catalog["question_index"]["question-01"]["input_type"],
    }
    assert finalized.response_facts["non_content_action"] == "navigate_previous"


def test_finalize_includes_minimal_response_context(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-finalize-context",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["turn"].update(
        {
            "raw_input": "你是谁",
            "input_mode": "message",
            "normalized_input": "你是谁",
            "main_branch": "non_content",
            "non_content_intent": "identity",
        }
    )
    graph_state["session_memory"]["current_question_id"] = "question-02"
    branch_result = create_branch_result(
        branch_type="non_content",
        response_facts={
            "non_content_mode": "pullback",
            "non_content_action": "pullback",
            "pullback_reason": "identity_question",
        },
    )

    finalized = TurnFinalizeNode().run(graph_state, branch_result)

    assert finalized.raw_input == "你是谁"
    assert finalized.input_mode == "message"
    assert finalized.main_branch == "non_content"
    assert finalized.non_content_intent == "identity"
    assert finalized.current_question == {
        "question_id": "question-02",
        "title": question_catalog["question_index"]["question-02"]["title"],
        "input_type": question_catalog["question_index"]["question-02"]["input_type"],
    }
    assert finalized.next_question == {
        "question_id": "question-02",
        "title": question_catalog["question_index"]["question-02"]["title"],
        "input_type": question_catalog["question_index"]["question-02"]["input_type"],
    }
