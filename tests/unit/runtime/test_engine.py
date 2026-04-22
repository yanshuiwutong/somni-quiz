"""Tests for runtime engine turn result shaping."""

from __future__ import annotations

from types import SimpleNamespace

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


def test_engine_keeps_companion_turn_status_masked(companion_question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="engine-companion-mask",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )

    result = GraphRuntimeEngine().run_turn(
        graph_state,
        TurnInput(
            session_id="engine-companion-mask",
            channel="grpc",
            input_mode="message",
            raw_input="你好",
            language_preference="zh-CN",
        ),
    )

    assert result["updated_graph_state"]["session_memory"]["companion_context"]["active"] is True
    assert result["updated_graph_state"]["session_memory"]["recent_turns"][-1]["turn_outcome"] == "pullback"
    assert (
        result["updated_graph_state"]["session_memory"]["recent_turns"][-1]["answer_status_override"]
        == "NOT_RECORDED"
    )


def test_engine_recent_turn_summary_tracks_companion_pullback_anchor(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="engine-companion-pullback-anchor",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    engine = GraphRuntimeEngine()

    finalized = SimpleNamespace(
        raw_input="好啊",
        response_facts={
            "stay_in_companion": True,
            "continue_chat_intent": "weak",
        },
        current_question={"question_id": "question-02", "title": "您平时通常的作息？"},
        next_question={"question_id": "question-02", "title": "您平时通常的作息？"},
        turn_outcome="pullback",
    )

    engine._append_recent_turn(
        graph_state,
        TurnInput(
            session_id="engine-companion-pullback-anchor",
            channel="grpc",
            input_mode="message",
            raw_input="好啊",
            language_preference="zh-CN",
        ),
        {
            "applied_question_ids": [],
            "modified_question_ids": [],
            "partial_question_ids": [],
            "skipped_question_ids": [],
        },
        finalized,
        "刚才那种睡不稳的感觉我们先放在这儿。要是你愿意，我们也可以慢慢从您平时通常的作息这部分继续往下看。",
    )

    recent_turn = graph_state["session_memory"]["recent_turns"][-1]
    assert recent_turn["assistant_mode"] == "companion"
    assert recent_turn["assistant_pullback_anchor"] == "您平时通常的作息？"
