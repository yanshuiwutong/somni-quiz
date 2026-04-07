"""Tests for single-choice closure inside content understand."""

from __future__ import annotations

from somni_graph_quiz.contracts.graph_state import create_graph_state
from somni_graph_quiz.contracts.turn_input import TurnInput
from somni_graph_quiz.llm.client import FakeLLMProvider
from somni_graph_quiz.nodes.layer2.content.understand import ContentUnderstandNode


def test_content_understand_closes_single_candidate_single_choice_from_llm() -> None:
    question_catalog = {
        "question_order": ["question-05"],
        "question_index": {
            "question-05": {
                "question_id": "question-05",
                "title": "遇到压力或重要事情，您的睡眠会受影响吗？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "毫无影响，倒头就睡", "aliases": []},
                    {"option_id": "E", "label": "大脑停不下来，几乎睡不着", "aliases": []},
                ],
                "tags": ["sleep"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["压力", "睡眠"],
                },
            }
        },
    }
    graph_state = create_graph_state(
        session_id="session-single-choice-closure",
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
                  "unit_text": "大脑停不下来，几乎睡不着",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-05"],
                  "winner_question_id": null,
                  "needs_attribution": true,
                  "raw_extracted_value": "大脑停不下来，几乎睡不着",
                  "selected_options": ["E"],
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

    understood = ContentUnderstandNode().run(
        graph_state,
        TurnInput(
            session_id="session-single-choice-closure",
            channel="grpc",
            input_mode="message",
            raw_input="大脑停不下来，几乎睡不着",
            language_preference="zh-CN",
        ),
    )

    assert understood["content_units"][0]["winner_question_id"] == "question-05"
    assert understood["content_units"][0]["needs_attribution"] is False
    assert understood["content_units"][0]["selected_options"] == ["E"]


def test_content_understand_keeps_true_multi_candidate_conflict_for_attribution() -> None:
    question_catalog = {
        "question_order": ["question-a", "question-b"],
        "question_index": {
            "question-a": {
                "question_id": "question-a",
                "title": "您对卧室里的光线敏感吗？",
                "description": "",
                "input_type": "radio",
                "options": [{"option_id": "A", "label": "很敏感", "aliases": []}],
                "tags": ["sleep"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["光线", "敏感"],
                },
            },
            "question-b": {
                "question_id": "question-b",
                "title": "您对卧室里的声音敏感吗？",
                "description": "",
                "input_type": "radio",
                "options": [{"option_id": "A", "label": "很敏感", "aliases": []}],
                "tags": ["sleep"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["声音", "敏感"],
                },
            },
        },
    }
    graph_state = create_graph_state(
        session_id="session-multi-candidate-conflict",
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
                  "unit_text": "很敏感",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-a", "question-b"],
                  "winner_question_id": null,
                  "needs_attribution": true,
                  "raw_extracted_value": "很敏感",
                  "selected_options": ["A"],
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

    understood = ContentUnderstandNode().run(
        graph_state,
        TurnInput(
            session_id="session-multi-candidate-conflict",
            channel="grpc",
            input_mode="message",
            raw_input="很敏感",
            language_preference="zh-CN",
        ),
    )

    assert understood["content_units"][0]["winner_question_id"] is None
    assert understood["content_units"][0]["needs_attribution"] is True
    assert understood["content_units"][0]["selected_options"] == []


def test_content_understand_resolves_multi_candidate_by_per_question_option_closure() -> None:
    question_catalog = {
        "question_order": ["question-05", "question-07", "question-08"],
        "question_index": {
            "question-05": {
                "question_id": "question-05",
                "title": "遇到压力或重要事情，您的睡眠会受影响吗？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "毫无影响，倒头就睡", "aliases": []},
                    {"option_id": "E", "label": "大脑停不下来，几乎睡不着", "aliases": []},
                ],
                "tags": ["sleep"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["压力", "睡眠"],
                },
            },
            "question-07": {
                "question_id": "question-07",
                "title": "最影响你睡好的问题是哪一个？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "B", "label": "躺下很久才能睡着", "aliases": []},
                ],
                "tags": ["sleep"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["入睡困难"],
                },
            },
            "question-08": {
                "question_id": "question-08",
                "title": "半夜醒来后，再次入睡困难吗？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "C", "label": "比较困难，需要 30 分钟以上", "aliases": []},
                ],
                "tags": ["sleep"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["再次入睡"],
                },
            },
        },
    }
    graph_state = create_graph_state(
        session_id="session-candidate-closure",
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
                  "unit_text": "压力很大睡不着",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-05", "question-07", "question-08"],
                  "winner_question_id": null,
                  "needs_attribution": true,
                  "raw_extracted_value": "压力导致入睡困难",
                  "selected_options": [],
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
    node = ContentUnderstandNode()
    seen_question_ids: list[str] = []

    def _fake_try_llm_option_mapping(_graph_state: dict, question: dict, raw_text: str) -> dict | None:
        seen_question_ids.append(str(question["question_id"]))
        assert raw_text == "压力很大睡不着"
        if question["question_id"] == "question-05":
            return {
                "selected_options": ["E"],
                "input_value": "",
                "field_updates": {},
                "missing_fields": [],
            }
        return None

    node._try_llm_option_mapping = _fake_try_llm_option_mapping  # type: ignore[method-assign]

    understood = node.run(
        graph_state,
        TurnInput(
            session_id="session-candidate-closure",
            channel="grpc",
            input_mode="message",
            raw_input="压力很大睡不着",
            language_preference="zh-CN",
        ),
    )

    assert seen_question_ids == ["question-05", "question-07", "question-08"]
    assert understood["content_units"][0]["winner_question_id"] == "question-05"
    assert understood["content_units"][0]["needs_attribution"] is False
    assert understood["content_units"][0]["selected_options"] == ["E"]


def test_content_understand_single_choice_never_keeps_multiple_selected_options() -> None:
    question_catalog = {
        "question_order": ["question-05"],
        "question_index": {
            "question-05": {
                "question_id": "question-05",
                "title": "遇到压力或重要事情，您的睡眠会受影响吗？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "毫无影响，倒头就睡", "aliases": []},
                    {"option_id": "E", "label": "大脑停不下来，几乎睡不着", "aliases": []},
                ],
                "tags": ["sleep"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["压力", "睡眠"],
                },
            }
        },
    }
    graph_state = create_graph_state(
        session_id="session-single-choice-unique-option",
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
                  "unit_text": "大脑停不下来，几乎睡不着",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-05"],
                  "winner_question_id": null,
                  "needs_attribution": true,
                  "raw_extracted_value": "大脑停不下来，几乎睡不着",
                  "selected_options": ["A", "E"],
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

    understood = ContentUnderstandNode().run(
        graph_state,
        TurnInput(
            session_id="session-single-choice-unique-option",
            channel="grpc",
            input_mode="message",
            raw_input="大脑停不下来，几乎睡不着",
            language_preference="zh-CN",
        ),
    )

    assert understood["content_units"][0]["winner_question_id"] == "question-05"
    assert understood["content_units"][0]["needs_attribution"] is False
    assert understood["content_units"][0]["selected_options"] == ["E"]
