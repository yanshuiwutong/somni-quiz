"""Tests for explicit real-provider diagnostics."""

from __future__ import annotations

from somni_graph_quiz.app.real_llm_check import run_real_llm_check
from somni_graph_quiz.app.settings import GraphQuizSettings


def test_run_real_llm_check_reports_missing_configuration() -> None:
    result = run_real_llm_check(
        GraphQuizSettings(
            llm_base_url="",
            llm_api_key="",
            llm_model="",
        )
    )

    assert result["ready"] is False
    assert result["success"] is False
    assert result["missing_keys"] == [
        "SOMNI_LLM_BASE_URL",
        "SOMNI_LLM_API_KEY",
        "SOMNI_LLM_MODEL",
    ]
    assert result["error"] == "missing_configuration"


def test_run_real_llm_check_invokes_real_provider(monkeypatch) -> None:
    events: list[tuple[str, str]] = []

    class _FakeProvider:
        def generate(self, prompt_key: str, prompt_text: str) -> str:
            events.append((prompt_key, prompt_text))
            return "pong"

    monkeypatch.setattr(
        "somni_graph_quiz.app.real_llm_check.build_llm_provider",
        lambda settings: _FakeProvider(),
    )

    result = run_real_llm_check(
        GraphQuizSettings(
            llm_base_url="https://ark.cn-beijing.volces.com/api/v3",
            llm_api_key="test-key",
            llm_model="doubao-seed-2-0-mini-260215",
        )
    )

    assert result["ready"] is True
    assert result["success"] is True
    assert result["response_preview"] == "pong"
    assert result["error"] is None
    assert events
    assert events[0][0] == "real_provider_check"
