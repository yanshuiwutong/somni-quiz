"""Helpers for building runtime prompt and response contexts."""

from __future__ import annotations

from somni_graph_quiz.contracts.question_catalog import get_question


def build_runtime_memory_view(graph_state: dict) -> dict:
    """Build a small runtime-facing memory view."""
    session_memory = graph_state["session_memory"]
    return {
        "current_question_id": session_memory["current_question_id"],
        "pending_question_ids": list(session_memory["pending_question_ids"]),
        "question_states": dict(session_memory["question_states"]),
        "answered_question_ids": list(session_memory["answered_question_ids"]),
        "partial_question_ids": list(session_memory["partial_question_ids"]),
        "skipped_question_ids": list(session_memory["skipped_question_ids"]),
        "clarification_context": session_memory["clarification_context"],
        "pending_weather_query": session_memory.get("pending_weather_query"),
    }


def build_llm_memory_view(graph_state: dict) -> dict:
    """Build a compact LLM-facing memory view."""
    question_catalog = graph_state["question_catalog"]
    session_memory = graph_state["session_memory"]
    answered_summary = [
        {
            "question_id": question_id,
            "input_value": entry["input_value"],
        }
        for question_id, entry in session_memory["answered_records"].items()
    ]
    return {
        "current_question": get_question(question_catalog, session_memory["current_question_id"]),
        "question_summaries": [
            {
                "question_id": question_id,
                "title": question_catalog["question_index"][question_id]["title"],
            }
            for question_id in question_catalog["question_order"]
        ],
        "answered_summary": answered_summary,
        "partial_summary": list(session_memory["pending_partial_answers"].values()),
        "recent_turn_summaries": list(session_memory["recent_turns"]),
        "clarification_context": session_memory["clarification_context"],
        "pending_weather_query": session_memory.get("pending_weather_query"),
    }
