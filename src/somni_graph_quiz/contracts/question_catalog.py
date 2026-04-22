"""Question catalog helpers."""

from __future__ import annotations


def get_question(question_catalog: dict, question_id: str | None) -> dict | None:
    """Return a question definition by id."""
    if question_id is None:
        return None
    return question_catalog["question_index"].get(question_id)
