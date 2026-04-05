"""Standalone gRPC server bootstrap for somni-graph-quiz."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import grpc

from somni_quiz_ai.grpc.generated import somni_quiz_pb2_grpc

from somni_graph_quiz.adapters.grpc.service import GrpcQuizService
from somni_graph_quiz.app.settings import GraphQuizSettings, get_settings


_MAX_WORKERS = 8


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
    server.add_insecure_port(f"{runtime_settings.grpc_host}:{runtime_settings.grpc_port}")
    server.start()
    return server
