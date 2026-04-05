"""Tests for standalone gRPC server bootstrap."""

from __future__ import annotations

from somni_graph_quiz.app.settings import GraphQuizSettings
from somni_graph_quiz.adapters.grpc.server import create_grpc_server, serve_grpc


def test_create_grpc_server_registers_quiz_service(monkeypatch) -> None:
    captured: dict = {}

    def _fake_add_servicer_to_server(servicer, server) -> None:
        captured["servicer"] = servicer
        captured["server"] = server

    monkeypatch.setattr(
        "somni_quiz_ai.grpc.generated.somni_quiz_pb2_grpc.add_QuizServiceServicer_to_server",
        _fake_add_servicer_to_server,
    )

    server = create_grpc_server()

    assert server is captured["server"]
    assert captured["servicer"].__class__.__name__ == "QuizServiceServicer"


def test_serve_grpc_binds_configured_address(monkeypatch) -> None:
    events: list[tuple[str, str | None]] = []

    class _FakeServer:
        def add_insecure_port(self, address: str) -> None:
            events.append(("bind", address))

        def start(self) -> None:
            events.append(("start", None))

    fake_server = _FakeServer()
    settings = GraphQuizSettings(grpc_host="127.0.0.1", grpc_port=19001)

    monkeypatch.setattr(
        "somni_graph_quiz.adapters.grpc.server.create_grpc_server",
        lambda incoming_settings=None: fake_server,
    )

    server = serve_grpc(settings)

    assert server is fake_server
    assert events == [("bind", "127.0.0.1:19001"), ("start", None)]
