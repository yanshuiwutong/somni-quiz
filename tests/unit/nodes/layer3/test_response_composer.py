"""Tests for response composition."""

import json
from types import SimpleNamespace

from somni_graph_quiz.contracts.finalized_turn_context import create_finalized_turn_context
from somni_graph_quiz.llm.client import FakeLLMProvider
from somni_graph_quiz.nodes.layer3.respond import ResponseComposerNode


def _extract_payload_from_prompt(prompt_text: str) -> dict:
    marker = "## Input Payload"
    start = prompt_text.index(marker)
    payload_section = prompt_text[start:]
    json_block_start = payload_section.index("```json") + len("```json")
    json_block_end = payload_section.index("```", json_block_start)
    json_text = payload_section[json_block_start:json_block_end].strip()
    return json.loads(json_text)


def test_response_composer_uses_chinese_for_non_english_language() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-01",
        next_question={"question_id": "question-01", "title": "年龄"},
        finalized=False,
        response_language="zh-CN",
        response_facts={},
    )

    message = ResponseComposerNode().run(finalized)

    assert "睡眠" in message
    assert "question-01" not in message


def test_response_composer_uses_english_for_english_language() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="answered",
        updated_answer_record={"answers": [{"question_id": "question-01"}]},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "Next question"},
        finalized=False,
        response_language="en",
        response_facts={},
    )

    message = ResponseComposerNode().run(finalized)

    assert "next question" in message.lower()


def test_response_composer_handles_view_only() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="view_only",
        updated_answer_record={"answers": [{"question_id": "question-01", "input_value": "22"}]},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "Next question"},
        finalized=False,
        response_language="en",
        response_facts={"view_records": [{"question_id": "question-01", "input_value": "22"}]},
    )

    message = ResponseComposerNode().run(finalized)

    assert "summary" in message.lower()


def test_response_composer_mentions_view_records() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="view_only",
        updated_answer_record={"answers": [{"question_id": "question-01", "input_value": "22"}]},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "您平时通常的作息？"},
        finalized=False,
        response_language="zh-CN",
        response_facts={"view_records": [{"question_id": "question-01", "input_value": "22"}]},
    )

    message = ResponseComposerNode().run(finalized)

    assert "记录" in message
    assert "22" in message


def test_response_composer_uses_llm_when_available() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/response_composer.md": """
            {
              "assistant_message": "我先记下了这部分作息，请再告诉我你通常几点起床。"
            }
            """
        }
    )
    finalized = create_finalized_turn_context(
        turn_outcome="partial_recorded",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "作息"},
        finalized=False,
        response_language="zh-CN",
        response_facts={
            "llm_provider": provider,
            "llm_available": True,
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert message == "我先记下了这部分作息，请再告诉我你通常几点起床。"
    assert len(provider.calls) == 1


def test_response_composer_partial_recorded_zh_only_missing_bedtime() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="partial_recorded",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "作息"},
        finalized=False,
        response_language="zh-CN",
        response_facts={
            "partial_followup": {"missing_fields": ["bedtime"]},
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert message == "已先记下你的起床时间，请告诉我你通常几点睡吧。"


def test_response_composer_partial_recorded_zh_only_missing_wake_time() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="partial_recorded",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "作息"},
        finalized=False,
        response_language="zh-CN",
        response_facts={
            "partial_followup": {"missing_fields": ["wake_time"]},
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert message == "已先记下你的入睡时间，请再告诉我你通常几点起床。"


def test_response_composer_partial_recorded_en_only_missing_bedtime() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="partial_recorded",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "Next question"},
        finalized=False,
        response_language="en",
        response_facts={
            "partial_followup": {"missing_fields": ["bedtime"]},
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert message == "I've noted your wake-up time; please tell me when you usually go to sleep."


def test_response_composer_partial_recorded_en_only_missing_wake_time() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="partial_recorded",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "Next question"},
        finalized=False,
        response_language="en",
        response_facts={
            "partial_followup": {"missing_fields": ["wake_time"]},
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert message == "I've noted your bedtime; please tell me when you usually wake up."


def test_response_composer_partial_recorded_en_uses_generic_message_for_multiple_missing_fields() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="partial_recorded",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "Next question"},
        finalized=False,
        response_language="en",
        response_facts={
            "partial_followup": {"missing_fields": ["bedtime", "wake_time"]},
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert message == "I noted part of your schedule. What time do you wake up?"


def test_response_composer_llm_payload_includes_partial_followup() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/response_composer.md": """
            {
              "assistant_message": "感谢"
            }
            """
        }
    )
    partial_followup = {"missing_fields": ["wake_time"]}
    finalized = create_finalized_turn_context(
        turn_outcome="partial_recorded",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "Next question"},
        finalized=False,
        response_language="en",
        response_facts={
            "llm_provider": provider,
            "llm_available": True,
            "partial_followup": partial_followup,
        },
    )

    ResponseComposerNode().run(finalized)

    payload = _extract_payload_from_prompt(provider.calls[0][1])

    assert payload["partial_followup"] == partial_followup

def test_response_composer_falls_back_when_llm_output_is_invalid() -> None:
    provider = FakeLLMProvider(
        responses={"layer3/response_composer.md": "oops"}
    )
    finalized = create_finalized_turn_context(
        turn_outcome="answered",
        updated_answer_record={"answers": [{"question_id": "question-01"}]},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "Next question"},
        finalized=False,
        response_language="en",
        response_facts={
            "llm_provider": provider,
            "llm_available": True,
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "next question" in message.lower()
    assert len(provider.calls) == 1


def test_response_composer_answered_mentions_recorded_fact_before_next_question() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="answered",
        updated_answer_record={"answers": [{"question_id": "question-03", "selected_options": ["D"]}]},
        updated_question_states={},
        current_question_id="question-04",
        next_question={"question_id": "question-04", "title": "完全自由安排时，您最自然的起床时间是？"},
        finalized=False,
        response_language="zh-CN",
        response_facts={
            "recorded_question_summaries": [
                {
                    "question_id": "question-03",
                    "title": "完全自由安排时，您最自然的入睡时间是？",
                }
            ]
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "入睡时间" in message
    assert "起床时间" in message


def test_response_composer_modified_has_specific_fallback_message() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="modified",
        updated_answer_record={"answers": [{"question_id": "question-03", "selected_options": ["D"]}]},
        updated_question_states={},
        current_question_id="question-04",
        next_question={"question_id": "question-04", "title": "完全自由安排时，您最自然的起床时间是？"},
        finalized=False,
        response_language="zh-CN",
        response_facts={
            "modified_question_summaries": [
                {
                    "question_id": "question-03",
                    "title": "完全自由安排时，您最自然的入睡时间是？",
                }
            ]
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "更新" in message or "改" in message
    assert "起床时间" in message


def test_response_composer_reanchors_identity_pullback_to_current_question() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "您平时通常的作息？"},
        finalized=False,
        response_language="zh-CN",
        response_facts={
            "non_content_action": "pullback",
            "pullback_reason": "identity_question",
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "陪你" in message or "Somni" in message
    assert "作息" in message
    assert "question-02" not in message


def test_response_composer_mentions_previous_record_scope() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="view_only",
        updated_answer_record={"answers": [{"question_id": "question-01", "selected_options": ["B"]}]},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "您平时通常的作息？"},
        finalized=False,
        response_language="zh-CN",
        response_facts={
            "non_content_action": "view_previous",
            "view_target_question_id": "question-01",
            "view_records": [{"question_id": "question-01", "selected_options": ["B"], "input_value": ""}],
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "上一题" in message
    assert "B" in message


def test_response_composer_greeting_pullback_matches_user_input() -> None:
    finalized = SimpleNamespace(
        raw_input="你好",
        input_mode="message",
        main_branch="non_content",
        non_content_intent="pullback_chat",
        turn_outcome="pullback",
        current_question={"question_id": "question-02", "title": "您平时通常的作息？", "input_type": "time_range"},
        next_question={"question_id": "question-02", "title": "您平时通常的作息？", "input_type": "time_range"},
        finalized=False,
        response_language="zh-CN",
        response_facts={
            "non_content_action": "pullback",
            "pullback_reason": "chat",
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "作息" in message
    assert "烦心" not in message
    assert "压力" not in message
    assert "辛苦" not in message


def test_response_composer_thanks_pullback_acknowledges_thanks() -> None:
    finalized = SimpleNamespace(
        raw_input="谢谢",
        input_mode="message",
        main_branch="non_content",
        non_content_intent="pullback_chat",
        turn_outcome="pullback",
        current_question={"question_id": "question-02", "title": "您平时通常的作息？", "input_type": "time_range"},
        next_question={"question_id": "question-02", "title": "您平时通常的作息？", "input_type": "time_range"},
        finalized=False,
        response_language="zh-CN",
        response_facts={
            "non_content_action": "pullback",
            "pullback_reason": "chat",
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "作息" in message
    assert "谢谢" in message or "不客气" in message


def test_response_composer_names_navigation_target() -> None:
    finalized = SimpleNamespace(
        raw_input="下一题",
        input_mode="message",
        main_branch="non_content",
        non_content_intent="navigate_next",
        turn_outcome="navigate",
        current_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？", "input_type": "radio"},
        next_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？", "input_type": "radio"},
        finalized=False,
        response_language="zh-CN",
        response_facts={
            "non_content_action": "navigate_next",
            "next_question_id": "question-03",
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "下一题" in message or "切到" in message
    assert "入睡时间" in message


def test_response_composer_clarification_uses_target_question_not_raw_input_topic() -> None:
    finalized = SimpleNamespace(
        raw_input="对声光轻微敏感，但影响不大",
        input_mode="message",
        main_branch="content",
        non_content_intent="none",
        turn_outcome="clarification",
        current_question={"question_id": "question-01", "title": "您的年龄段？", "input_type": "radio"},
        next_question={"question_id": "question-01", "title": "您的年龄段？", "input_type": "radio"},
        finalized=False,
        response_language="zh-CN",
        response_facts={
            "clarification_question_id": "question-01",
            "clarification_question_title": "您的年龄段？",
            "clarification_kind": "question_identified_option_not_identified",
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "年龄" in message
    assert "声光" not in message
    assert "敏感" not in message


def test_response_composer_clarification_uses_identified_sensitivity_question() -> None:
    finalized = SimpleNamespace(
        raw_input="很敏感",
        input_mode="message",
        main_branch="content",
        non_content_intent="none",
        turn_outcome="clarification",
        current_question={"question_id": "question-01", "title": "您的年龄段？", "input_type": "radio"},
        next_question={"question_id": "question-01", "title": "您的年龄段？", "input_type": "radio"},
        finalized=False,
        response_language="zh-CN",
        response_facts={
            "clarification_question_id": "question-06",
            "clarification_question_title": "您对卧室里的光线、声音敏感度如何？",
            "clarification_kind": "question_identified_option_not_identified",
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "光线" in message or "声音" in message or "敏感度" in message


def test_response_composer_completed_uses_longer_fallback_message() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="completed",
        updated_answer_record={
            "answers": [
                {"question_id": "question-01", "input_value": "18"},
                {
                    "question_id": "question-02",
                    "field_updates": {"bedtime": "23:00", "wake_time": "07:00"},
                    "input_value": "",
                },
            ]
        },
        updated_question_states={},
        current_question_id=None,
        next_question=None,
        finalized=True,
        response_language="zh-CN",
        response_facts={},
    )

    message = ResponseComposerNode().run(finalized)

    assert "感谢" in message
    assert "睡眠" in message
    assert "方案" in message or "处方" in message
    assert len(message) >= 30


def test_response_composer_completed_uses_llm_personalized_message_with_answer_record() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/response_composer.md": """
            {
              "assistant_message": "感谢你的分享。我已经大致了解了你的睡眠习惯，接下来会结合你记录下来的作息节律，为你整理更适合你的专属声、光、香睡眠方案。"
            }
            """
        }
    )
    finalized = create_finalized_turn_context(
        turn_outcome="completed",
        updated_answer_record={
            "answers": [
                {"question_id": "question-01", "input_value": "18"},
                {
                    "question_id": "question-02",
                    "field_updates": {"bedtime": "23:00", "wake_time": "07:00"},
                    "input_value": "",
                },
            ]
        },
        updated_question_states={},
        current_question_id=None,
        next_question=None,
        finalized=True,
        response_language="zh-CN",
        response_facts={
            "llm_provider": provider,
            "llm_available": True,
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "专属声、光、香睡眠方案" in message
    assert len(provider.calls) == 1
    assert "question-02" in provider.calls[0][1]
    assert "23:00" in provider.calls[0][1]


def test_response_composer_weather_success_pulls_back_to_current_question() -> None:
    finalized = SimpleNamespace(
        raw_input="今天天气怎么样",
        input_mode="message",
        main_branch="non_content",
        non_content_intent="weather_query",
        turn_outcome="pullback",
        current_question={"question_id": "question-01", "title": "您的年龄段？", "input_type": "radio"},
        next_question={"question_id": "question-01", "title": "您的年龄段？", "input_type": "radio"},
        finalized=False,
        response_language="zh-CN",
        response_facts={
            "non_content_mode": "weather",
            "non_content_action": "weather_query",
            "weather_status": "success",
            "weather_city": "北京",
            "weather_summary": "晴，22C",
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "北京" in message
    assert "晴" in message
    assert "年龄段" in message


def test_response_composer_weather_missing_city_asks_for_city() -> None:
    finalized = SimpleNamespace(
        raw_input="今天天气怎么样",
        input_mode="message",
        main_branch="non_content",
        non_content_intent="weather_query",
        turn_outcome="pullback",
        current_question={"question_id": "question-01", "title": "您的年龄段？", "input_type": "radio"},
        next_question={"question_id": "question-01", "title": "您的年龄段？", "input_type": "radio"},
        finalized=False,
        response_language="zh-CN",
        response_facts={
            "non_content_mode": "weather",
            "non_content_action": "weather_query",
            "weather_status": "missing_city",
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "城市" in message
    assert "年龄段" not in message


def test_response_composer_answered_uses_llm_with_turn_scoped_prompt() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/response_composer.md": """
            {
              "assistant_message": "已记下你关于完全自由安排时，您最自然的入睡时间是？的回答。接下来请回答完全自由安排时，您最自然的起床时间是？。"
            }
            """
        }
    )
    finalized = create_finalized_turn_context(
        turn_outcome="answered",
        updated_question_states={},
        current_question_id="question-04",
        next_question={"question_id": "question-04", "title": "完全自由安排时，您最自然的起床时间是？"},
        finalized=False,
        response_language="zh-CN",
        response_facts={
            "llm_provider": provider,
            "llm_available": True,
            "recorded_question_summaries": [
                {
                    "question_id": "question-03",
                    "title": "完全自由安排时，您最自然的入睡时间是？",
                }
            ],
        },
        current_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        updated_answer_record={
            "answers": [
                {"question_id": "question-03", "selected_options": ["B"]},
                {"question_id": "question-99", "input_value": "无关历史压力题"},
            ]
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "入睡时间" in message
    assert "起床时间" in message
    assert len(provider.calls) == 1
    assert "无关历史压力题" not in provider.calls[0][1]
    assert "完全自由安排时，您最自然的入睡时间是？" in provider.calls[0][1]


def test_response_composer_answered_falls_back_when_llm_output_drifts_to_unrelated_topic() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/response_composer.md": """
            {
              "assistant_message": "已记下你关于睡眠受压力影响的相关选择，接下来请回答下一题。"
            }
            """
        }
    )
    finalized = create_finalized_turn_context(
        turn_outcome="answered",
        updated_answer_record={"answers": [{"question_id": "question-03", "selected_options": ["B"]}]},
        updated_question_states={},
        current_question_id="question-04",
        next_question={"question_id": "question-04", "title": "完全自由安排时，您最自然的起床时间是？"},
        finalized=False,
        response_language="zh-CN",
        response_facts={
            "llm_provider": provider,
            "llm_available": True,
            "recorded_question_summaries": [
                {
                    "question_id": "question-03",
                    "title": "完全自由安排时，您最自然的入睡时间是？",
                }
            ],
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "入睡时间" in message
    assert "起床时间" in message
    assert "压力" not in message
    assert len(provider.calls) == 1


def test_response_composer_modified_uses_llm_with_turn_scoped_prompt() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/response_composer.md": """
            {
              "assistant_message": "已更新你关于完全自由安排时，您最自然的入睡时间是？的回答。接下来请回答完全自由安排时，您最自然的起床时间是？。"
            }
            """
        }
    )
    finalized = create_finalized_turn_context(
        turn_outcome="modified",
        updated_question_states={},
        current_question_id="question-04",
        next_question={"question_id": "question-04", "title": "完全自由安排时，您最自然的起床时间是？"},
        finalized=False,
        response_language="zh-CN",
        response_facts={
            "llm_provider": provider,
            "llm_available": True,
            "modified_question_summaries": [
                {
                    "question_id": "question-03",
                    "title": "完全自由安排时，您最自然的入睡时间是？",
                }
            ],
        },
        updated_answer_record={
            "answers": [
                {"question_id": "question-03", "selected_options": ["B"]},
                {"question_id": "question-99", "input_value": "无关历史压力题"},
            ]
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "更新" in message
    assert "起床时间" in message
    assert len(provider.calls) == 1
    assert "无关历史压力题" not in provider.calls[0][1]
