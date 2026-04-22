"""Tests for the real-LLM check script wrapper."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_script_module():
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "check_real_llm.py"
    spec = importlib.util.spec_from_file_location("check_real_llm_script", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_configure_stdout_uses_utf8_when_reconfigure_available() -> None:
    module = _load_script_module()
    captured: list[dict[str, object]] = []

    class _FakeStdout:
        def reconfigure(self, **kwargs) -> None:
            captured.append(kwargs)

    module._configure_stdout(_FakeStdout())

    assert captured == [{"encoding": "utf-8", "errors": "replace"}]
