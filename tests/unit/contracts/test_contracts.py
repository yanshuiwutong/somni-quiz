"""Contract tests for minimal graph runtime types."""

import threading

from somni_graph_quiz.contracts.finalized_turn_context import create_finalized_turn_context
from somni_graph_quiz.contracts.graph_state import create_graph_state, merge_graph_state
from somni_graph_quiz.contracts.turn_input import TurnInput
from somni_graph_quiz.contracts.turn_result import calculate_progress_percent


def test_create_graph_state_has_expected_top_level_sections(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-1",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )

    assert sorted(graph_state.keys()) == [
        "artifacts",
        "question_catalog",
        "runtime",
        "session",
        "session_memory",
        "turn",
    ]
    assert graph_state["session_memory"]["current_question_id"] == "question-01"
    assert graph_state["session_memory"]["pending_question_ids"] == [
        "question-01",
        "question-02",
        "question-03",
        "question-04",
    ]
    assert graph_state["session"]["default_city"] == ""
    assert graph_state["session_memory"]["pending_weather_query"] is None
    assert graph_state["turn"]["response_language"] == "zh-CN"


def test_create_graph_state_preserves_custom_default_city(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-city",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
        default_city="上海",
    )

    assert graph_state["session"]["default_city"] == "上海"


def test_turn_input_defaults_direct_answer_payload_to_none() -> None:
    turn_input = TurnInput(
        session_id="session-1",
        channel="grpc",
        input_mode="message",
        raw_input="next",
    )

    assert turn_input.direct_answer_payload is None
    assert turn_input.language_preference is None


def test_create_finalized_turn_context_keeps_single_response_contract() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="answered",
        updated_answer_record={"answers": [{"question_id": "question-01", "input_value": "22"}]},
        updated_question_states={"question-01": {"status": "answered"}},
        current_question_id="question-01",
        next_question={"question_id": "question-02", "title": "Next"},
        finalized=False,
        response_language="zh-CN",
        response_facts={"recorded_question_ids": ["question-01"]},
    )

    assert finalized.turn_outcome == "answered"
    assert finalized.response_language == "zh-CN"
    assert list(finalized.to_response_payload().keys()) == ["assistant_message"]


def test_calculate_progress_percent_counts_partial_once_per_question() -> None:
    progress_percent = calculate_progress_percent(
        answered_question_ids=["question-01"],
        partial_question_ids=["question-01", "question-02"],
        question_count=4,
        finalized=False,
    )

    assert progress_percent == 37.5


def test_calculate_progress_percent_handles_empty_and_completed_states() -> None:
    assert (
        calculate_progress_percent(
            answered_question_ids=[],
            partial_question_ids=[],
            question_count=0,
            finalized=False,
        )
        == 0.0
    )
    assert (
        calculate_progress_percent(
            answered_question_ids=["question-01"],
            partial_question_ids=[],
            question_count=4,
            finalized=True,
        )
        == 100.0
    )


def test_merge_graph_state_keeps_opaque_llm_provider(question_catalog: dict) -> None:
    class _OpaqueProvider:
        def __init__(self) -> None:
            self._lock = threading.RLock()

    graph_state = create_graph_state(
        session_id="session-opaque",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    provider = _OpaqueProvider()
    graph_state["runtime"]["llm_provider"] = provider

    merged = merge_graph_state(
        graph_state,
        {"turn": {"main_branch": "content"}},
    )

    assert merged["runtime"]["llm_provider"] is provider
    assert merged["turn"]["main_branch"] == "content"
