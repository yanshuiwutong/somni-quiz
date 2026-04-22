"""gRPC service adapter."""

from __future__ import annotations

from dataclasses import dataclass

import grpc

from somni_quiz_ai.grpc.generated import somni_quiz_pb2

from somni_graph_quiz.adapters.grpc.mapper import (
    build_answer_record_message,
    build_final_result_message,
    build_pending_question_message,
    derive_answer_status_code,
    map_chat_request_to_turn_input,
    map_questionnaire_to_catalog,
)
from somni_graph_quiz.app.bootstrap import apply_runtime_dependencies
from somni_graph_quiz.contracts.graph_state import create_graph_state
from somni_graph_quiz.contracts.question_catalog import get_question
from somni_graph_quiz.contracts.turn_result import calculate_progress_percent
from somni_graph_quiz.runtime.engine import GraphRuntimeEngine


@dataclass
class SessionSnapshot:
    """In-memory session snapshot for the minimal adapter."""

    graph_state: dict
    quiz_mode: str
    language: str


class GrpcQuizService:
    """Minimal in-memory gRPC service adapter backed by the graph runtime."""

    _SUPPORTED_ANSWER_STATUS_CODES = {
        "NOT_RECORDED",
        "RECORDED",
        "PARTIAL",
        "UPDATED",
    }

    def __init__(self) -> None:
        self._engine = GraphRuntimeEngine()
        self._sessions: dict[str, SessionSnapshot] = {}

    def InitQuiz(  # noqa: N802
        self,
        request: somni_quiz_pb2.InitQuizRequest,
        context: object | None = None,
    ) -> somni_quiz_pb2.InitQuizResponse:
        snapshot = self._sessions.get(request.session_id)
        if snapshot is not None:
            apply_runtime_dependencies(snapshot.graph_state)
            return self._build_init_response(snapshot)

        question_catalog = map_questionnaire_to_catalog(list(request.questionnaire))
        graph_state = create_graph_state(
            session_id=request.session_id,
            channel="grpc",
            quiz_mode=request.quiz_mode or "dynamic",
            question_catalog=question_catalog,
            language_preference=request.language or "zh-CN",
            default_city=request.default_city,
        )
        apply_runtime_dependencies(graph_state)
        self._sessions[request.session_id] = SessionSnapshot(
            graph_state=graph_state,
            quiz_mode=request.quiz_mode or "dynamic",
            language=request.language or "zh-CN",
        )
        return self._build_init_response(self._sessions[request.session_id])

    def ChatQuiz(  # noqa: N802
        self,
        request: somni_quiz_pb2.ChatQuizRequest,
        context: object | None = None,
    ) -> somni_quiz_pb2.ChatQuizResponse:
        snapshot = self._sessions.get(request.session_id)
        if snapshot is None:
            details = "Session not initialized. Call InitQuiz first."
            if context is not None:
                context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                context.set_details(details)
            return somni_quiz_pb2.ChatQuizResponse(
                success=False,
                session_id=request.session_id,
                assistant_message=details,
                answer_status_code="NOT_RECORDED",
            )
        turn_input = map_chat_request_to_turn_input(
            request,
            language_preference=snapshot.language,
        )
        result = self._engine.run_turn(snapshot.graph_state, turn_input)
        snapshot.graph_state = result["updated_graph_state"]
        recent_turns = snapshot.graph_state["session_memory"].get("recent_turns", [])
        recent_turn = recent_turns[-1] if recent_turns else None
        answer_status_code = self._resolve_answer_status_code(recent_turn)
        return somni_quiz_pb2.ChatQuizResponse(
            success=True,
            session_id=request.session_id,
            assistant_message=result["assistant_message"],
            pending_question=build_pending_question_message(result["pending_question"]),
            finalized=result["finalized"],
            answer_record=build_answer_record_message(result["answer_record"]),
            final_result=build_final_result_message(result["final_result"]),
            progress_percent=float(result.get("progress_percent", 0.0)),
            quiz_mode=snapshot.quiz_mode,
            answer_status_code=answer_status_code,
        )

    def _resolve_answer_status_code(self, recent_turn: dict | None) -> str:
        if isinstance(recent_turn, dict):
            direct_override = recent_turn.get("answer_status_override")
            if (
                isinstance(direct_override, str)
                and direct_override in self._SUPPORTED_ANSWER_STATUS_CODES
            ):
                return direct_override
            metadata = recent_turn.get("metadata")
            if isinstance(metadata, dict):
                override = metadata.get("answer_status_override")
                if (
                    isinstance(override, str)
                    and override in self._SUPPORTED_ANSWER_STATUS_CODES
                ):
                    return override
        return derive_answer_status_code(recent_turn)

    def _build_init_response(self, snapshot: SessionSnapshot) -> somni_quiz_pb2.InitQuizResponse:
        graph_state = snapshot.graph_state
        session_memory = graph_state["session_memory"]
        question_catalog = graph_state["question_catalog"]
        pending_question_data = get_question(question_catalog, session_memory.get("current_question_id"))
        pending_question = build_pending_question_message(pending_question_data)
        assistant_message = pending_question.title or self._default_init_message(snapshot)
        return somni_quiz_pb2.InitQuizResponse(
            success=True,
            session_id=graph_state["session"]["session_id"],
            initialized=True,
            assistant_message=assistant_message,
            pending_question=pending_question,
            answer_record=build_answer_record_message(
                {"answers": list(session_memory.get("answered_records", {}).values())}
            ),
            progress_percent=calculate_progress_percent(
                answered_question_ids=session_memory.get("answered_question_ids", []),
                partial_question_ids=session_memory.get("partial_question_ids", []),
                question_count=len(question_catalog.get("question_order", [])),
                finalized=bool(graph_state["runtime"].get("finalized", False)),
            ),
            quiz_mode=snapshot.quiz_mode,
        )

    def _default_init_message(self, snapshot: SessionSnapshot) -> str:
        if snapshot.language.startswith("en"):
            return "Quiz already completed."
        return "问卷已完成。"
