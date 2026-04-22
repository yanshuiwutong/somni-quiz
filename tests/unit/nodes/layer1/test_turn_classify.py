"""Tests for turn classification."""

from somni_graph_quiz.contracts.graph_state import create_graph_state
from somni_graph_quiz.contracts.turn_input import TurnInput
from somni_graph_quiz.llm.client import FakeLLMProvider
from somni_graph_quiz.nodes.layer1.turn_classify import TurnClassifyNode

OPEN_TRAVEL_CHAT = (
    "\u6211\u60f3\u53bb\u65c5\u6e38\uff0c\u4f60\u6709\u4ec0\u4e48"
    "\u63a8\u8350\u7684\u5730\u65b9\u5417"
)


def test_turn_classify_marks_control_as_non_content(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-1",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-1",
            channel="grpc",
            input_mode="message",
            raw_input="下一题",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "non_content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "pending_non_content"
    assert result["state_patch"]["turn"]["normalized_input"] == "下一题"


def test_turn_classify_marks_numeric_input_as_content(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-1",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="en",
    )

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-1",
            channel="grpc",
            input_mode="message",
            raw_input="22",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "none"


def test_turn_classify_uses_llm_when_available(question_catalog: dict) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "content",
              "normalized_input": "7点起",
              "reason": "partial completion of sleep schedule"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="session-llm",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-llm",
            channel="grpc",
            input_mode="message",
            raw_input="7点起",
            language_preference="zh-CN",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "none"
    assert result["state_patch"]["turn"]["normalized_input"] == "7点起"
    assert len(provider.calls) == 1


def test_turn_classify_short_circuits_explicit_control_before_llm(question_catalog: dict) -> None:
    provider = FakeLLMProvider(
        responses={"layer1/turn_classify.md": "not json"}
    )
    graph_state = create_graph_state(
        session_id="session-fallback",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-fallback",
            channel="grpc",
            input_mode="message",
            raw_input="下一题",
            language_preference="zh-CN",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "non_content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "pending_non_content"
    assert provider.calls == []


def test_turn_classify_marks_identity_question_as_non_content(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-identity",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-identity",
            channel="grpc",
            input_mode="message",
            raw_input="你是谁",
            language_preference="zh-CN",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "non_content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "pending_non_content"


def test_turn_classify_bypasses_llm_for_direct_answer(question_catalog: dict) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "non_content",
              "normalized_input": "should-not-be-used"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="session-direct-answer",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-direct-answer",
            channel="grpc",
            input_mode="direct_answer",
            raw_input="23:00-07:00",
            direct_answer_payload={
                "question_id": "question-02",
                "selected_options": [],
                "input_value": "23:00-07:00",
            },
            language_preference="zh-CN",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "none"
    assert result["state_patch"]["turn"]["normalized_input"] == "23:00-07:00"
    assert provider.calls == []


def test_turn_classify_marks_view_all_as_non_content_intent(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-view",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-view",
            channel="grpc",
            input_mode="message",
            raw_input="查看记录",
            language_preference="zh-CN",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "non_content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "pending_non_content"


def test_turn_classify_marks_greeting_as_pullback_chat(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-greeting",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-greeting",
            channel="grpc",
            input_mode="message",
            raw_input="你好",
            language_preference="zh-CN",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "non_content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "pending_non_content"


def test_turn_classify_marks_short_confirmation_as_non_content(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-short-confirmation",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-03"

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-short-confirmation",
            channel="grpc",
            input_mode="message",
            raw_input="是的",
            language_preference="zh-CN",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "non_content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "pending_non_content"


def test_turn_classify_marks_weather_query_as_non_content(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-weather",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-weather",
            channel="grpc",
            input_mode="message",
            raw_input="上海今天天气怎么样",
            language_preference="zh-CN",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "non_content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "pending_non_content"


def test_turn_classify_llm_payload_includes_future_question_option_summary() -> None:
    question_catalog = {
        "question_order": ["question-01", "question-05", "question-06"],
        "question_index": {
            "question-01": {
                "question_id": "question-01",
                "title": "您的年龄段？",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "18-24 岁", "aliases": []},
                    {"option_id": "B", "label": "25-34 岁", "aliases": []},
                ],
                "tags": ["基础信息"],
                "metadata": {"matching_hints": ["年龄"]},
            },
            "question-05": {
                "question_id": "question-05",
                "title": "遇到压力或重要事情，您的睡眠会受影响吗？",
                "input_type": "radio",
                "options": [
                    {"option_id": "E", "label": "大脑停不下来，几乎睡不着", "aliases": []},
                ],
                "tags": ["人格判定"],
                "metadata": {"matching_hints": ["压力", "睡眠"]},
            },
            "question-06": {
                "question_id": "question-06",
                "title": "您对卧室里的光线、声音敏感度如何？",
                "input_type": "radio",
                "options": [
                    {"option_id": "B", "label": "轻微敏感，但影响不大", "aliases": []},
                ],
                "tags": ["人格判定"],
                "metadata": {"matching_hints": ["声光", "敏感"]},
            },
        },
    }
    provider = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "content",
              "non_content_intent": "none",
              "normalized_input": "大脑停不下来，几乎睡不着"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="session-l1-payload",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider

    TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-l1-payload",
            channel="grpc",
            input_mode="message",
            raw_input="大脑停不下来，几乎睡不着",
            language_preference="zh-CN",
        ),
    )

    prompt_text = provider.calls[0][1]
    assert "question_catalog_summary" in prompt_text
    assert "大脑停不下来，几乎睡不着" in prompt_text
    assert "轻微敏感，但影响不大" in prompt_text


def test_turn_classify_overrides_pullback_for_catalog_answer_like_text() -> None:
    question_catalog = {
        "question_order": ["question-05"],
        "question_index": {
            "question-05": {
                "question_id": "question-05",
                "title": "遇到压力或重要事情，您的睡眠会受影响吗？",
                "input_type": "radio",
                "options": [
                    {"option_id": "D", "label": "显著紧张，伴有心跳快或身体紧绷", "aliases": []},
                    {"option_id": "E", "label": "大脑停不下来，几乎睡不着", "aliases": []},
                ],
                "tags": ["人格判定"],
                "metadata": {"matching_hints": ["压力", "睡眠"]},
            }
        },
    }
    provider = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "non_content",
              "non_content_intent": "pullback_chat",
              "normalized_input": "压力很大睡不着"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="session-l1-guard",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-l1-guard",
            channel="grpc",
            input_mode="message",
            raw_input="压力很大睡不着",
            language_preference="zh-CN",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "none"


def test_turn_classify_overrides_pullback_for_current_question_answerable_text() -> None:
    question_catalog = {
        "question_order": ["question-06"],
        "question_index": {
            "question-06": {
                "question_id": "question-06",
                "title": "您对卧室里的光线、声音敏感度如何？",
                "input_type": "radio",
                "options": [
                    {"option_id": "B", "label": "轻微敏感，但影响不大", "aliases": []},
                    {"option_id": "D", "label": "一点微光或细小声音就会惊醒", "aliases": []},
                    {"option_id": "E", "label": "必须绝对黑暗安静", "aliases": []},
                ],
                "tags": ["人格判定"],
                "metadata": {"matching_hints": ["声光", "敏感"]},
            }
        },
    }
    provider = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "non_content",
              "non_content_intent": "pullback_chat",
              "normalized_input": "比较敏感"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="session-l1-current-question-guard",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["session_memory"]["clarification_context"] = {
        "question_id": "question-06",
        "question_title": "您对卧室里的光线、声音敏感度如何？",
        "kind": "pullback_chat",
    }

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-l1-current-question-guard",
            channel="grpc",
            input_mode="message",
            raw_input="比较敏感",
            language_preference="zh-CN",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "none"


def test_turn_classify_overrides_pullback_for_current_question_without_clarification_context() -> None:
    question_catalog = {
        "question_order": ["question-06"],
        "question_index": {
            "question-06": {
                "question_id": "question-06",
                "title": "您对卧室里的光线、声音敏感度如何？",
                "input_type": "radio",
                "options": [
                    {"option_id": "B", "label": "轻微敏感，但影响不大", "aliases": []},
                    {"option_id": "D", "label": "一点微光或细小声音就会惊醒", "aliases": []},
                    {"option_id": "E", "label": "必须绝对黑暗安静", "aliases": []},
                ],
                "tags": ["人格判定"],
                "metadata": {"matching_hints": ["声光", "敏感"]},
            }
        },
    }
    provider = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "non_content",
              "non_content_intent": "pullback_chat",
              "normalized_input": "比较敏感"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="session-l1-current-question-only",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["session_memory"]["current_question_id"] = "question-06"

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-l1-current-question-only",
            channel="grpc",
            input_mode="message",
            raw_input="比较敏感",
            language_preference="zh-CN",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "none"


def test_turn_classify_keeps_pullback_for_open_chat_on_current_text_question(question_catalog: dict) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "non_content",
              "non_content_intent": "pullback_chat",
              "normalized_input": "我想去旅游，你有什么推荐的地方吗"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="session-l1-text-question-open-chat",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["session_memory"]["current_question_id"] = "question-01"

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-l1-text-question-open-chat",
            channel="grpc",
            input_mode="message",
            raw_input="我想去旅游，你有什么推荐的地方吗",
            language_preference="zh-CN",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "non_content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "pending_non_content"


def test_turn_classify_rule_fallback_marks_open_life_topic_as_pullback_chat(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-open-life-topic-fallback",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-02"

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-open-life-topic-fallback",
            channel="grpc",
            input_mode="message",
            raw_input=OPEN_TRAVEL_CHAT,
            language_preference="zh-CN",
        ),
    )

    assert result["fallback_used"] is True
    assert result["state_patch"]["turn"]["main_branch"] == "non_content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "pending_non_content"


def test_turn_classify_still_overrides_pullback_for_numeric_answer_on_current_text_question(
    question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "non_content",
              "non_content_intent": "pullback_chat",
              "normalized_input": "22"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="session-l1-text-question-numeric-answer",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["session_memory"]["current_question_id"] = "question-01"

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-l1-text-question-numeric-answer",
            channel="grpc",
            input_mode="message",
            raw_input="22",
            language_preference="zh-CN",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "none"


def test_turn_classify_marks_refusal_as_non_content_without_detail_intent(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-refusal",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-refusal",
            channel="grpc",
            input_mode="message",
            raw_input="不做",
            language_preference="zh-CN",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "non_content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "pending_non_content"


def test_turn_classify_keeps_answer_priority_for_mixed_answer_and_chat_text(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-answer-plus-chat",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-answer-plus-chat",
            channel="grpc",
            input_mode="message",
            raw_input="我想去旅游，但平时十一点睡",
            language_preference="zh-CN",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "none"


def test_turn_classify_prompt_uses_answering_questionnaire_as_content_standard(
    question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "non_content",
              "non_content_intent": "pending_non_content",
              "normalized_input": "褪黑素怎么样，可以吃吗"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="session-l1-prompt-content-standard",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider

    TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-l1-prompt-content-standard",
            channel="grpc",
            input_mode="message",
            raw_input="褪黑素怎么样，可以吃吗",
            language_preference="zh-CN",
        ),
    )

    prompt_text = provider.calls[0][1]
    assert "是否在回答问卷" in prompt_text
    assert "不要因为话题与睡眠相关" in prompt_text
    assert "褪黑素怎么样，可以吃吗" in prompt_text


def test_turn_classify_overrides_llm_content_for_short_confirmation(question_catalog: dict) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "content",
              "non_content_intent": "none",
              "normalized_input": "是的",
              "reason": "short confirmation"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="session-l1-short-confirmation-override",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["current_question_id"] = "question-03"

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-l1-short-confirmation-override",
            channel="grpc",
            input_mode="message",
            raw_input="是的",
            language_preference="zh-CN",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "non_content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "pending_non_content"


def test_turn_classify_prompt_keeps_answer_priority_for_answer_plus_chat_examples(
    question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "content",
              "non_content_intent": "none",
              "normalized_input": "我想去旅游，但平时十一点睡"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="session-l1-prompt-answer-priority",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider

    TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-l1-prompt-answer-priority",
            channel="grpc",
            input_mode="message",
            raw_input="我想去旅游，但平时十一点睡",
            language_preference="zh-CN",
        ),
    )

    prompt_text = provider.calls[0][1]
    assert "若同一输入同时包含答案和闲聊，答案优先" in prompt_text
    assert "我想去旅游，但平时十一点睡" in prompt_text


def test_turn_classify_prompt_marks_short_confirmation_as_non_content_by_default(
    question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "non_content",
              "non_content_intent": "pending_non_content",
              "normalized_input": "是的",
              "reason": "short confirmation is not a stable questionnaire answer"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="session-l1-short-confirmation-prompt",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True

    TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-l1-short-confirmation-prompt",
            channel="grpc",
            input_mode="message",
            raw_input="是的",
            language_preference="zh-CN",
        ),
    )

    prompt_text = provider.calls[0][1]
    assert "短确认" in prompt_text
    assert "是的" in prompt_text
    assert "好的" in prompt_text
    assert "默认判为 `non_content`" in prompt_text
