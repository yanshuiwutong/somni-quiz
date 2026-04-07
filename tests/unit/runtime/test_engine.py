"""Tests for runtime engine turn result shaping."""

from __future__ import annotations

from somni_graph_quiz.contracts.graph_state import create_graph_state
from somni_graph_quiz.contracts.turn_input import TurnInput
from somni_graph_quiz.runtime.engine import GraphRuntimeEngine


def test_engine_populates_final_result_when_turn_is_completed(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-engine-completed",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["answered_records"] = {
        question_id: {
            "question_id": question_id,
            "selected_options": [],
            "input_value": "done",
            "field_updates": {},
        }
        for question_id in question_catalog["question_order"]
    }
    graph_state["session_memory"]["answered_question_ids"] = list(question_catalog["question_order"])
    graph_state["session_memory"]["pending_question_ids"] = []
    graph_state["session_memory"]["unanswered_question_ids"] = []
    graph_state["session_memory"]["current_question_id"] = None

    result = GraphRuntimeEngine().run_turn(
        graph_state,
        TurnInput(
            session_id="session-engine-completed",
            channel="grpc",
            input_mode="message",
            raw_input="谢谢",
            language_preference="zh-CN",
        ),
    )

    assert result["finalized"] is True
    assert result["final_result"] == {
        "completion_message": result["assistant_message"],
        "finalized": True,
    }


def test_engine_keeps_final_result_empty_when_turn_not_completed(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-engine-not-completed",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )

    result = GraphRuntimeEngine().run_turn(
        graph_state,
        TurnInput(
            session_id="session-engine-not-completed",
            channel="grpc",
            input_mode="message",
            raw_input="22",
            language_preference="zh-CN",
        ),
    )

    assert result["finalized"] is False
    assert result["final_result"] is None
