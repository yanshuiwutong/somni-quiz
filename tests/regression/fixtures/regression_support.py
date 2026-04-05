"""Helpers for structured regression cases."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from somni_quiz_ai.grpc.generated import somni_quiz_pb2

from somni_graph_quiz.adapters.grpc.service import GrpcQuizService
from somni_graph_quiz.adapters.streamlit.mapper import map_streamlit_questionnaire_to_catalog
from somni_graph_quiz.adapters.streamlit.controller import StreamlitQuizController
from somni_graph_quiz.app.streamlit_app import build_default_questionnaire
from somni_graph_quiz.contracts.graph_state import create_graph_state
from somni_graph_quiz.contracts.turn_input import TurnInput
from somni_graph_quiz.runtime.engine import GraphRuntimeEngine


REGRESSION_ROOT = Path(__file__).resolve().parents[1]


def load_case(path: Path) -> dict:
    """Load a regression case from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


def runtime_question_catalog() -> dict:
    """Return the shared regression question catalog."""
    questionnaire = build_default_questionnaire()
    return map_streamlit_questionnaire_to_catalog(questionnaire)


def apply_initial_state(graph_state: dict, initial_state: dict | None) -> dict:
    """Apply an initial session-memory patch to a graph state."""
    if not initial_state:
        return graph_state
    updated = deepcopy(graph_state)
    _merge(updated["session_memory"], initial_state)
    return updated


def execute_runtime_case(case: dict) -> tuple[dict, list[dict]]:
    """Execute a runtime regression case."""
    graph_state = create_graph_state(
        session_id=f'{case["case_id"]}-session',
        channel="grpc",
        quiz_mode=case.get("quiz_mode", "dynamic"),
        question_catalog=runtime_question_catalog(),
        language_preference=case.get("language", "zh-CN"),
    )
    graph_state = apply_initial_state(graph_state, case.get("initial_state"))
    engine = GraphRuntimeEngine()
    turn_results: list[dict] = []
    for turn in case["turns"]:
        turn_input = TurnInput(
            session_id=f'{case["case_id"]}-session',
            channel="grpc",
            input_mode=turn["input_mode"],
            raw_input=turn["raw_input"],
            direct_answer_payload=turn.get("direct_answer_payload"),
            language_preference=case.get("language", "zh-CN"),
        )
        result = engine.run_turn(graph_state, turn_input)
        turn_results.append(result)
        graph_state = result["updated_graph_state"]
    return graph_state, turn_results


def execute_grpc_case(case: dict) -> somni_quiz_pb2.ChatQuizResponse:
    """Execute a gRPC regression case and return the final response."""
    service = GrpcQuizService()
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id=case["case_id"],
            language=case.get("language", "zh-CN"),
            questionnaire=[
                somni_quiz_pb2.BusinessQuestion(
                    question_id=question["question_id"],
                    title=question["title"],
                    input_type=question["input_type"],
                )
                for question in runtime_question_catalog()["question_index"].values()
            ],
            quiz_mode=case.get("quiz_mode", "dynamic"),
        ),
        context=None,
    )
    response = None
    for turn in case["turns"]:
        if turn["input_mode"] == "direct_answer":
            request = somni_quiz_pb2.ChatQuizRequest(
                session_id=case["case_id"],
                direct_answer=somni_quiz_pb2.DirectAnswer(
                    question_id=turn["direct_answer_payload"]["question_id"],
                    selected_options=turn["direct_answer_payload"].get("selected_options", []),
                    input_value=turn["direct_answer_payload"].get("input_value", ""),
                ),
            )
        else:
            request = somni_quiz_pb2.ChatQuizRequest(
                session_id=case["case_id"],
                message=turn["raw_input"],
            )
        response = service.ChatQuiz(request, context=None)
    assert response is not None
    return response


def execute_streamlit_case(case: dict) -> dict:
    """Execute a Streamlit regression case and return the final view."""
    controller = StreamlitQuizController()
    session_id = case["case_id"]
    controller.initialize_session(
        session_id=session_id,
        questionnaire=list(runtime_question_catalog()["question_index"].values()),
        language_preference=case.get("language", "zh-CN"),
        quiz_mode=case.get("quiz_mode", "dynamic"),
    )
    if case.get("initial_state"):
        session = controller._sessions[session_id]
        session.graph_state = apply_initial_state(session.graph_state, case["initial_state"])
    view = None
    for turn in case["turns"]:
        if turn["input_mode"] == "direct_answer":
            view = controller.submit_direct_answer(
                session_id=session_id,
                answer=turn["direct_answer_payload"],
            )
        else:
            view = controller.submit_message(
                session_id=session_id,
                message=turn["raw_input"],
            )
    assert view is not None
    return view


def assert_runtime_expectations(graph_state: dict, turn_results: list[dict], expected: dict) -> None:
    """Assert common structured expectations against runtime state."""
    session_memory = graph_state["session_memory"]
    final_turn = turn_results[-1]
    assert session_memory["answered_question_ids"] == expected["answered_question_ids"]
    assert session_memory["partial_question_ids"] == expected["partial_question_ids"]
    assert session_memory["skipped_question_ids"] == expected["skipped_question_ids"]
    assert session_memory["current_question_id"] == expected["pending_question_id"]
    assert (final_turn["pending_question"] or {}).get("question_id") == expected["pending_question_id"]
    if expected["clarification_needed"]:
        assert session_memory["answered_question_ids"] == expected["answered_question_ids"]
    if expected["modified_question_ids"]:
        previous = session_memory.get("previous_answer_record") or {}
        assert sorted(previous.keys()) == sorted(expected["modified_question_ids"])
    if "expected_answer_record" in expected:
        answered_records = session_memory.get("answered_records", {})
        for question_id, answer_expectation in expected["expected_answer_record"].items():
            answer = answered_records[question_id]
            for key, value in answer_expectation.items():
                assert answer[key] == value
    if "expected_previous_answer_record" in expected:
        previous_record = session_memory.get("previous_answer_record") or {}
        for question_id, answer_expectation in expected["expected_previous_answer_record"].items():
            answer = previous_record[question_id]
            for key, value in answer_expectation.items():
                assert answer[key] == value
    if "expected_response_contains" in expected:
        expected_tokens = expected["expected_response_contains"]
        if isinstance(expected_tokens, str):
            expected_tokens = [expected_tokens]
        for token in expected_tokens:
            assert token in final_turn["assistant_message"]


def assert_grpc_expectations(response: somni_quiz_pb2.ChatQuizResponse, expected: dict) -> None:
    """Assert structured expectations against a gRPC response."""
    assert response.pending_question.question_id == expected["pending_question_id"]
    assert [item.question_id for item in response.answer_record.answers] == expected["answered_question_ids"]
    if "expected_answer_record" in expected:
        answered_records = {
            item.question_id: {
                "selected_options": list(item.direct_answer.selected_options),
                "input_value": item.direct_answer.input_value,
                "field_updates": {
                    key: value
                    for key, value in {
                        "bedtime": item.value.bedtime,
                        "wake_time": item.value.wake_time,
                    }.items()
                    if value
                },
            }
            for item in response.answer_record.answers
        }
        for question_id, answer_expectation in expected["expected_answer_record"].items():
            answer = answered_records[question_id]
            for key, value in answer_expectation.items():
                assert answer[key] == value
    if "expected_response_contains" in expected:
        expected_tokens = expected["expected_response_contains"]
        if isinstance(expected_tokens, str):
            expected_tokens = [expected_tokens]
        for token in expected_tokens:
            assert token in response.assistant_message


def assert_streamlit_expectations(view: dict, expected: dict) -> None:
    """Assert structured expectations against a Streamlit view model."""
    assert view["pending_question"]["question_id"] == expected["pending_question_id"]
    assert [item["question_id"] for item in view["answer_record"]["answers"]] == expected["answered_question_ids"]
    if "expected_answer_record" in expected:
        answered_records = {
            item["question_id"]: {
                "selected_options": list(item.get("selected_options", [])),
                "input_value": item.get("input_value", ""),
                "field_updates": dict(item.get("field_updates", {})),
            }
            for item in view["answer_record"]["answers"]
        }
        for question_id, answer_expectation in expected["expected_answer_record"].items():
            answer = answered_records[question_id]
            for key, value in answer_expectation.items():
                assert answer[key] == value
    if "expected_response_contains" in expected:
        expected_tokens = expected["expected_response_contains"]
        if isinstance(expected_tokens, str):
            expected_tokens = [expected_tokens]
        for token in expected_tokens:
            assert token in view["assistant_message"]


def _merge(target: dict, patch: dict) -> None:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = deepcopy(value)
