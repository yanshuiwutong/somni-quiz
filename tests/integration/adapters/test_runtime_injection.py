"""Tests for adapter-level runtime dependency injection."""

from __future__ import annotations

from somni_quiz_ai.grpc.generated import somni_quiz_pb2

from somni_graph_quiz.adapters.grpc.service import GrpcQuizService
from somni_graph_quiz.adapters.streamlit.controller import StreamlitQuizController


def test_grpc_service_init_injects_runtime_provider(monkeypatch) -> None:
    service = GrpcQuizService()
    injected_marker = object()
    captured_states: list[dict] = []

    def _fake_apply_runtime_dependencies(graph_state: dict, settings=None) -> None:
        graph_state["runtime"]["llm_provider"] = injected_marker
        captured_states.append(graph_state)

    monkeypatch.setattr(
        "somni_graph_quiz.adapters.grpc.service.apply_runtime_dependencies",
        _fake_apply_runtime_dependencies,
    )

    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="session-inject-grpc",
            language="zh-CN",
            questionnaire=[
                somni_quiz_pb2.BusinessQuestion(
                    question_id="question-01",
                    title="Age",
                    input_type="text",
                )
            ],
            quiz_mode="dynamic",
        ),
        context=None,
    )

    assert captured_states
    assert service._sessions["session-inject-grpc"].graph_state["runtime"]["llm_provider"] is injected_marker


def test_streamlit_controller_init_injects_runtime_provider(monkeypatch) -> None:
    controller = StreamlitQuizController()
    injected_marker = object()
    captured_states: list[dict] = []

    def _fake_apply_runtime_dependencies(graph_state: dict, settings=None) -> None:
        graph_state["runtime"]["llm_provider"] = injected_marker
        captured_states.append(graph_state)

    monkeypatch.setattr(
        "somni_graph_quiz.adapters.streamlit.controller.apply_runtime_dependencies",
        _fake_apply_runtime_dependencies,
    )

    controller.initialize_session(
        session_id="session-inject-streamlit",
        questionnaire=[
            {
                "question_id": "question-01",
                "title": "Age",
                "input_type": "text",
                "tags": [],
                "options": [],
            }
        ],
        language_preference="zh-CN",
        quiz_mode="dynamic",
    )

    assert captured_states
    assert controller._sessions["session-inject-streamlit"].graph_state["runtime"]["llm_provider"] is injected_marker
