"""Run the standalone somni-graph-quiz gRPC server."""

from somni_graph_quiz.adapters.grpc.server import serve_grpc
from somni_graph_quiz.app.settings import get_settings


def main() -> None:
    server = serve_grpc(get_settings())
    server.wait_for_termination()


if __name__ == "__main__":
    main()
