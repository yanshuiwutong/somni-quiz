"""Graph state contract."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

from somni_graph_quiz.contracts.session_memory import create_session_memory

_REPLACE_DICT_PATHS = {
    ("session_memory", "answered_records"),
    ("session_memory", "pending_partial_answers"),
    ("session_memory", "question_states"),
    ("session_memory", "previous_answer_record"),
}


def create_graph_state(
    *,
    session_id: str,
    channel: str,
    quiz_mode: str,
    question_catalog: dict,
    language_preference: str,
    default_city: str | None = None,
    started_at: str | None = None,
) -> dict:
    """Create the initial graph state."""
    session_memory = create_session_memory(question_catalog)
    response_language = language_preference
    return {
        "session": {
            "session_id": session_id,
            "channel": channel,
            "quiz_mode": quiz_mode,
            "language_preference": language_preference,
            "language_source": f"{channel}_input",
            "default_city": "" if default_city is None else str(default_city).strip(),
            "started_at": started_at or datetime.now(UTC).isoformat(),
        },
        "question_catalog": deepcopy(question_catalog),
        "session_memory": session_memory,
        "runtime": {
            "llm_available": True,
            "finalized": False,
            "current_turn_index": 0,
            "fallback_used": False,
        },
        "turn": {
            "raw_input": "",
            "input_mode": "message",
            "normalized_input": "",
            "main_branch": None,
            "non_content_intent": "none",
            "response_language": response_language,
            "content_units": [],
            "branch_results": {},
        },
        "artifacts": {
            "trace_entries": [],
            "mapping_artifacts": [],
            "response_facts": {},
            "llm_inputs_summary": [],
            "llm_outputs_summary": [],
        },
    }


def merge_graph_state(graph_state: dict, state_patch: dict) -> dict:
    """Recursively merge a state patch into a graph state."""
    merged = {
        "session": deepcopy(graph_state["session"]),
        "question_catalog": deepcopy(graph_state["question_catalog"]),
        "session_memory": deepcopy(graph_state["session_memory"]),
        "runtime": dict(graph_state["runtime"]),
        "turn": deepcopy(graph_state["turn"]),
        "artifacts": deepcopy(graph_state["artifacts"]),
    }
    _merge_dict(merged, state_patch, path=())
    return merged


def _merge_dict(target: dict, patch: dict, *, path: tuple[str, ...]) -> None:
    for key, value in patch.items():
        current_path = (*path, key)
        if current_path in _REPLACE_DICT_PATHS and isinstance(value, dict):
            target[key] = deepcopy(value)
        elif isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge_dict(target[key], value, path=current_path)
        else:
            target[key] = deepcopy(value)
