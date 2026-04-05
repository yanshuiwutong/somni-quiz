"""Tests for independent packaging of the new project."""

from __future__ import annotations

from pathlib import Path

from somni_quiz_ai.grpc.generated import somni_quiz_pb2


def test_vendored_proto_module_is_loaded_from_new_project() -> None:
    module_path = Path(somni_quiz_pb2.__file__).resolve()

    assert "somni-graph-quiz" in str(module_path)
    assert module_path.parts[-4:] == ("somni_quiz_ai", "grpc", "generated", "somni_quiz_pb2.py")
