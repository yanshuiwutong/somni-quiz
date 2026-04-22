"""Node input/output contracts."""

from __future__ import annotations


def create_branch_result(
    *,
    branch_type: str,
    state_patch: dict | None = None,
    applied_question_ids: list[str] | None = None,
    modified_question_ids: list[str] | None = None,
    partial_question_ids: list[str] | None = None,
    skipped_question_ids: list[str] | None = None,
    rejected_unit_ids: list[str] | None = None,
    clarification_needed: bool = False,
    response_facts: dict | None = None,
) -> dict:
    """Return a normalized branch result."""
    return {
        "branch_type": branch_type,
        "state_patch": state_patch or {},
        "applied_question_ids": applied_question_ids or [],
        "modified_question_ids": modified_question_ids or [],
        "partial_question_ids": partial_question_ids or [],
        "skipped_question_ids": skipped_question_ids or [],
        "rejected_unit_ids": rejected_unit_ids or [],
        "clarification_needed": clarification_needed,
        "response_facts": response_facts or {},
    }
