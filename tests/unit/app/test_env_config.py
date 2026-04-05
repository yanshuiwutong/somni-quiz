"""Tests for runtime env persistence helpers."""

from __future__ import annotations

from pathlib import Path

from somni_graph_quiz.app.env_config import write_runtime_settings_to_env
from somni_graph_quiz.app.settings import GraphQuizSettings


def test_write_runtime_settings_to_env_updates_expected_keys_and_preserves_other_lines(
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "# existing comment",
                "CUSTOM_KEEP=1",
                "SOMNI_LLM_BASE_URL=https://old.example.com/v1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    settings = GraphQuizSettings.model_validate(
        {
            "llm_base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "llm_api_key": "test-secret",
            "llm_model": "doubao-seed-2-0-mini-260215",
            "llm_temperature": 0.35,
            "llm_reasoning_effort": "high",
            "llm_timeout": 45,
            "grpc_host": "127.0.0.1",
            "grpc_port": 19001,
        }
    )

    write_runtime_settings_to_env(settings, env_path)

    text = env_path.read_text(encoding="utf-8")
    assert "# existing comment" in text
    assert "CUSTOM_KEEP=1" in text
    assert "SOMNI_LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3" in text
    assert "SOMNI_LLM_API_KEY=test-secret" in text
    assert "SOMNI_LLM_MODEL=doubao-seed-2-0-mini-260215" in text
    assert "SOMNI_LLM_TEMPERATURE=0.35" in text
    assert "SOMNI_LLM_TIMEOUT=45" in text
    assert "SOMNI_LLM_REASONING_EFFORT=high" in text
    assert "SOMNI_GRPC_HOST=127.0.0.1" in text
    assert "SOMNI_GRPC_PORT=19001" in text
