"""gRPC service adapter."""

from __future__ import annotations

from dataclasses import dataclass

from somni_quiz_ai.grpc.generated import somni_quiz_pb2

from somni_graph_quiz.adapters.grpc.mapper import (
    build_answer_record_message,
    build_final_result_message,
    build_pending_question_message,
    map_chat_request_to_turn_input,
    map_questionnaire_to_catalog,
)
from somni_graph_quiz.app.bootstrap import apply_runtime_dependencies
from somni_graph_quiz.contracts.graph_state import create_graph_state
from somni_graph_quiz.runtime.engine import GraphRuntimeEngine


@dataclass
class SessionSnapshot:
    """In-memory session snapshot for the minimal adapter."""

    graph_state: dict
    quiz_mode: str
    language: str


class GrpcQuizService:
    """Minimal in-memory gRPC service adapter backed by the graph runtime."""

    def __init__(self) -> None:
        self._engine = GraphRuntimeEngine()
        self._sessions: dict[str, SessionSnapshot] = {}

    def InitQuiz(  # noqa: N802
        self,
        request: somni_quiz_pb2.InitQuizRequest,
        context: object | None = None,
    ) -> somni_quiz_pb2.InitQuizResponse:
        question_catalog = map_questionnaire_to_catalog(list(request.questionnaire))
        graph_state = create_graph_state(
            session_id=request.session_id,
            channel="grpc",
            quiz_mode=request.quiz_mode or "dynamic",
            question_catalog=question_catalog,
            language_preference=request.language or "zh-CN",
        )
        apply_runtime_dependencies(graph_state)
        self._sessions[request.session_id] = SessionSnapshot(
            graph_state=graph_state,
            quiz_mode=request.quiz_mode or "dynamic",
            language=request.language or "zh-CN",
        )
        pending_question = build_pending_question_message(
            question_catalog["question_index"].get(graph_state["session_memory"]["current_question_id"])
        )
        return somni_quiz_pb2.InitQuizResponse(
            success=True,
            session_id=request.session_id,
            initialized=True,
            assistant_message=pending_question.title,
            pending_question=pending_question,
            answer_record=somni_quiz_pb2.AnswerRecord(answer_id="", answers=[]),
            quiz_mode=request.quiz_mode or "dynamic",
        )

    def ChatQuiz(  # noqa: N802
        self,
        request: somni_quiz_pb2.ChatQuizRequest,
        context: object | None = None,
    ) -> somni_quiz_pb2.ChatQuizResponse:
        snapshot = self._sessions[request.session_id]
        turn_input = map_chat_request_to_turn_input(
            request,
            language_preference=snapshot.language,
        )
        result = self._engine.run_turn(snapshot.graph_state, turn_input)
        snapshot.graph_state = result["updated_graph_state"]
        return somni_quiz_pb2.ChatQuizResponse(
            success=True,
            session_id=request.session_id,
            assistant_message=result["assistant_message"],
            pending_question=build_pending_question_message(result["pending_question"]),
            finalized=result["finalized"],
            answer_record=build_answer_record_message(result["answer_record"]),
            final_result=build_final_result_message(result["final_result"]),
            quiz_mode=snapshot.quiz_mode,
        )
