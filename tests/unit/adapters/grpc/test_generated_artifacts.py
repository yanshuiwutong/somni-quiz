"""Regression tests for vendored generated gRPC artifacts."""

from __future__ import annotations

from pathlib import Path


def test_generated_grpc_module_stays_compatible_with_grpcio_178() -> None:
    generated_module = Path("src/somni_quiz_ai/grpc/generated/somni_quiz_pb2_grpc.py").read_text(
        encoding="utf-8"
    )

    assert "from . import somni_quiz_pb2 as somni__quiz__pb2" in generated_module
    assert "GRPC_GENERATED_VERSION = '1.78.0'" in generated_module
