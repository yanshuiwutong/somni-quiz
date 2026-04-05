"""Streamlit mapper."""

from __future__ import annotations


def map_streamlit_questionnaire_to_catalog(questionnaire: list[dict]) -> dict:
    """Map a Streamlit questionnaire payload into the runtime catalog shape."""
    question_order = []
    question_index = {}
    for question in questionnaire:
        question_order.append(question["question_id"])
        question_index[question["question_id"]] = {
            "question_id": question["question_id"],
            "title": question.get("title", ""),
            "description": question.get("description", ""),
            "input_type": question.get("input_type", ""),
            "tags": list(question.get("tags", [])),
            "options": [
                {
                    "option_id": option.get("option_id", ""),
                    "label": option.get("option_text", option.get("label", "")),
                    "aliases": list(option.get("aliases", [])),
                }
                for option in question.get("options", [])
            ],
            "config": _map_question_config(question),
            "metadata": {
                "allow_partial": question.get("input_type") == "time_range",
                "structured_kind": question.get("input_type"),
                "response_style": "followup" if question.get("input_type") == "time_range" else "default",
                "matching_hints": list(question.get("tags", [])),
            },
        }
    return {"question_order": question_order, "question_index": question_index}


def build_streamlit_view(
    *,
    session_id: str,
    assistant_message: str,
    answer_record: dict,
    pending_question: dict | None,
    finalized: bool,
    final_result: dict | None,
    quiz_mode: str,
    chat_history: list[dict],
) -> dict:
    """Build the Streamlit-facing view model."""
    return {
        "session_id": session_id,
        "assistant_message": assistant_message,
        "answer_record": answer_record,
        "pending_question": pending_question,
        "finalized": finalized,
        "final_result": final_result,
        "quiz_mode": quiz_mode,
        "chat_history": chat_history,
    }


def _map_question_config(question: dict) -> dict | None:
    config = question.get("config")
    if not isinstance(config, dict):
        return None
    items = [
        {
            "index": int(item.get("index", 0)),
            "label": str(item.get("label", "")),
            "format": str(item.get("format", "")),
        }
        for item in config.get("items", [])
        if isinstance(item, dict)
    ]
    if not items:
        return None
    return {"items": items}
