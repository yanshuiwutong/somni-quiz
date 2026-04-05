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
from somni_graph_quiz.contracts.turn_input import TurnInput
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
    ) -> dict:
        question_catalog = map_streamlit_questionnaire_to_catalog(questionnaire)
        graph_state = create_graph_state(
            session_id=session_id,
            channel="streamlit",
            quiz_mode=quiz_mode,
            question_catalog=question_catalog,
            language_preference=language_preference,
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
            session_id=session_id,
            assistant_message=assistant_message,
            answer_record={"answers": []},
            pending_question=current_question,
            finalized=False,
            final_result=None,
            quiz_mode=quiz_mode,
            chat_history=chat_history,
        )

    def submit_message(self, *, session_id: str, message: str) -> dict:
        session = self._sessions[session_id]
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
            session_id=session_id,
            assistant_message=result["assistant_message"],
            answer_record=result["answer_record"],
            pending_question=result["pending_question"],
            finalized=result["finalized"],
            final_result=result["final_result"],
            quiz_mode=session.quiz_mode,
            chat_history=list(session.chat_history),
        )

    def submit_direct_answer(self, *, session_id: str, answer: dict) -> dict:
        session = self._sessions[session_id]
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
            session_id=session_id,
            assistant_message=result["assistant_message"],
            answer_record=result["answer_record"],
            pending_question=result["pending_question"],
            finalized=result["finalized"],
            final_result=result["final_result"],
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
