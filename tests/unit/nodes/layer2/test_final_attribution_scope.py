"""Scope tests for final attribution."""

from __future__ import annotations

import pytest

from somni_graph_quiz.nodes.layer2.content.attribution import FinalAttributionNode


@pytest.mark.parametrize(
    ("content_unit", "expected_winner"),
    [
        (
            {
                "unit_id": "unit-1",
                "unit_text": "anything",
                "action_mode": "answer",
                "candidate_question_ids": [],
                "winner_question_id": None,
                "needs_attribution": True,
                "raw_extracted_value": "anything",
            },
            None,
        ),
        (
            {
                "unit_id": "unit-2",
                "unit_text": "anything",
                "action_mode": "answer",
                "candidate_question_ids": ["question-02"],
                "winner_question_id": None,
                "needs_attribution": True,
                "raw_extracted_value": "anything",
            },
            "question-02",
        ),
        (
            {
                "unit_id": "unit-3",
                "unit_text": "anything",
                "action_mode": "answer",
                "candidate_question_ids": ["question-02", "question-03"],
                "winner_question_id": "question-03",
                "needs_attribution": True,
                "raw_extracted_value": "anything",
            },
            "question-03",
        ),
    ],
)
def test_final_attribution_short_circuits_non_conflict_units(
    content_unit: dict,
    expected_winner: str | None,
) -> None:
    graph_state = {}
    node = FinalAttributionNode()

    def _fail_try_llm(_graph_state: dict, _content_unit: dict) -> dict:
        raise AssertionError("FinalAttributionNode should not call LLM for non-conflict units")

    def _fail_fallback(_graph_state: dict, _content_unit: dict) -> dict:
        raise AssertionError("FinalAttributionNode should not call fallback for non-conflict units")

    node._try_llm = _fail_try_llm  # type: ignore[method-assign]
    node._fallback = _fail_fallback  # type: ignore[method-assign]

    resolved = node.run(graph_state, content_unit)

    assert resolved["winner_question_id"] == expected_winner
    assert resolved["needs_attribution"] is False
