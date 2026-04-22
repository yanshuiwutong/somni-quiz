"""Streamlit controller."""

from __future__ import annotations

from dataclasses import dataclass

from somni_graph_quiz.adapters.streamlit.mapper import (
    build_streamlit_view,
    map_streamlit_questionnaire_to_catalog,
)
from somni_graph_quiz.app.bootstrap import apply_runtime_dependencies
from somni_graph_quiz.app.settings import GraphQuizSettings
from somni_graph_quiz.contracts.graph_state import create_graph_state
from somni_graph_quiz.contracts.question_catalog import get_question
from somni_graph_quiz.contracts.turn_input import TurnInput
from somni_graph_quiz.contracts.turn_result import calculate_progress_percent
from somni_graph_quiz.runtime.engine import GraphRuntimeEngine


@dataclass
class StreamlitSession:
    """In-memory session container for the Streamlit adapter."""

    graph_state: dict
    chat_history: list[dict]
    quiz_mode: str
    language_preference: str


class StreamlitQuizController:
    """Minimal Streamlit adapter over the graph runtime."""

    _SUPPORTED_ANSWER_STATUS_CODES = {
        "NOT_RECORDED",
        "RECORDED",
        "PARTIAL",
        "UPDATED",
    }

    def __init__(self) -> None:
        self._engine = GraphRuntimeEngine()
        self._sessions: dict[str, StreamlitSession] = {}

    def initialize_session(
        self,
        *,
        session_id: str,
        questionnaire: list[dict],
        language_preference: str,
        quiz_mode: str,
        default_city: str = "",
    ) -> dict:
        snapshot = self._sessions.get(session_id)
        if snapshot is not None:
            apply_runtime_dependencies(snapshot.graph_state)
            return self._build_initialized_view(
                session_id=session_id,
                session=snapshot,
            )

        question_catalog = map_streamlit_questionnaire_to_catalog(questionnaire)
        graph_state = create_graph_state(
            session_id=session_id,
            channel="streamlit",
            quiz_mode=quiz_mode,
            question_catalog=question_catalog,
            language_preference=language_preference,
            default_city=default_city,
        )
        apply_runtime_dependencies(graph_state)
        current_question = question_catalog["question_index"][graph_state["session_memory"]["current_question_id"]]
        assistant_message = current_question["title"]
        chat_history = [{"role": "assistant", "content": assistant_message}]
        self._sessions[session_id] = StreamlitSession(
            graph_state=graph_state,
            chat_history=chat_history,
            quiz_mode=quiz_mode,
            language_preference=language_preference,
        )
        return build_streamlit_view(
            success=True,
            session_id=session_id,
            initialized=True,
            assistant_message=assistant_message,
            answer_record={"answers": []},
            pending_question=current_question,
            finalized=False,
            final_result=None,
            answer_status_code="NOT_RECORDED",
            progress_percent=calculate_progress_percent(
                answered_question_ids=graph_state["session_memory"].get("answered_question_ids", []),
                partial_question_ids=graph_state["session_memory"].get("partial_question_ids", []),
                question_count=len(question_catalog.get("question_order", [])),
                finalized=False,
            ),
            quiz_mode=quiz_mode,
            chat_history=chat_history,
        )

    def submit_message(self, *, session_id: str, message: str) -> dict:
        session = self._sessions.get(session_id)
        if session is None:
            return self._build_missing_session_view(session_id=session_id)
        session.chat_history.append({"role": "user", "content": message})
        result = self._engine.run_turn(
            session.graph_state,
            TurnInput(
                session_id=session_id,
                channel="streamlit",
                input_mode="message",
                raw_input=message,
                language_preference=session.language_preference,
            ),
        )
        session.graph_state = result["updated_graph_state"]
        session.chat_history.append({"role": "assistant", "content": result["assistant_message"]})
        return build_streamlit_view(
            success=True,
            session_id=session_id,
            initialized=None,
            assistant_message=result["assistant_message"],
            answer_record=result["answer_record"],
            pending_question=result["pending_question"],
            finalized=result["finalized"],
            final_result=result["final_result"],
            answer_status_code=self._resolve_answer_status_code(session.graph_state),
            progress_percent=float(result.get("progress_percent", 0.0)),
            quiz_mode=session.quiz_mode,
            chat_history=list(session.chat_history),
        )

    def submit_direct_answer(self, *, session_id: str, answer: dict) -> dict:
        session = self._sessions.get(session_id)
        if session is None:
            return self._build_missing_session_view(session_id=session_id)
        user_content = answer.get("input_value") or " ".join(answer.get("selected_options", []))
        session.chat_history.append({"role": "user", "content": user_content})
        result = self._engine.run_turn(
            session.graph_state,
            TurnInput(
                session_id=session_id,
                channel="streamlit",
                input_mode="direct_answer",
                raw_input=user_content,
                direct_answer_payload=answer,
                language_preference=session.language_preference,
            ),
        )
        session.graph_state = result["updated_graph_state"]
        session.chat_history.append({"role": "assistant", "content": result["assistant_message"]})
        return build_streamlit_view(
            success=True,
            session_id=session_id,
            initialized=None,
            assistant_message=result["assistant_message"],
            answer_record=result["answer_record"],
            pending_question=result["pending_question"],
            finalized=result["finalized"],
            final_result=result["final_result"],
            answer_status_code=self._resolve_answer_status_code(session.graph_state),
            progress_percent=float(result.get("progress_percent", 0.0)),
            quiz_mode=session.quiz_mode,
            chat_history=list(session.chat_history),
        )

    def refresh_runtime(
        self,
        *,
        session_id: str,
        settings: GraphQuizSettings | None = None,
    ) -> None:
        """Re-inject runtime dependencies for an existing session."""
        session = self._sessions[session_id]
        apply_runtime_dependencies(session.graph_state, settings=settings)

    def _build_initialized_view(
        self,
        *,
        session_id: str,
        session: StreamlitSession,
    ) -> dict:
        graph_state = session.graph_state
        session_memory = graph_state["session_memory"]
        question_catalog = graph_state["question_catalog"]
        pending_question = get_question(question_catalog, session_memory.get("current_question_id"))
        finalized = bool(graph_state["runtime"].get("finalized", False))
        assistant_message = self._current_assistant_message(
            pending_question=pending_question,
            language_preference=session.language_preference,
        )
        return build_streamlit_view(
            success=True,
            session_id=session_id,
            initialized=True,
            assistant_message=assistant_message,
            answer_record={"answers": list(session_memory.get("answered_records", {}).values())},
            pending_question=pending_question,
            finalized=finalized,
            final_result=None,
            answer_status_code="NOT_RECORDED",
            progress_percent=calculate_progress_percent(
                answered_question_ids=session_memory.get("answered_question_ids", []),
                partial_question_ids=session_memory.get("partial_question_ids", []),
                question_count=len(question_catalog.get("question_order", [])),
                finalized=finalized,
            ),
            quiz_mode=session.quiz_mode,
            chat_history=list(session.chat_history),
        )

    def _build_missing_session_view(self, *, session_id: str) -> dict:
        return build_streamlit_view(
            success=False,
            session_id=session_id,
            initialized=False,
            assistant_message="Session not initialized. Call initialize_session first.",
            answer_record={"answers": []},
            pending_question=None,
            finalized=False,
            final_result=None,
            answer_status_code="NOT_RECORDED",
            progress_percent=0.0,
            quiz_mode="",
            chat_history=[],
        )

    def _current_assistant_message(
        self,
        *,
        pending_question: dict | None,
        language_preference: str,
    ) -> str:
        if pending_question is not None:
            return pending_question.get("title", "")
        if language_preference.startswith("en"):
            return "Quiz already completed."
        return "问卷已完成。"

    def _resolve_answer_status_code(self, graph_state: dict) -> str:
        recent_turns = graph_state["session_memory"].get("recent_turns", [])
        recent_turn = recent_turns[-1] if recent_turns else None
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
                if isinstance(override, str) and override in self._SUPPORTED_ANSWER_STATUS_CODES:
                    return override
            if recent_turn.get("partial_question_ids"):
                return "PARTIAL"
            if recent_turn.get("modified_question_ids"):
                return "UPDATED"
            if recent_turn.get("recorded_question_ids"):
                return "RECORDED"
            turn_outcome = recent_turn.get("turn_outcome")
            if turn_outcome == "partial_recorded":
                return "PARTIAL"
            if turn_outcome in {"modified", "undo_applied"}:
                return "UPDATED"
            if turn_outcome == "answered":
                return "RECORDED"
        return "NOT_RECORDED"
