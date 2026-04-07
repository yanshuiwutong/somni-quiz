"""Diagnostics tests for content understanding."""

from __future__ import annotations

import json
import logging

from somni_graph_quiz.contracts.graph_state import create_graph_state
from somni_graph_quiz.contracts.turn_input import TurnInput
from somni_graph_quiz.llm.client import FakeLLMProvider
from somni_graph_quiz.nodes.layer2.content.understand import ContentUnderstandNode


def _parse_diagnostic_messages(caplog) -> list[dict]:
    records: list[dict] = []
    for record in caplog.records:
        if record.name != "somni_graph_quiz.diagnostics.content_understand":
            continue
        records.append(json.loads(record.getMessage()))
    return records


def test_content_understand_logs_llm_invalid_schema_and_rule_fallback(
    question_catalog: dict,
    caplog,
) -> None:
    graph_state = create_graph_state(
        session_id="session-diag-invalid",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
        responses={
            "layer2/content_understand.md": """
            {
              "content_units": {
                "winner_question_id": "question-01"
              },
              "clarification_needed": false,
              "clarification_reason": null
            }
            """
        }
    )

    with caplog.at_level(logging.WARNING, logger="somni_graph_quiz.diagnostics.content_understand"):
        ContentUnderstandNode().run(
            graph_state,
            TurnInput(
                session_id="session-diag-invalid",
                channel="grpc",
                input_mode="message",
                raw_input="29",
                language_preference="zh-CN",
            ),
        )

    events = [entry["event"] for entry in _parse_diagnostic_messages(caplog)]

    assert "llm_invalid_schema" in events
    assert "rule_fallback_used" in events


def test_content_understand_logs_llm_result_consumed_summary(
    question_catalog: dict,
    caplog,
) -> None:
    graph_state = create_graph_state(
        session_id="session-diag-llm",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
        responses={
            "layer2/content_understand.md": """
            {
              "content_units": [
                {
                  "unit_id": "unit-1",
                  "unit_text": "25岁",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-01"],
                  "winner_question_id": "question-01",
                  "needs_attribution": false,
                  "raw_extracted_value": "25",
                  "selected_options": ["B"],
                  "input_value": "",
                  "field_updates": {},
                  "missing_fields": []
                }
              ],
              "clarification_needed": false,
              "clarification_reason": null
            }
            """
        }
    )

    with caplog.at_level(logging.WARNING, logger="somni_graph_quiz.diagnostics.content_understand"):
        ContentUnderstandNode().run(
            graph_state,
            TurnInput(
                session_id="session-diag-llm",
                channel="grpc",
                input_mode="message",
                raw_input="25岁",
                language_preference="zh-CN",
            ),
        )

    diagnostics = _parse_diagnostic_messages(caplog)
    events = [entry["event"] for entry in diagnostics]

    assert "llm_result_received" in events
    assert "llm_result_consumed" in events
    consumed = next(entry for entry in diagnostics if entry["event"] == "llm_result_consumed")
    assert consumed["path"] == "llm"
    assert consumed["content_units"][0]["winner_question_id"] == "question-01"
    assert consumed["content_units"][0]["selected_options"] == ["B"]
