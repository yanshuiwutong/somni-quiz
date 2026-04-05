"""Tests for the minimal non-content branch."""

from somni_graph_quiz.contracts.graph_state import create_graph_state
from somni_graph_quiz.contracts.turn_input import TurnInput
from somni_graph_quiz.nodes.layer2.non_content.branch import NonContentBranch


def test_non_content_branch_moves_to_next_question(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-1",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )

    graph_state["turn"]["non_content_intent"] = "navigate_next"

    result = NonContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-1",
            channel="grpc",
            input_mode="message",
            raw_input="下一题",
        ),
    )

    assert result["branch_type"] == "non_content"
    assert result["state_patch"]["session_memory"]["current_question_id"] == "question-02"
    assert result["response_facts"]["non_content_mode"] == "control"


def test_non_content_branch_marks_thanks_as_pullback(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-1",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )

    graph_state["turn"]["non_content_intent"] = "pullback_chat"

    result = NonContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-1",
            channel="grpc",
            input_mode="message",
            raw_input="谢谢你",
        ),
    )

    assert result["applied_question_ids"] == []
    assert result["response_facts"]["non_content_mode"] == "pullback"


def test_non_content_skip_keeps_partial_answer(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-1",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_partial_answers"]["question-02"] = {
        "question_id": "question-02",
        "filled_fields": {"bedtime": "23:00"},
        "missing_fields": ["wake_time"],
        "source_question_state": "partial",
    }
    graph_state["session_memory"]["partial_question_ids"] = ["question-02"]
    graph_state["session_memory"]["question_states"]["question-02"] = {
        "status": "partial",
        "attempt_count": 1,
        "last_action_mode": "answer",
    }

    graph_state["turn"]["non_content_intent"] = "skip"

    result = NonContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-1",
            channel="grpc",
            input_mode="message",
            raw_input="跳过",
        ),
    )

    assert result["skipped_question_ids"] == ["question-02"]
    assert result["state_patch"]["session_memory"]["pending_partial_answers"]["question-02"]["filled_fields"] == {
        "bedtime": "23:00"
    }


def test_non_content_undo_restores_previous_answer(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-1",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="en",
    )
    graph_state["session_memory"]["answered_records"]["question-01"] = {
        "question_id": "question-01",
        "selected_options": [],
        "input_value": "29",
        "field_updates": {},
    }
    graph_state["session_memory"]["previous_answer_record"] = {
        "question-01": {
            "question_id": "question-01",
            "selected_options": [],
            "input_value": "22",
            "field_updates": {},
        }
    }

    graph_state["turn"]["non_content_intent"] = "undo"

    result = NonContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-1",
            channel="grpc",
            input_mode="message",
            raw_input="undo",
        ),
    )

    assert result["state_patch"]["session_memory"]["answered_records"]["question-01"]["input_value"] == "22"
    assert result["response_facts"]["undo_applied"] is True


def test_non_content_branch_view_all_returns_answer_records(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-view-all",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["answered_records"]["question-01"] = {
        "question_id": "question-01",
        "selected_options": [],
        "input_value": "22",
        "field_updates": {},
    }

    graph_state["turn"]["non_content_intent"] = "view_all"

    result = NonContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-view-all",
            channel="grpc",
            input_mode="message",
            raw_input="查看记录",
        ),
    )

    assert result["branch_type"] == "non_content"
    assert result["response_facts"]["non_content_mode"] == "view"
    assert result["response_facts"]["view_records"] == [
        {
            "question_id": "question-01",
            "selected_options": [],
            "input_value": "22",
            "field_updates": {},
        }
    ]


def test_non_content_branch_uses_turn_intent_for_modify_previous(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-llm-nc",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["turn"]["non_content_intent"] = "modify_previous"
    graph_state["session_memory"]["answered_records"]["question-01"] = {
        "question_id": "question-01",
        "selected_options": [],
        "input_value": "22",
        "field_updates": {},
    }
    graph_state["session_memory"]["answered_question_ids"] = ["question-01"]
    graph_state["session_memory"]["recent_turns"] = [
        {"recorded_question_ids": ["question-01"], "modified_question_ids": []}
    ]
    graph_state["session_memory"]["current_question_id"] = "question-02"

    result = NonContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-llm-nc",
            channel="grpc",
            input_mode="message",
            raw_input="改上一题",
            language_preference="zh-CN",
        ),
    )

    assert result["response_facts"]["control_action"] == "modify_previous"
    assert result["state_patch"]["session_memory"]["current_question_id"] == "question-01"


def test_non_content_branch_uses_identity_intent_as_pullback(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-identity",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["turn"]["non_content_intent"] = "identity"

    result = NonContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-identity",
            channel="grpc",
            input_mode="message",
            raw_input="你是谁",
            language_preference="zh-CN",
        ),
    )

    assert result["response_facts"]["non_content_mode"] == "pullback"
    assert result["response_facts"]["pullback_reason"] == "identity_question"


def test_non_content_branch_view_previous_returns_previous_record(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-view-previous",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["answered_records"]["question-01"] = {
        "question_id": "question-01",
        "selected_options": ["B"],
        "input_value": "",
        "field_updates": {},
    }
    graph_state["session_memory"]["answered_question_ids"] = ["question-01"]
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["recent_turns"] = [
        {
            "turn_index": 0,
            "recorded_question_ids": ["question-01"],
            "modified_question_ids": [],
        }
    ]

    graph_state["turn"]["non_content_intent"] = "view_previous"

    result = NonContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-view-previous",
            channel="grpc",
            input_mode="message",
            raw_input="查看上一题记录",
            language_preference="zh-CN",
        ),
    )

    assert result["branch_type"] == "non_content"
    assert result["response_facts"]["non_content_action"] == "view_previous"
    assert result["response_facts"]["view_target_question_id"] == "question-01"
    assert result["response_facts"]["view_records"] == [
        {
            "question_id": "question-01",
            "selected_options": ["B"],
            "input_value": "",
            "field_updates": {},
        }
    ]


def test_non_content_branch_navigate_previous_switches_to_latest_answered(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-previous",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["answered_records"]["question-01"] = {
        "question_id": "question-01",
        "selected_options": ["B"],
        "input_value": "",
        "field_updates": {},
    }
    graph_state["session_memory"]["answered_question_ids"] = ["question-01"]
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]

    graph_state["turn"]["non_content_intent"] = "navigate_previous"

    result = NonContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-previous",
            channel="grpc",
            input_mode="message",
            raw_input="上一题",
            language_preference="zh-CN",
        ),
    )

    assert result["branch_type"] == "non_content"
    assert result["response_facts"]["non_content_action"] == "navigate_previous"
    assert result["state_patch"]["session_memory"]["current_question_id"] == "question-01"
