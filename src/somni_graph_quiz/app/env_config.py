"""Helpers for persisting runtime settings into the standalone .env."""

from __future__ import annotations

from pathlib import Path

from somni_graph_quiz.app.settings import GraphQuizSettings


def write_runtime_settings_to_env(settings: GraphQuizSettings, env_path: Path) -> None:
    """Persist runtime-editable settings while preserving unrelated lines."""
    env_path.parent.mkdir(parents=True, exist_ok=True)
    existing_lines = []
    if env_path.exists():
        existing_lines = env_path.read_text(encoding="utf-8").splitlines()

    replacements = dict(_runtime_env_pairs(settings))
    updated_lines: list[str] = []
    seen_keys: set[str] = set()

    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            updated_lines.append(line)
            continue
        key, _value = line.split("=", 1)
        key = key.strip()
        if key in replacements:
            updated_lines.append(f"{key}={_render_env_value(replacements[key])}")
            seen_keys.add(key)
            continue
        updated_lines.append(line)

    for key, value in _runtime_env_pairs(settings):
        if key not in seen_keys:
            updated_lines.append(f"{key}={_render_env_value(value)}")

    env_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")


def _runtime_env_pairs(settings: GraphQuizSettings) -> list[tuple[str, str]]:
    return [
        ("SOMNI_LLM_BASE_URL", settings.llm_base_url),
        ("SOMNI_LLM_API_KEY", settings.llm_api_key),
        ("SOMNI_LLM_MODEL", settings.llm_model),
        ("SOMNI_LLM_TEMPERATURE", _format_float(settings.llm_temperature)),
        ("SOMNI_LLM_TIMEOUT", str(settings.llm_timeout)),
        ("SOMNI_LLM_REASONING_EFFORT", settings.llm_reasoning_effort),
        ("SOMNI_GRPC_HOST", settings.grpc_host),
        ("SOMNI_GRPC_PORT", str(settings.grpc_port)),
    ]


def _format_float(value: float) -> str:
    return f"{value:g}"


def _render_env_value(value: str) -> str:
    if value == "":
        return ""
    if any(ch.isspace() for ch in value) or "#" in value:
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    return value
