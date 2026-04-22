"""Standalone gRPC server bootstrap for somni-graph-quiz."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import logging
from pathlib import Path

import grpc

from somni_quiz_ai import grpc as somni_quiz_grpc_pkg
from somni_quiz_ai.grpc.generated import somni_quiz_pb2_grpc

from somni_graph_quiz.adapters.grpc.service import GrpcQuizService
from somni_graph_quiz.app.settings import GraphQuizSettings, get_settings
from somni_graph_quiz.nodes.layer2.content import understand as content_understand_module


_MAX_WORKERS = 8
_DIAGNOSTIC_LOGGER = logging.getLogger("somni_graph_quiz.diagnostics.grpc_runtime")


class QuizServiceServicer(somni_quiz_pb2_grpc.QuizServiceServicer):
    """Transport-facing servicer delegating to the in-memory graph service."""

    def __init__(self, service: GrpcQuizService | None = None) -> None:
        self._service = service or GrpcQuizService()

    def InitQuiz(self, request, context):  # noqa: N802
        return self._service.InitQuiz(request, context)

    def ChatQuiz(self, request, context):  # noqa: N802
        return self._service.ChatQuiz(request, context)


def create_grpc_server(settings: GraphQuizSettings | None = None) -> grpc.Server:
    """Create a gRPC server with the quiz servicer registered."""
    _ = settings
    server = grpc.server(ThreadPoolExecutor(max_workers=_MAX_WORKERS))
    somni_quiz_pb2_grpc.add_QuizServiceServicer_to_server(
        QuizServiceServicer(),
        server,
    )
    return server


def serve_grpc(settings: GraphQuizSettings | None = None) -> grpc.Server:
    """Bind and start the standalone gRPC server."""
    runtime_settings = settings or get_settings()
    server = create_grpc_server(runtime_settings)
    bind_address = f"{runtime_settings.grpc_host}:{runtime_settings.grpc_port}"
    bound_port = server.add_insecure_port(bind_address)
    if bound_port == 0:
        raise RuntimeError(f"Failed to bind gRPC server to {bind_address}")
    server.start()
    _log_runtime_bootstrap(bind_address)
    return server


def _log_runtime_bootstrap(bind_address: str) -> None:
    payload = {
        "diagnostic": "grpc_runtime",
        "event": "grpc_server_started",
        "bind_address": bind_address,
        "server_module_path": _module_path(__file__),
        "content_understand_module_path": _module_path(getattr(content_understand_module, "__file__", None)),
        "vendored_grpc_package_path": _module_path(getattr(somni_quiz_grpc_pkg, "__file__", None)),
        "generated_servicer_module_path": _module_path(getattr(somni_quiz_pb2_grpc, "__file__", None)),
    }
    _DIAGNOSTIC_LOGGER.warning(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _module_path(value: str | None) -> str | None:
    if not value:
        return None
    return str(Path(value).resolve())
