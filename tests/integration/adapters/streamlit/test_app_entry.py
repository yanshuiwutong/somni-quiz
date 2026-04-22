"""Tests for the standalone Streamlit app entry helpers."""

from __future__ import annotations

from pathlib import Path

from somni_graph_quiz.app.settings import GraphQuizSettings
from somni_graph_quiz.app.streamlit_app import (
    build_default_questionnaire,
    build_runtime_settings,
    initialize_default_view,
    persist_runtime_settings,
)
from somni_graph_quiz.adapters.streamlit.controller import StreamlitQuizController


def test_build_default_questionnaire_returns_9_questions() -> None:
    questionnaire = build_default_questionnaire()

    assert [question["question_id"] for question in questionnaire] == [
        "question-01",
        "question-02",
        "question-03",
        "question-04",
        "question-05",
        "question-06",
        "question-07",
        "question-08",
        "question-09",
    ]


def test_initialize_default_view_uses_streamlit_controller() -> None:
    controller = StreamlitQuizController()

    view = initialize_default_view(
        controller,
        session_id="streamlit-app-1",
        language_preference="zh-CN",
        quiz_mode="dynamic",
    )

    assert view["chat_history"][0]["role"] == "assistant"
    assert view["pending_question"]["question_id"]


def test_build_runtime_settings_prefers_form_state_values() -> None:
    settings = build_runtime_settings(
        {
            "llm_base_url": "https://runtime.example.com/v1",
            "llm_api_key": "runtime-key",
            "llm_model": "runtime-model",
            "llm_temperature": 0.6,
            "llm_reasoning_effort": "high",
            "llm_timeout": 20,
            "grpc_host": "127.0.0.1",
            "grpc_port": 19002,
        },
        defaults=GraphQuizSettings(),
    )

    assert settings.llm_base_url == "https://runtime.example.com/v1"
    assert settings.llm_api_key == "runtime-key"
    assert settings.llm_model == "runtime-model"
    assert settings.llm_temperature == 0.6
    assert settings.llm_reasoning_effort == "high"
    assert settings.llm_timeout == 20
    assert settings.grpc_port == 19002


def test_persist_runtime_settings_writes_env_and_clears_cache(
    monkeypatch,
    tmp_path: Path,
) -> None:
    cache_cleared: list[bool] = []

    monkeypatch.setattr(
        "somni_graph_quiz.app.streamlit_app.get_settings",
        type("_CachedSettings", (), {"cache_clear": staticmethod(lambda: cache_cleared.append(True))})(),
    )

    settings = persist_runtime_settings(
        {
            "llm_base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "llm_api_key": "saved-key",
            "llm_model": "doubao-online",
            "llm_temperature": 0.2,
            "llm_reasoning_effort": "minimal",
            "llm_timeout": 30,
            "grpc_host": "0.0.0.0",
            "grpc_port": 19000,
        },
        env_path=tmp_path / ".env",
    )

    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert settings.llm_model == "doubao-online"
    assert "SOMNI_LLM_API_KEY=saved-key" in text
    assert cache_cleared == [True]
