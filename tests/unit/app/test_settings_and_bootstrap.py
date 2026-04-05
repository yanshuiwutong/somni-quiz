"""Tests for runtime settings and bootstrap wiring."""

from __future__ import annotations

from somni_graph_quiz.app.bootstrap import apply_runtime_dependencies, build_llm_provider
from somni_graph_quiz.app.settings import GraphQuizSettings
from somni_graph_quiz.llm.client import RealLLMProvider


def test_graph_quiz_settings_loads_doubao_env(monkeypatch) -> None:
    monkeypatch.setenv("SOMNI_LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    monkeypatch.setenv("SOMNI_LLM_API_KEY", "test-api-key")
    monkeypatch.setenv("SOMNI_LLM_MODEL", "doubao-seed-2-0-mini-260215")
    monkeypatch.setenv("SOMNI_LLM_TEMPERATURE", "0.1")
    monkeypatch.setenv("SOMNI_LLM_TIMEOUT", "45")
    monkeypatch.setenv("SOMNI_GRPC_HOST", "0.0.0.0")
    monkeypatch.setenv("SOMNI_GRPC_PORT", "19000")

    settings = GraphQuizSettings()

    assert settings.llm_base_url == "https://ark.cn-beijing.volces.com/api/v3"
    assert settings.llm_api_key == "test-api-key"
    assert settings.llm_model == "doubao-seed-2-0-mini-260215"
    assert settings.llm_timeout == 45
    assert settings.grpc_host == "0.0.0.0"
    assert settings.grpc_port == 19000
    assert settings.llm_ready is True


def test_build_llm_provider_returns_none_when_llm_not_configured() -> None:
    settings = GraphQuizSettings(
        llm_base_url="",
        llm_api_key="",
        llm_model="",
    )

    provider = build_llm_provider(settings)

    assert provider is None


def test_graph_quiz_settings_reports_missing_llm_keys() -> None:
    settings = GraphQuizSettings(
        llm_base_url="",
        llm_api_key="test-key",
        llm_model="",
    )

    assert settings.missing_llm_config_keys == [
        "SOMNI_LLM_BASE_URL",
        "SOMNI_LLM_MODEL",
    ]


def test_apply_runtime_dependencies_injects_real_provider(monkeypatch) -> None:
    settings = GraphQuizSettings(
        llm_base_url="https://ark.cn-beijing.volces.com/api/v3",
        llm_api_key="test-api-key",
        llm_model="doubao-seed-2-0-mini-260215",
        llm_temperature=0.2,
        llm_timeout=30,
        llm_reasoning_effort="minimal",
    )
    graph_state = {
        "runtime": {
            "llm_available": True,
            "finalized": False,
            "current_turn_index": 0,
            "fallback_used": False,
        }
    }

    monkeypatch.setattr(
        "somni_graph_quiz.app.bootstrap.build_llm_provider",
        lambda incoming_settings: RealLLMProvider(
            base_url=incoming_settings.llm_base_url,
            api_key=incoming_settings.llm_api_key,
            model=incoming_settings.llm_model,
            temperature=incoming_settings.llm_temperature,
            timeout=incoming_settings.llm_timeout,
            reasoning_effort=incoming_settings.llm_reasoning_effort,
        ),
    )

    apply_runtime_dependencies(graph_state, settings=settings)

    assert isinstance(graph_state["runtime"]["llm_provider"], RealLLMProvider)
    assert graph_state["runtime"]["llm_available"] is True
