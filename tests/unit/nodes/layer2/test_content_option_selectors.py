from __future__ import annotations

from somni_graph_quiz.contracts.graph_state import create_graph_state
from somni_graph_quiz.contracts.turn_input import TurnInput
from somni_graph_quiz.llm.client import FakeLLMProvider
from somni_graph_quiz.nodes.layer2.content.branch import ContentBranch
from somni_graph_quiz.nodes.layer2.content.mapping import map_content_answer


def _single_choice_question() -> dict:
    return {
        "question_id": "question-06",
        "title": "您对卧室里的光线、声音敏感度如何？",
        "description": "",
        "input_type": "radio",
        "options": [
            {"option_id": "A", "label": "完全不敏感，在哪都能睡", "aliases": []},
            {"option_id": "B", "label": "轻微敏感，但影响不大", "aliases": []},
            {"option_id": "C", "label": "需要相对安静和避光的环境", "aliases": []},
            {"option_id": "D", "label": "一点微光或细小声音就会惊醒", "aliases": []},
            {"option_id": "E", "label": "必须绝对黑暗安静", "aliases": []},
        ],
        "tags": ["sleep"],
        "metadata": {
            "allow_partial": False,
            "structured_kind": "radio",
            "response_style": "default",
            "matching_hints": ["敏感", "光线", "声音"],
        },
    }


def _custom_fallback_question() -> dict:
    return {
        "question_id": "question-09",
        "title": "早上醒来后，多久能彻底清醒？",
        "description": "",
        "input_type": "radio",
        "options": [
            {"option_id": "A", "label": "几乎立刻清醒，满血复活", "option_text": "几乎立刻清醒，满血复活", "aliases": []},
            {"option_id": "B", "label": "需要洗漱或咖啡缓冲", "option_text": "需要洗漱或咖啡缓冲", "aliases": []},
            {"option_id": "C", "label": "1-2 小时都不太清醒，身体沉重", "option_text": "1-2 小时都不太清醒，身体沉重", "aliases": []},
            {"option_id": "D", "label": "", "option_text": "", "aliases": []},
        ],
        "tags": ["anchor"],
        "metadata": {
            "allow_partial": False,
            "structured_kind": "radio",
            "response_style": "default",
            "matching_hints": ["清醒", "醒来", "早起", "缓过来"],
        },
    }


def _age_question() -> dict:
    return {
        "question_id": "question-01",
        "title": "您的年龄段？",
        "description": "",
        "input_type": "radio",
        "options": [
            {"option_id": "A", "label": "18-24 岁", "aliases": []},
            {"option_id": "B", "label": "25-34 岁", "aliases": []},
            {"option_id": "C", "label": "35-44 岁", "aliases": []},
        ],
        "tags": ["basic"],
        "metadata": {
            "allow_partial": False,
            "structured_kind": "radio",
            "response_style": "default",
            "matching_hints": ["年龄"],
        },
    }


def _regular_schedule_question() -> dict:
    return {
        "question_id": "question-02",
        "title": "您平时通常的作息？",
        "description": "",
        "input_type": "time_range",
        "options": [],
        "tags": ["basic"],
        "metadata": {
            "allow_partial": True,
            "structured_kind": "time_range",
            "response_style": "default",
        },
    }


def _free_wake_question() -> dict:
    return {
        "question_id": "question-04",
        "title": "完全自由安排时，您最自然的起床时间是？",
        "description": "",
        "input_type": "radio",
        "options": [
            {"option_id": "A", "label": "06:00 前", "aliases": []},
            {"option_id": "B", "label": "06:00-07:45", "aliases": []},
            {"option_id": "C", "label": "07:45-09:45", "aliases": []},
            {"option_id": "D", "label": "09:45 后", "aliases": []},
        ],
        "tags": ["chronotype"],
        "metadata": {
            "allow_partial": False,
            "structured_kind": "radio",
            "response_style": "default",
            "matching_hints": ["自由", "起床", "自然醒"],
        },
    }


def test_map_content_answer_maps_explicit_ordinal_selector() -> None:
    mapped = map_content_answer(_single_choice_question(), "我选第二个", raw_text="我选第二个")

    assert mapped["selected_options"] == ["B"]
    assert mapped["input_value"] == ""


def test_map_content_answer_prefers_explicit_selector_over_semantic_match() -> None:
    mapped = map_content_answer(
        _single_choice_question(),
        "我选第二个，比较敏感",
        raw_text="我选第二个，比较敏感",
    )

    assert mapped["selected_options"] == ["B"]
    assert mapped["input_value"] == ""


def test_map_content_answer_maps_explicit_letter_selector() -> None:
    mapped = map_content_answer(_single_choice_question(), "我选C", raw_text="我选C")

    assert mapped["selected_options"] == ["C"]
    assert mapped["input_value"] == ""


def test_content_branch_resolves_current_single_choice_selector() -> None:
    question_catalog = {
        "question_order": ["question-06"],
        "question_index": {"question-06": _single_choice_question()},
    }
    graph_state = create_graph_state(
        session_id="session-selector-current-question",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-06"
    graph_state["session_memory"]["pending_question_ids"] = ["question-06"]

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-selector-current-question",
            channel="grpc",
            input_mode="message",
            raw_input="是的我选第二个",
            language_preference="zh-CN",
        ),
    )

    assert result["applied_question_ids"] == ["question-06"]
    answer = result["state_patch"]["session_memory"]["answered_records"]["question-06"]
    assert answer["selected_options"] == ["B"]
    assert answer["input_value"] == ""


def test_content_branch_resolves_current_single_choice_letter_selector() -> None:
    question_catalog = {
        "question_order": ["question-06"],
        "question_index": {"question-06": _single_choice_question()},
    }
    graph_state = create_graph_state(
        session_id="session-selector-current-letter",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-06"
    graph_state["session_memory"]["pending_question_ids"] = ["question-06"]

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-selector-current-letter",
            channel="grpc",
            input_mode="message",
            raw_input="C",
            language_preference="zh-CN",
        ),
    )

    assert result["applied_question_ids"] == ["question-06"]
    answer = result["state_patch"]["session_memory"]["answered_records"]["question-06"]
    assert answer["selected_options"] == ["C"]
    assert answer["input_value"] == ""


def test_content_branch_does_not_apply_bare_selector_to_non_single_choice_current_question() -> None:
    question_catalog = {
        "question_order": ["question-02", "question-06"],
        "question_index": {
            "question-02": {
                "question_id": "question-02",
                "title": "您平时通常的作息？",
                "description": "",
                "input_type": "time_range",
                "options": [],
                "tags": ["sleep"],
                "metadata": {"allow_partial": True, "structured_kind": "time_range"},
            },
            "question-06": _single_choice_question(),
        },
    }
    graph_state = create_graph_state(
        session_id="session-selector-non-single-choice",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-06"]

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-selector-non-single-choice",
            channel="grpc",
            input_mode="message",
            raw_input="A",
            language_preference="zh-CN",
        ),
    )

    assert result["applied_question_ids"] == []
    assert result["clarification_needed"] is True


def test_map_content_answer_uses_empty_option_as_custom_fallback_for_current_question_text() -> None:
    mapped = map_content_answer(
        _custom_fallback_question(),
        "我一般要缓很久才能完全清醒",
        raw_text="我一般要缓很久才能完全清醒",
        allow_custom_empty_option_fallback=True,
    )

    assert mapped["selected_options"] == ["D"]
    assert mapped["input_value"] == "我一般要缓很久才能完全清醒"


def test_content_branch_does_not_use_empty_option_fallback_for_small_talk() -> None:
    question_catalog = {
        "question_order": ["question-09"],
        "question_index": {"question-09": _custom_fallback_question()},
    }
    graph_state = create_graph_state(
        session_id="session-custom-fallback-small-talk",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-09"
    graph_state["session_memory"]["pending_question_ids"] = ["question-09"]

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-custom-fallback-small-talk",
            channel="grpc",
            input_mode="message",
            raw_input="你好啊",
            language_preference="zh-CN",
        ),
    )

    assert result["applied_question_ids"] == []
    assert result["clarification_needed"] is True


def test_content_branch_records_empty_option_fallback_for_current_question() -> None:
    question_catalog = {
        "question_order": ["question-09"],
        "question_index": {"question-09": _custom_fallback_question()},
    }
    graph_state = create_graph_state(
        session_id="session-custom-fallback-record",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-09"
    graph_state["session_memory"]["pending_question_ids"] = ["question-09"]

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-custom-fallback-record",
            channel="grpc",
            input_mode="message",
            raw_input="我一般要缓很久才能完全清醒",
            language_preference="zh-CN",
        ),
    )

    assert result["applied_question_ids"] == ["question-09"]
    answer = result["state_patch"]["session_memory"]["answered_records"]["question-09"]
    assert answer["selected_options"] == ["D"]
    assert answer["input_value"] == "我一般要缓很久才能完全清醒"


def test_content_branch_scopes_selector_only_input_to_current_question_even_when_llm_hallucinates_other_question() -> None:
    question_catalog = {
        "question_order": ["question-01", "question-04"],
        "question_index": {
            "question-01": _age_question(),
            "question-04": _free_wake_question(),
        },
    }
    graph_state = create_graph_state(
        session_id="session-selector-llm-scope-current",
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
                  "unit_text": "我选第二个",
                  "action_mode": "modify",
                  "candidate_question_ids": ["question-01"],
                  "winner_question_id": "question-01",
                  "needs_attribution": false,
                  "raw_extracted_value": {
                    "selected_options": ["B"],
                    "input_value": ""
                  },
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
    graph_state["session_memory"]["answered_records"]["question-01"] = {
        "question_id": "question-01",
        "selected_options": ["A"],
        "input_value": "",
        "field_updates": {},
    }
    graph_state["session_memory"]["answered_question_ids"] = ["question-01"]
    graph_state["session_memory"]["question_states"]["question-01"] = {
        "status": "answered",
        "attempt_count": 0,
        "last_action_mode": "answer",
    }
    graph_state["session_memory"]["current_question_id"] = "question-04"
    graph_state["session_memory"]["pending_question_ids"] = ["question-04"]

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-selector-llm-scope-current",
            channel="grpc",
            input_mode="message",
            raw_input="我选第二个",
            language_preference="zh-CN",
        ),
    )

    assert result["applied_question_ids"] == ["question-04"]
    assert result["modified_question_ids"] == []
    answer = result["state_patch"]["session_memory"]["answered_records"]["question-04"]
    assert answer["selected_options"] == ["B"]
    assert answer["input_value"] == ""


def test_content_branch_allows_selector_only_input_to_hit_explicit_modify_target() -> None:
    question_catalog = {
        "question_order": ["question-01", "question-02"],
        "question_index": {
            "question-01": _age_question(),
            "question-02": _regular_schedule_question(),
        },
    }
    graph_state = create_graph_state(
        session_id="session-selector-modify-target",
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
                  "unit_text": "我选第二个",
                  "action_mode": "modify",
                  "candidate_question_ids": ["question-01"],
                  "winner_question_id": "question-01",
                  "needs_attribution": false,
                  "raw_extracted_value": {
                    "selected_options": ["B"],
                    "input_value": ""
                  },
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
    graph_state["session_memory"]["answered_records"]["question-01"] = {
        "question_id": "question-01",
        "selected_options": ["A"],
        "input_value": "",
        "field_updates": {},
    }
    graph_state["session_memory"]["answered_question_ids"] = ["question-01"]
    graph_state["session_memory"]["question_states"]["question-01"] = {
        "status": "answered",
        "attempt_count": 0,
        "last_action_mode": "answer",
    }
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02"]
    graph_state["session_memory"]["pending_modify_context"] = {"question_id": "question-01"}

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-selector-modify-target",
            channel="grpc",
            input_mode="message",
            raw_input="我选第二个",
            language_preference="zh-CN",
        ),
    )

    assert result["applied_question_ids"] == []
    assert result["modified_question_ids"] == ["question-01"]
    answer = result["state_patch"]["session_memory"]["answered_records"]["question-01"]
    assert answer["selected_options"] == ["B"]
    assert answer["input_value"] == ""


def test_content_branch_uses_empty_option_fallback_after_llm_returns_empty_units() -> None:
    question_catalog = {
        "question_order": ["question-09"],
        "question_index": {"question-09": _custom_fallback_question()},
    }
    graph_state = create_graph_state(
        session_id="session-custom-fallback-llm-empty",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
        responses={
            "layer2/content_understand.md": """
            {
              "content_units": [],
              "clarification_needed": false,
              "clarification_reason": null
            }
            """
        }
    )
    graph_state["session_memory"]["current_question_id"] = "question-09"
    graph_state["session_memory"]["pending_question_ids"] = ["question-09"]

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-custom-fallback-llm-empty",
            channel="grpc",
            input_mode="message",
            raw_input="我一般要缓很久才能完全清醒",
            language_preference="zh-CN",
        ),
    )

    assert result["applied_question_ids"] == ["question-09"]
    answer = result["state_patch"]["session_memory"]["answered_records"]["question-09"]
    assert answer["selected_options"] == ["D"]
    assert answer["input_value"] == "我一般要缓很久才能完全清醒"


def test_content_branch_uses_empty_option_fallback_after_llm_requests_clarification() -> None:
    question_catalog = {
        "question_order": ["question-09"],
        "question_index": {"question-09": _custom_fallback_question()},
    }
    graph_state = create_graph_state(
        session_id="session-custom-fallback-llm-clarification",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
        responses={
            "layer2/content_understand.md": """
            {
              "content_units": [],
              "clarification_needed": true,
              "clarification_reason": "question_identified_option_not_identified"
            }
            """
        }
    )
    graph_state["session_memory"]["current_question_id"] = "question-09"
    graph_state["session_memory"]["pending_question_ids"] = ["question-09"]

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-custom-fallback-llm-clarification",
            channel="grpc",
            input_mode="message",
            raw_input="我一般要缓很久才能完全清醒",
            language_preference="zh-CN",
        ),
    )

    assert result["applied_question_ids"] == ["question-09"]
    answer = result["state_patch"]["session_memory"]["answered_records"]["question-09"]
    assert answer["selected_options"] == ["D"]
    assert answer["input_value"] == "我一般要缓很久才能完全清醒"


def test_content_branch_uses_empty_option_fallback_after_llm_leaves_current_question_unmapped() -> None:
    question_catalog = {
        "question_order": ["question-09"],
        "question_index": {"question-09": _custom_fallback_question()},
    }
    graph_state = create_graph_state(
        session_id="session-custom-fallback-llm-unmapped",
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
                  "unit_text": "我一般要缓很久才能完全清醒",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-09"],
                  "winner_question_id": "question-09",
                  "needs_attribution": false,
                  "raw_extracted_value": "我一般要缓很久才能完全清醒",
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
    graph_state["session_memory"]["current_question_id"] = "question-09"
    graph_state["session_memory"]["pending_question_ids"] = ["question-09"]

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-custom-fallback-llm-unmapped",
            channel="grpc",
            input_mode="message",
            raw_input="我一般要缓很久才能完全清醒",
            language_preference="zh-CN",
        ),
    )

    assert result["applied_question_ids"] == ["question-09"]
    answer = result["state_patch"]["session_memory"]["answered_records"]["question-09"]
    assert answer["selected_options"] == ["D"]
    assert answer["input_value"] == "我一般要缓很久才能完全清醒"
