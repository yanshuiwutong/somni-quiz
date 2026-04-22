"""Tests for companion runtime transition behavior."""

from __future__ import annotations

from somni_graph_quiz.contracts.graph_state import create_graph_state
from somni_graph_quiz.contracts.turn_input import TurnInput
from somni_graph_quiz.llm.client import FakeLLMProvider
from somni_graph_quiz.runtime.companion_transition import CompanionTransition

OPEN_TRAVEL_CHAT = (
    "\u6211\u60f3\u53bb\u65c5\u6e38\uff0c\u4f60\u6709\u4ec0\u4e48"
    "\u63a8\u8350\u7684\u5730\u65b9\u5417"
)
CASUAL_SMALLTALK = "\u4f60\u597d\u5440"


def test_graph_state_initializes_companion_context(companion_question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="companion-initial-context",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )

    assert graph_state["session_memory"]["companion_context"] == {
        "active": False,
        "mode": None,
        "entered_from_question_id": None,
        "rounds_since_enter": 0,
        "last_turn_continue_chat_intent": None,
        "last_trigger_reason": None,
    }


def test_transition_recent_turn_summaries_preserve_assistant_pullback_anchor() -> None:
    summaries = CompanionTransition()._recent_turn_summaries(
        [
            {
                "turn_index": 1,
                "raw_input": "最近开始的",
                "main_branch": "non_content",
                "turn_outcome": "pullback",
                "assistant_mode": "companion",
                "assistant_topic": "sleep_stress",
                "assistant_followup_kind": None,
                "assistant_pullback_anchor": "您平时通常的作息？",
            }
        ]
    )

    assert summaries == [
        {
            "raw_input": "最近开始的",
            "turn_outcome": "pullback",
            "main_branch": "non_content",
            "assistant_mode": "companion",
            "assistant_topic": "sleep_stress",
            "assistant_followup_kind": None,
            "assistant_pullback_anchor": "您平时通常的作息？",
        }
    ]


def test_transition_enters_smalltalk_from_pullback_chat(companion_question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="companion-smalltalk",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "pullback_chat"
    branch_result = {"branch_type": "non_content", "state_patch": {}, "response_facts": {}}

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-smalltalk",
            channel="grpc",
            input_mode="message",
            raw_input="你好",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is True
    assert result["state_patch"]["session_memory"]["companion_context"]["mode"] == "smalltalk"
    assert result["response_facts"]["stay_in_companion"] is True
    assert result["response_facts"]["answer_status_override"] == "NOT_RECORDED"


def test_transition_prefers_llm_companion_none_over_rule_smalltalk(
    companion_question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/companion_decision.md": """
            {
              "companion_action": "none",
              "companion_mode": "none",
              "answer_status_override": "none",
              "reason": "keep in quiz flow"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="companion-llm-none",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "pullback_chat"
    branch_result = {"branch_type": "non_content", "state_patch": {}, "response_facts": {}}

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-llm-none",
            channel="grpc",
            input_mode="message",
            raw_input="你好",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is False
    assert result["response_facts"].get("stay_in_companion") is not True
    assert result["response_facts"].get("answer_status_override") is None
    assert provider.calls[0][0] == "layer1/companion_decision.md"


def test_transition_companion_decision_prompt_expands_beyond_open_life_topics(
    companion_question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/companion_decision.md": """
            {
              "companion_action": "stay",
              "companion_mode": "supportive",
              "continue_chat_intent": "strong",
              "answer_status_override": "NOT_RECORDED",
              "reason": "user is still sharing everyday life stress"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="companion-llm-expanded-scope-prompt",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "smalltalk",
        "entered_from_question_id": "question-01",
        "rounds_since_enter": 0,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "smalltalk",
    }
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "pullback_chat"

    CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-llm-expanded-scope-prompt",
            channel="grpc",
            input_mode="message",
            raw_input="最近工作和人际关系都挺烦的，就想找个人聊聊",
            language_preference="zh-CN",
        ),
        {"branch_type": "non_content", "state_patch": {}, "response_facts": {}},
    )

    prompt_text = provider.calls[0][1]

    assert "多数非工具、非控制、非单纯答题的生活与情绪聊天" in prompt_text
    assert "工作学习、人际关系、家庭琐事、兴趣爱好、购物消费、影视音乐、宠物、周末安排、碎碎念" in prompt_text
    assert "先判断用户是不是想继续聊当前生活或情绪话题" in prompt_text
    assert "不要只把旅行、美食、散心、去哪玩这类话题当作 smalltalk 的主要范围" in prompt_text


def test_transition_companion_decision_prompt_treats_contextual_acknowledgment_as_continue_chat(
    companion_question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/companion_decision.md": """
            {
              "companion_action": "stay",
              "companion_mode": "supportive",
              "continue_chat_intent": "strong",
              "answer_status_override": "NOT_RECORDED",
              "reason": "user is acknowledging and willing to continue the current topic"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="companion-llm-contextual-ack-prompt",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "supportive",
        "entered_from_question_id": "question-02",
        "rounds_since_enter": 2,
        "last_turn_continue_chat_intent": "strong",
        "last_trigger_reason": "distress",
    }
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "pullback_chat"
    graph_state["session_memory"]["recent_turns"] = [
        {
            "raw_input": "我有的时候晚上会睡不着很晚才能睡着",
            "turn_outcome": "pullback",
            "main_branch": "non_content",
        }
    ]

    CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-llm-contextual-ack-prompt",
            channel="grpc",
            input_mode="message",
            raw_input="好的",
            language_preference="zh-CN",
        ),
        {"branch_type": "non_content", "state_patch": {}, "response_facts": {}},
    )

    prompt_text = provider.calls[0][1]

    assert "短确认 / 短片段默认先判 `weak`" in prompt_text
    assert "要结合 `companion_recent_turns`" in prompt_text
    assert "不能只因为有最近上下文就自动升成 `strong`" in prompt_text
    assert "“好的”“嗯”“可以”“行”" in prompt_text
    assert "“北京”“海边”“三天”“安静点”“工作忙的时候”“一般在晚上”" in prompt_text


def test_transition_companion_decision_prompt_treats_broad_identity_meta_questions_as_weak(
    companion_question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/companion_decision.md": """
            {
              "companion_action": "stay",
              "companion_mode": "smalltalk",
              "continue_chat_intent": "weak",
              "answer_status_override": "NOT_RECORDED",
              "reason": "identity meta question should default to weak"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="companion-llm-identity-meta-weak-prompt",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "smalltalk",
        "entered_from_question_id": "question-01",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "smalltalk",
    }
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "pullback_chat"

    CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-llm-identity-meta-weak-prompt",
            channel="grpc",
            input_mode="message",
            raw_input="你是做什么的",
            language_preference="zh-CN",
        ),
        {"branch_type": "non_content", "state_patch": {}, "response_facts": {}},
    )

    prompt_text = provider.calls[0][1]

    assert "更广泛自我介绍类" in prompt_text
    assert "你是谁" in prompt_text
    assert "你叫什么" in prompt_text
    assert "你是做什么的" in prompt_text
    assert "你能做什么" in prompt_text
    assert "默认判 `weak`" in prompt_text
    assert "不代表用户要强烈继续当前陪聊话题" in prompt_text


def test_transition_overrides_llm_none_for_content_answer_with_high_risk_distress(
    companion_question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/companion_decision.md": """
            {
              "companion_action": "none",
              "companion_mode": "none",
              "answer_status_override": "none",
              "reason": "keep in quiz flow"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="companion-llm-none-high-risk",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    graph_state["turn"]["main_branch"] = "content"
    graph_state["turn"]["non_content_intent"] = "none"
    branch_result = {
        "branch_type": "content",
        "state_patch": {
            "session_memory": {
                "answered_records": {
                    "question-01": {
                        "question_id": "question-01",
                        "selected_options": ["A"],
                        "input_value": "",
                        "field_updates": {},
                    }
                },
                "answered_question_ids": ["question-01"],
                "pending_question_ids": ["question-02", "question-03"],
                "current_question_id": "question-02",
            }
        },
        "applied_question_ids": ["question-01"],
        "modified_question_ids": [],
        "partial_question_ids": [],
        "skipped_question_ids": [],
        "rejected_unit_ids": [],
        "clarification_needed": False,
        "response_facts": {},
    }

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-llm-none-high-risk",
            channel="grpc",
            input_mode="message",
            raw_input="我18岁，我好难受我想死",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["response_facts"]["stay_in_companion"] is True
    assert result["state_patch"]["session_memory"]["companion_context"]["mode"] == "supportive"
    assert result["response_facts"]["companion_distress_level"] == "high_risk"
    assert provider.calls[0][0] == "layer1/companion_decision.md"


def test_transition_uses_llm_companion_exit_for_active_conversation(
    companion_question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/companion_decision.md": """
            {
              "companion_action": "exit",
              "companion_mode": "none",
              "answer_status_override": "NOT_RECORDED",
              "reason": "user asked to return"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="companion-llm-exit",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "smalltalk",
        "entered_from_question_id": "question-01",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "smalltalk",
    }
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "pullback_chat"
    branch_result = {"branch_type": "non_content", "state_patch": {}, "response_facts": {}}

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-llm-exit",
            channel="grpc",
            input_mode="message",
            raw_input="继续问卷吧",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["response_facts"]["return_to_quiz"] is True
    assert result["response_facts"]["answer_status_override"] == "NOT_RECORDED"
    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is False
    assert provider.calls[0][0] == "layer1/companion_decision.md"


def test_transition_falls_back_to_rules_when_companion_decision_is_invalid(
    companion_question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/companion_decision.md": """
            {
              "companion_action": "pause",
              "companion_mode": "smalltalk",
              "answer_status_override": "NOT_RECORDED",
              "reason": "invalid action"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="companion-llm-fallback",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "pullback_chat"
    branch_result = {"branch_type": "non_content", "state_patch": {}, "response_facts": {}}

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-llm-fallback",
            channel="grpc",
            input_mode="message",
            raw_input="你好",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is True
    assert result["state_patch"]["session_memory"]["companion_context"]["mode"] == "smalltalk"
    assert result["response_facts"]["stay_in_companion"] is True
    assert result["response_facts"]["answer_status_override"] == "NOT_RECORDED"


def test_transition_skips_llm_companion_decision_for_weather_query(
    companion_question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/companion_decision.md": """
            {
              "companion_action": "enter",
              "companion_mode": "smalltalk",
              "answer_status_override": "NOT_RECORDED",
              "reason": "should not be used"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="companion-weather-skip",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "weather_query"
    branch_result = {
        "branch_type": "non_content",
        "state_patch": {},
        "response_facts": {
            "non_content_mode": "weather",
            "weather_status": "success",
            "weather_city": "北京",
            "weather_summary": "晴，22C",
        },
    }

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-weather-skip",
            channel="grpc",
            input_mode="message",
            raw_input="今天天气怎么样",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert provider.calls == []
    assert result["response_facts"]["non_content_mode"] == "weather"
    assert result["response_facts"].get("stay_in_companion") is not True


def test_transition_enters_supportive_after_content_answer_with_distress(companion_question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="companion-content-entry",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["turn"]["main_branch"] = "content"
    graph_state["turn"]["non_content_intent"] = "none"
    branch_result = {
        "branch_type": "content",
        "state_patch": {
            "session_memory": {
                "answered_records": {
                    "question-02": {
                        "question_id": "question-02",
                        "selected_options": [],
                        "input_value": "12点",
                        "field_updates": {},
                    }
                },
                "answered_question_ids": ["question-02"],
                "pending_question_ids": ["question-01", "question-03"],
                "current_question_id": "question-01",
            }
        },
        "applied_question_ids": ["question-02"],
        "modified_question_ids": [],
        "partial_question_ids": [],
        "skipped_question_ids": [],
        "rejected_unit_ids": [],
        "clarification_needed": False,
        "response_facts": {},
    }

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-content-entry",
            channel="grpc",
            input_mode="message",
            raw_input="我一般12点睡，但最近总头疼睡不着",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["response_facts"]["stay_in_companion"] is True
    assert result["state_patch"]["session_memory"]["companion_context"]["mode"] == "supportive"
    assert result["response_facts"]["silent_recorded_question_ids"] == ["question-02"]


def test_transition_enters_supportive_after_content_answer_with_unhappy_tail(
    companion_question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="companion-content-unhappy-entry",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["turn"]["main_branch"] = "content"
    graph_state["turn"]["non_content_intent"] = "none"
    branch_result = {
        "branch_type": "content",
        "state_patch": {
            "session_memory": {
                "answered_records": {
                    "question-01": {
                        "question_id": "question-01",
                        "selected_options": ["A"],
                        "input_value": "",
                        "field_updates": {},
                    }
                },
                "answered_question_ids": ["question-01"],
                "pending_question_ids": ["question-02", "question-03"],
                "current_question_id": "question-02",
            }
        },
        "applied_question_ids": ["question-01"],
        "modified_question_ids": [],
        "partial_question_ids": [],
        "skipped_question_ids": [],
        "rejected_unit_ids": [],
        "clarification_needed": False,
        "response_facts": {},
    }

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-content-unhappy-entry",
            channel="grpc",
            input_mode="message",
            raw_input="18岁，但是今天我很不开心",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["response_facts"]["stay_in_companion"] is True
    assert result["response_facts"]["answer_status_override"] == "NOT_RECORDED"
    assert result["state_patch"]["session_memory"]["companion_context"]["mode"] == "supportive"
    assert result["response_facts"]["companion_distress_level"] == "normal"
    assert result["response_facts"]["silent_recorded_question_ids"] == ["question-01"]


def test_transition_marks_high_risk_distress_level_for_self_harm_tail(
    companion_question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="companion-content-high-risk-entry",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["turn"]["main_branch"] = "content"
    graph_state["turn"]["non_content_intent"] = "none"
    branch_result = {
        "branch_type": "content",
        "state_patch": {
            "session_memory": {
                "answered_records": {
                    "question-01": {
                        "question_id": "question-01",
                        "selected_options": ["A"],
                        "input_value": "",
                        "field_updates": {},
                    }
                },
                "answered_question_ids": ["question-01"],
                "pending_question_ids": ["question-02", "question-03"],
                "current_question_id": "question-02",
            }
        },
        "applied_question_ids": ["question-01"],
        "modified_question_ids": [],
        "partial_question_ids": [],
        "skipped_question_ids": [],
        "rejected_unit_ids": [],
        "clarification_needed": False,
        "response_facts": {},
    }

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-content-high-risk-entry",
            channel="grpc",
            input_mode="message",
            raw_input="我18岁，我好难受我想死",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["response_facts"]["stay_in_companion"] is True
    assert result["response_facts"]["answer_status_override"] == "NOT_RECORDED"
    assert result["state_patch"]["session_memory"]["companion_context"]["mode"] == "supportive"
    assert result["response_facts"]["companion_distress_level"] == "high_risk"
    assert result["response_facts"]["silent_recorded_question_ids"] == ["question-01"]


def test_transition_enters_supportive_after_partial_content_answer_with_distress(
    companion_question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="companion-content-partial-entry",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["turn"]["main_branch"] = "content"
    graph_state["turn"]["non_content_intent"] = "none"
    branch_result = {
        "branch_type": "content",
        "state_patch": {
            "session_memory": {
                "pending_partial_answers": {
                    "question-02": {
                        "question_id": "question-02",
                        "filled_fields": {"bedtime": "23:00"},
                        "missing_fields": ["wake_time"],
                        "source_question_state": "partial",
                    }
                },
                "partial_question_ids": ["question-02"],
                "current_question_id": "question-02",
            }
        },
        "applied_question_ids": [],
        "modified_question_ids": [],
        "partial_question_ids": ["question-02"],
        "skipped_question_ids": [],
        "rejected_unit_ids": [],
        "clarification_needed": False,
        "response_facts": {},
    }

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-content-partial-entry",
            channel="grpc",
            input_mode="message",
            raw_input="我一般11点睡，但最近总头疼睡不着",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["response_facts"]["stay_in_companion"] is True
    assert result["state_patch"]["session_memory"]["companion_context"]["mode"] == "supportive"
    assert result["response_facts"]["answer_status_override"] == "NOT_RECORDED"


def test_transition_exits_when_current_question_answered_in_companion_mode(
    companion_question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="companion-exit-current-answer",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "supportive",
        "entered_from_question_id": "question-01",
        "rounds_since_enter": 2,
        "last_turn_continue_chat_intent": "strong",
        "last_trigger_reason": "distress",
    }
    graph_state["session_memory"]["current_question_id"] = "question-01"
    graph_state["turn"]["main_branch"] = "content"
    branch_result = {
        "branch_type": "content",
        "state_patch": {
            "session_memory": {
                "answered_records": {
                    "question-01": {
                        "question_id": "question-01",
                        "selected_options": ["B"],
                        "input_value": "",
                        "field_updates": {},
                    }
                },
                "answered_question_ids": ["question-01"],
                "current_question_id": "question-02",
            }
        },
        "applied_question_ids": ["question-01"],
        "modified_question_ids": [],
        "partial_question_ids": [],
        "skipped_question_ids": [],
        "rejected_unit_ids": [],
        "clarification_needed": False,
        "response_facts": {},
    }

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-exit-current-answer",
            channel="grpc",
            input_mode="message",
            raw_input="我25到34岁",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["response_facts"].get("companion_soft_return_to_quiz") is not True
    assert result["response_facts"].get("return_to_quiz") is not True
    assert result["response_facts"].get("answer_status_override") is None
    assert result["response_facts"]["silent_recorded_question_ids"] == ["question-01"]
    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is False


def test_transition_keeps_companion_after_silent_record_for_non_current_question(
    companion_question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="companion-keep-after-silent-record-non-current",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "supportive",
        "entered_from_question_id": "question-01",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "distress",
    }
    graph_state["session_memory"]["current_question_id"] = "question-01"
    graph_state["turn"]["main_branch"] = "content"
    branch_result = {
        "branch_type": "content",
        "state_patch": {
            "session_memory": {
                "answered_records": {
                    "question-05": {
                        "question_id": "question-05",
                        "selected_options": ["E"],
                        "input_value": "",
                        "field_updates": {},
                    }
                },
                "answered_question_ids": ["question-05"],
                "current_question_id": "question-01",
            }
        },
        "applied_question_ids": ["question-05"],
        "modified_question_ids": [],
        "partial_question_ids": [],
        "skipped_question_ids": [],
        "rejected_unit_ids": [],
        "clarification_needed": False,
        "response_facts": {"content_unit_count": 1},
    }

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-keep-after-silent-record-non-current",
            channel="grpc",
            input_mode="message",
            raw_input="入睡比较困难",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["response_facts"]["stay_in_companion"] is True
    assert result["response_facts"]["answer_status_override"] == "NOT_RECORDED"
    assert result["response_facts"]["silent_recorded_question_ids"] == ["question-05"]
    assert result["response_facts"].get("companion_recorded_exit") is not True
    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is True


def test_transition_overrides_llm_stay_for_pure_answer_on_current_question(
    companion_question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/companion_decision.md": """
            {
              "companion_action": "stay",
              "companion_mode": "supportive",
              "continue_chat_intent": "weak",
              "answer_status_override": "NOT_RECORDED",
              "reason": "keep companion tone"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="companion-pure-answer-llm-stay-should-exit",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "supportive",
        "entered_from_question_id": "question-06",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "distress",
    }
    graph_state["session_memory"]["current_question_id"] = "question-06"
    graph_state["turn"]["main_branch"] = "content"
    graph_state["turn"]["non_content_intent"] = "none"
    branch_result = {
        "branch_type": "content",
        "state_patch": {
            "session_memory": {
                "answered_records": {
                    "question-06": {
                        "question_id": "question-06",
                        "selected_options": ["B"],
                        "input_value": "",
                        "field_updates": {},
                    }
                },
                "answered_question_ids": ["question-01", "question-02", "question-03", "question-04", "question-05", "question-06"],
                "current_question_id": "question-07",
            }
        },
        "applied_question_ids": ["question-06"],
        "modified_question_ids": [],
        "partial_question_ids": [],
        "skipped_question_ids": [],
        "rejected_unit_ids": [],
        "clarification_needed": False,
        "response_facts": {},
    }

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-pure-answer-llm-stay-should-exit",
            channel="grpc",
            input_mode="message",
            raw_input="比较敏感",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is False
    assert result["response_facts"].get("stay_in_companion") is not True
    assert result["response_facts"].get("answer_status_override") is None
    assert result["response_facts"]["silent_recorded_question_ids"] == ["question-06"]


def test_transition_exits_for_pure_current_answer_even_when_llm_marks_strong_chat(
    companion_question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/companion_decision.md": """
            {
              "companion_action": "stay",
              "companion_mode": "supportive",
              "continue_chat_intent": "strong",
              "answer_status_override": "NOT_RECORDED",
              "reason": "user still wants to keep chatting"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="companion-pure-answer-llm-strong-should-exit",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "supportive",
        "entered_from_question_id": "question-02",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "distress",
    }
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["turn"]["main_branch"] = "content"
    graph_state["turn"]["non_content_intent"] = "none"
    branch_result = {
        "branch_type": "content",
        "state_patch": {
            "session_memory": {
                "answered_records": {
                    "question-01": {
                        "question_id": "question-01",
                        "selected_options": ["A"],
                        "input_value": "",
                        "field_updates": {},
                    },
                    "question-02": {
                        "question_id": "question-02",
                        "selected_options": [],
                        "input_value": "23:00",
                        "field_updates": {"bedtime": "23:00"},
                    }
                },
                "answered_question_ids": ["question-01", "question-02"],
                "current_question_id": "question-03",
            }
        },
        "applied_question_ids": ["question-02"],
        "modified_question_ids": [],
        "partial_question_ids": [],
        "skipped_question_ids": [],
        "rejected_unit_ids": [],
        "clarification_needed": False,
        "response_facts": {"content_unit_count": 1},
    }

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-pure-answer-llm-strong-should-exit",
            channel="grpc",
            input_mode="message",
            raw_input="11鐐圭潯",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is False
    assert result["response_facts"].get("stay_in_companion") is not True
    assert result["response_facts"].get("answer_status_override") is None
    assert result["response_facts"]["silent_recorded_question_ids"] == ["question-02"]


def test_transition_keeps_companion_when_current_question_answer_and_chat_mix_are_both_present(
    companion_question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="companion-keep-for-answer-plus-chat",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "smalltalk",
        "entered_from_question_id": "question-02",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "smalltalk",
    }
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["turn"]["main_branch"] = "content"
    graph_state["turn"]["non_content_intent"] = "none"
    branch_result = {
        "branch_type": "content",
        "state_patch": {
            "session_memory": {
                "answered_records": {
                    "question-02": {
                        "question_id": "question-02",
                        "selected_options": [],
                        "input_value": "19:00-10:00",
                        "field_updates": {"bedtime": "19:00", "wake_time": "10:00"},
                    }
                },
                "answered_question_ids": ["question-02"],
                "current_question_id": "question-03",
            }
        },
        "applied_question_ids": ["question-02"],
        "modified_question_ids": [],
        "partial_question_ids": [],
        "skipped_question_ids": [],
        "rejected_unit_ids": [],
        "clarification_needed": False,
        "response_facts": {},
    }

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-keep-for-answer-plus-chat",
            channel="grpc",
            input_mode="message",
            raw_input="我想去旅游，但平时早十晚七",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["response_facts"]["stay_in_companion"] is True
    assert result["response_facts"]["answer_status_override"] == "NOT_RECORDED"
    assert result["response_facts"]["silent_recorded_question_ids"] == ["question-02"]
    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is True


def test_transition_keeps_companion_for_explicit_defer_chat_and_answer_mix(
    companion_question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="companion-keep-for-explicit-defer-chat-and-answer-mix",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "smalltalk",
        "entered_from_question_id": "question-02",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "smalltalk",
    }
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["turn"]["main_branch"] = "content"
    graph_state["turn"]["non_content_intent"] = "none"
    branch_result = {
        "branch_type": "content",
        "state_patch": {
            "session_memory": {
                "answered_records": {
                    "question-02": {
                        "question_id": "question-02",
                        "selected_options": [],
                        "input_value": "22:00",
                        "field_updates": {"bedtime": "22:00"},
                    }
                },
                "answered_question_ids": ["question-02"],
                "current_question_id": "question-03",
            }
        },
        "applied_question_ids": ["question-02"],
        "modified_question_ids": [],
        "partial_question_ids": [],
        "skipped_question_ids": [],
        "rejected_unit_ids": [],
        "clarification_needed": False,
        "response_facts": {"content_unit_count": 1},
    }

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-keep-for-explicit-defer-chat-and-answer-mix",
            channel="grpc",
            input_mode="message",
            raw_input="鍏堣亰鍒殑锛屼笉杩囨垜涓€鑸?0鐐圭潯",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["response_facts"]["stay_in_companion"] is True
    assert result["response_facts"]["answer_status_override"] == "NOT_RECORDED"
    assert result["response_facts"]["silent_recorded_question_ids"] == ["question-02"]
    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is True


def test_transition_keeps_companion_for_single_partial_unit_even_when_not_current_question(
    companion_question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/companion_decision.md": """
            {
              "companion_action": "stay",
              "companion_mode": "supportive",
              "continue_chat_intent": "weak",
              "answer_status_override": "NOT_RECORDED",
              "reason": "keep companion tone"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="companion-single-partial-should-exit",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "supportive",
        "entered_from_question_id": "question-06",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "distress",
    }
    graph_state["session_memory"]["current_question_id"] = "question-06"
    graph_state["turn"]["main_branch"] = "content"
    graph_state["turn"]["non_content_intent"] = "none"
    branch_result = {
        "branch_type": "content",
        "state_patch": {
            "session_memory": {
                "pending_partial_answers": {
                    "question-02": {
                        "question_id": "question-02",
                        "filled_fields": {"wake_time": "11:00"},
                        "missing_fields": ["bedtime"],
                        "source_question_state": "partial",
                    }
                },
                "partial_question_ids": ["question-02"],
                "current_question_id": "question-02",
            }
        },
        "applied_question_ids": [],
        "modified_question_ids": [],
        "partial_question_ids": ["question-02"],
        "skipped_question_ids": [],
        "rejected_unit_ids": [],
        "clarification_needed": False,
        "response_facts": {"content_unit_count": 1},
    }

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-single-partial-should-exit",
            channel="grpc",
            input_mode="message",
            raw_input="11点起",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is True
    assert result["response_facts"]["stay_in_companion"] is True
    assert result["response_facts"]["answer_status_override"] == "NOT_RECORDED"


def test_transition_keeps_companion_for_single_modified_unit_even_when_not_current_question(
    companion_question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/companion_decision.md": """
            {
              "companion_action": "stay",
              "companion_mode": "smalltalk",
              "continue_chat_intent": "weak",
              "answer_status_override": "NOT_RECORDED",
              "reason": "keep companion tone"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="companion-single-modified-should-exit",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "smalltalk",
        "entered_from_question_id": "question-07",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "smalltalk",
    }
    graph_state["session_memory"]["current_question_id"] = "question-07"
    graph_state["turn"]["main_branch"] = "content"
    graph_state["turn"]["non_content_intent"] = "none"
    branch_result = {
        "branch_type": "content",
        "state_patch": {
            "session_memory": {
                "answered_records": {
                    "question-06": {
                        "question_id": "question-06",
                        "selected_options": ["C"],
                        "input_value": "",
                        "field_updates": {},
                    }
                },
                "answered_question_ids": ["question-06"],
                "current_question_id": "question-07",
            }
        },
        "applied_question_ids": [],
        "modified_question_ids": ["question-06"],
        "partial_question_ids": [],
        "skipped_question_ids": [],
        "rejected_unit_ids": [],
        "clarification_needed": False,
        "response_facts": {"content_unit_count": 1},
    }

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-single-modified-should-exit",
            channel="grpc",
            input_mode="message",
            raw_input="比较敏感",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is True
    assert result["response_facts"]["stay_in_companion"] is True
    assert result["response_facts"]["answer_status_override"] == "NOT_RECORDED"


def test_transition_suppresses_llm_exit_overlay_for_single_success_unit_when_companion_inactive(
    companion_question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/companion_decision.md": """
            {
              "companion_action": "exit",
              "companion_mode": "none",
              "continue_chat_intent": "weak",
              "answer_status_override": "NOT_RECORDED",
              "reason": "return to quiz"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="inactive-single-success-no-overlay",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    graph_state["turn"]["main_branch"] = "content"
    graph_state["turn"]["non_content_intent"] = "none"
    branch_result = {
        "branch_type": "content",
        "state_patch": {
            "session_memory": {
                "answered_records": {
                    "question-06": {
                        "question_id": "question-06",
                        "selected_options": ["C"],
                        "input_value": "",
                        "field_updates": {},
                    }
                },
                "answered_question_ids": ["question-06"],
                "current_question_id": "question-07",
            }
        },
        "applied_question_ids": ["question-06"],
        "modified_question_ids": [],
        "partial_question_ids": [],
        "skipped_question_ids": [],
        "rejected_unit_ids": [],
        "clarification_needed": False,
        "response_facts": {"content_unit_count": 1},
    }

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="inactive-single-success-no-overlay",
            channel="grpc",
            input_mode="message",
            raw_input="比较敏感",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is False
    assert result["response_facts"].get("stay_in_companion") is not True
    assert result["response_facts"].get("return_to_quiz") is not True
    assert result["response_facts"].get("companion_soft_return_to_quiz") is not True
    assert result["response_facts"].get("answer_status_override") is None


def test_transition_exits_active_companion_for_weather_branch_result(
    companion_question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/companion_decision.md": """
            {
              "companion_action": "stay",
              "companion_mode": "smalltalk",
              "answer_status_override": "NOT_RECORDED",
              "reason": "should not be used"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="companion-weather-exit",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "smalltalk",
        "entered_from_question_id": "question-01",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "smalltalk",
    }
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "pending_non_content"

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-weather-exit",
            channel="grpc",
            input_mode="message",
            raw_input="今天天气怎么样",
            language_preference="zh-CN",
        ),
        {
            "branch_type": "non_content",
            "state_patch": {},
            "response_facts": {
                "non_content_mode": "weather",
                "non_content_action": "weather_query",
                "weather_status": "success",
                "weather_city": "北京",
                "weather_summary": "晴，22C",
            },
        },
    )

    assert provider.calls == []
    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is False
    assert result["response_facts"]["companion_force_main_flow"] is True


def test_transition_resets_supportive_round_counter_on_strong_turn_at_round_four(
    companion_question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="companion-reset-rounds",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "supportive",
        "entered_from_question_id": "question-02",
        "rounds_since_enter": 4,
        "last_turn_continue_chat_intent": "strong",
        "last_trigger_reason": "distress",
    }
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "pullback_chat"
    branch_result = {"branch_type": "non_content", "state_patch": {}, "response_facts": {}}

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-reset-rounds",
            channel="grpc",
            input_mode="message",
            raw_input="其实还有一件事让我更烦",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["state_patch"]["session_memory"]["companion_context"]["rounds_since_enter"] == 0
    assert result["response_facts"]["stay_in_companion"] is True


def test_transition_resets_supportive_round_counter_on_any_strong_turn_before_threshold(
    companion_question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="companion-reset-rounds-early",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "supportive",
        "entered_from_question_id": "question-02",
        "rounds_since_enter": 2,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "distress",
    }
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "pullback_chat"
    branch_result = {"branch_type": "non_content", "state_patch": {}, "response_facts": {}}

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-reset-rounds-early",
            channel="grpc",
            input_mode="message",
            raw_input="我想找个安静点的海边住两天，最好吃的也不错",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["response_facts"]["stay_in_companion"] is True
    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is True
    assert result["state_patch"]["session_memory"]["companion_context"]["rounds_since_enter"] == 0


def test_transition_returns_to_quiz_when_supportive_turn_is_no_longer_strong(
    companion_question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="companion-return-round-four",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "supportive",
        "entered_from_question_id": "question-02",
        "rounds_since_enter": 4,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "distress",
    }
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "pullback_chat"
    branch_result = {"branch_type": "non_content", "state_patch": {}, "response_facts": {}}

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-return-round-four",
            channel="grpc",
            input_mode="message",
            raw_input="嗯，谢谢你",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["response_facts"]["companion_soft_return_to_quiz"] is True
    assert result["response_facts"].get("return_to_quiz") is not True
    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is False


def test_transition_keeps_supportive_mode_for_open_question_chat_at_round_four(
    companion_question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="companion-open-question-round-four",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "supportive",
        "entered_from_question_id": "question-02",
        "rounds_since_enter": 4,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "distress",
    }
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "pullback_chat"
    branch_result = {"branch_type": "non_content", "state_patch": {}, "response_facts": {}}

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-open-question-round-four",
            channel="grpc",
            input_mode="message",
            raw_input="我想明天去旅游，你推荐去哪",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["response_facts"]["stay_in_companion"] is True
    assert result["response_facts"].get("return_to_quiz") is not True
    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is True
    assert result["state_patch"]["session_memory"]["companion_context"]["rounds_since_enter"] == 0


def test_transition_explicit_return_to_quiz_exits_companion_immediately(
    companion_question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="companion-explicit-return",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "smalltalk",
        "entered_from_question_id": "question-01",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "smalltalk",
    }
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "pullback_chat"
    branch_result = {"branch_type": "non_content", "state_patch": {}, "response_facts": {}}

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-explicit-return",
            channel="grpc",
            input_mode="message",
            raw_input="继续问卷吧",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["response_facts"]["return_to_quiz"] is True
    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is False


def test_transition_enforces_smalltalk_threshold_even_when_llm_says_stay(
    companion_question_catalog: dict,
) -> None:
    weak_turn_text = "\u597d\u7684"
    provider = FakeLLMProvider(
        responses={
            "layer1/companion_decision.md": """
            {
              "companion_action": "stay",
              "companion_mode": "smalltalk",
              "answer_status_override": "NOT_RECORDED",
              "reason": "keep chatting"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="companion-smalltalk-threshold-llm",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "smalltalk",
        "entered_from_question_id": "question-01",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "smalltalk",
    }
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "pullback_chat"

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-smalltalk-threshold-llm",
            channel="grpc",
            input_mode="message",
            raw_input="我想去旅游",
            language_preference="zh-CN",
        ),
        {"branch_type": "non_content", "state_patch": {}, "response_facts": {}},
    )
    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-smalltalk-threshold-llm",
            channel="grpc",
            input_mode="message",
            raw_input=weak_turn_text,
            language_preference="zh-CN",
        ),
        {"branch_type": "non_content", "state_patch": {}, "response_facts": {}},
    )

    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is False
    assert result["response_facts"]["companion_soft_return_to_quiz"] is True
    assert result["response_facts"].get("return_to_quiz") is not True
    assert result["response_facts"].get("stay_in_companion") is not True


def test_transition_resets_smalltalk_round_counter_on_any_strong_turn_before_threshold(
    companion_question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="companion-smalltalk-reset-rounds-early",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "smalltalk",
        "entered_from_question_id": "question-01",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "smalltalk",
    }
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "pullback_chat"
    branch_result = {"branch_type": "non_content", "state_patch": {}, "response_facts": {}}

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-smalltalk-reset-rounds-early",
            channel="grpc",
            input_mode="message",
            raw_input="我想去旅游，你有什么推荐的地方吗",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["response_facts"]["stay_in_companion"] is True
    assert result["response_facts"].get("companion_soft_return_to_quiz") is not True
    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is True
    assert result["state_patch"]["session_memory"]["companion_context"]["rounds_since_enter"] == 0
    assert result["state_patch"]["session_memory"]["companion_context"]["last_turn_continue_chat_intent"] == "strong"


def test_transition_uses_llm_continue_chat_intent_to_reset_smalltalk_rounds(
    companion_question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/companion_decision.md": """
            {
              "companion_action": "stay",
              "companion_mode": "smalltalk",
              "continue_chat_intent": "strong",
              "answer_status_override": "NOT_RECORDED",
              "reason": "user still wants to keep chatting about travel"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="companion-smalltalk-llm-continue-strong",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "smalltalk",
        "entered_from_question_id": "question-01",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "smalltalk",
    }
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "pullback_chat"

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-smalltalk-llm-continue-strong",
            channel="grpc",
            input_mode="message",
            raw_input="我想去旅游，你有什么推荐的地方吗",
            language_preference="zh-CN",
        ),
        {"branch_type": "non_content", "state_patch": {}, "response_facts": {}},
    )

    assert result["response_facts"]["stay_in_companion"] is True
    assert result["response_facts"].get("companion_soft_return_to_quiz") is not True
    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is True
    assert result["state_patch"]["session_memory"]["companion_context"]["rounds_since_enter"] == 0
    assert result["state_patch"]["session_memory"]["companion_context"]["last_turn_continue_chat_intent"] == "strong"


def test_transition_overrides_llm_exit_for_open_question_and_keeps_companion(
    companion_question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/companion_decision.md": """
            {
              "companion_action": "exit",
              "companion_mode": "none",
              "continue_chat_intent": "weak",
              "answer_status_override": "NOT_RECORDED",
              "reason": "return to quiz"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="companion-smalltalk-llm-exit-overridden-by-open-question",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "smalltalk",
        "entered_from_question_id": "question-01",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "smalltalk",
    }
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "pullback_chat"

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-smalltalk-llm-exit-overridden-by-open-question",
            channel="grpc",
            input_mode="message",
            raw_input="奶茶有什么坏处吗",
            language_preference="zh-CN",
        ),
        {"branch_type": "non_content", "state_patch": {}, "response_facts": {}},
    )

    assert result["response_facts"]["stay_in_companion"] is True
    assert result["response_facts"].get("return_to_quiz") is not True
    assert result["response_facts"].get("companion_soft_return_to_quiz") is not True
    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is True
    assert result["state_patch"]["session_memory"]["companion_context"]["rounds_since_enter"] == 0
    assert result["state_patch"]["session_memory"]["companion_context"]["last_turn_continue_chat_intent"] == "strong"


def test_transition_upgrades_llm_weak_continue_chat_intent_for_open_life_topic(
    companion_question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/companion_decision.md": """
            {
              "companion_action": "stay",
              "companion_mode": "smalltalk",
              "continue_chat_intent": "weak",
              "answer_status_override": "NOT_RECORDED",
              "reason": "user asked an open follow-up"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="companion-smalltalk-llm-continue-weak-upgraded",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "smalltalk",
        "entered_from_question_id": "question-01",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "smalltalk",
    }
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "pullback_chat"

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-smalltalk-llm-continue-weak-upgraded",
            channel="grpc",
            input_mode="message",
            raw_input=OPEN_TRAVEL_CHAT,
            language_preference="zh-CN",
        ),
        {"branch_type": "non_content", "state_patch": {}, "response_facts": {}},
    )

    assert result["response_facts"]["stay_in_companion"] is True
    assert result["response_facts"].get("companion_soft_return_to_quiz") is not True
    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is True
    assert result["state_patch"]["session_memory"]["companion_context"]["rounds_since_enter"] == 0
    assert result["state_patch"]["session_memory"]["companion_context"]["last_turn_continue_chat_intent"] == "strong"


def test_transition_considers_llm_companion_entry_for_open_life_topic_content_turn(
    companion_question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/companion_decision.md": """
            {
              "companion_action": "enter",
              "companion_mode": "smalltalk",
              "continue_chat_intent": "strong",
              "answer_status_override": "NOT_RECORDED",
              "reason": "user wants to keep chatting about travel"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="companion-open-chat-content-entry",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    graph_state["turn"]["main_branch"] = "content"
    graph_state["turn"]["non_content_intent"] = "none"

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-open-chat-content-entry",
            channel="grpc",
            input_mode="message",
            raw_input=OPEN_TRAVEL_CHAT,
            language_preference="zh-CN",
        ),
        {
            "branch_type": "content",
            "state_patch": {},
            "applied_question_ids": [],
            "modified_question_ids": [],
            "partial_question_ids": [],
            "skipped_question_ids": [],
            "rejected_unit_ids": [],
            "clarification_needed": False,
            "response_facts": {},
        },
    )

    assert provider.calls[0][0] == "layer1/companion_decision.md"
    assert result["response_facts"]["stay_in_companion"] is True
    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is True
    assert result["state_patch"]["session_memory"]["companion_context"]["mode"] == "smalltalk"
    assert result["state_patch"]["session_memory"]["companion_context"]["rounds_since_enter"] == 0


def test_transition_considers_llm_companion_entry_for_casual_smalltalk_content_turn(
    companion_question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/companion_decision.md": """
            {
              "companion_action": "enter",
              "companion_mode": "smalltalk",
              "continue_chat_intent": "weak",
              "answer_status_override": "NOT_RECORDED",
              "reason": "user is greeting and should be handled by companion"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="companion-smalltalk-content-entry",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    graph_state["turn"]["main_branch"] = "content"
    graph_state["turn"]["non_content_intent"] = "none"

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-smalltalk-content-entry",
            channel="grpc",
            input_mode="message",
            raw_input=CASUAL_SMALLTALK,
            language_preference="zh-CN",
        ),
        {
            "branch_type": "content",
            "state_patch": {},
            "applied_question_ids": [],
            "modified_question_ids": [],
            "partial_question_ids": [],
            "skipped_question_ids": [],
            "rejected_unit_ids": [],
            "clarification_needed": True,
            "response_facts": {},
        },
    )

    assert provider.calls[0][0] == "layer1/companion_decision.md"
    assert result["response_facts"]["stay_in_companion"] is True
    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is True
    assert result["state_patch"]["session_memory"]["companion_context"]["mode"] == "smalltalk"
    assert result["state_patch"]["session_memory"]["companion_context"]["rounds_since_enter"] == 0


def test_transition_rule_fallback_enters_companion_for_casual_smalltalk_content_turn(
    companion_question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="companion-smalltalk-content-entry-rule-fallback",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["turn"]["main_branch"] = "content"
    graph_state["turn"]["non_content_intent"] = "none"

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-smalltalk-content-entry-rule-fallback",
            channel="grpc",
            input_mode="message",
            raw_input=CASUAL_SMALLTALK,
            language_preference="zh-CN",
        ),
        {
            "branch_type": "content",
            "state_patch": {},
            "applied_question_ids": [],
            "modified_question_ids": [],
            "partial_question_ids": [],
            "skipped_question_ids": [],
            "rejected_unit_ids": [],
            "clarification_needed": True,
            "response_facts": {},
        },
    )

    assert result["response_facts"]["stay_in_companion"] is True
    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is True
    assert result["state_patch"]["session_memory"]["companion_context"]["mode"] == "smalltalk"
    assert result["state_patch"]["session_memory"]["companion_context"]["rounds_since_enter"] == 0


def test_transition_uses_llm_continue_chat_intent_to_reset_supportive_rounds(
    companion_question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/companion_decision.md": """
            {
              "companion_action": "stay",
              "companion_mode": "supportive",
              "continue_chat_intent": "strong",
              "answer_status_override": "NOT_RECORDED",
              "reason": "user still wants to keep exploring the topic"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="companion-llm-continue-strong",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "supportive",
        "entered_from_question_id": "question-02",
        "rounds_since_enter": 2,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "distress",
    }
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "pullback_chat"

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-llm-continue-strong",
            channel="grpc",
            input_mode="message",
            raw_input="好的",
            language_preference="zh-CN",
        ),
        {"branch_type": "non_content", "state_patch": {}, "response_facts": {}},
    )

    assert result["response_facts"]["stay_in_companion"] is True
    assert result["state_patch"]["session_memory"]["companion_context"]["rounds_since_enter"] == 0
    assert result["state_patch"]["session_memory"]["companion_context"]["last_turn_continue_chat_intent"] == "strong"


def test_transition_uses_llm_continue_chat_intent_to_soft_return_at_threshold(
    companion_question_catalog: dict,
) -> None:
    weak_turn_text = "\u597d\u7684"
    provider = FakeLLMProvider(
        responses={
            "layer1/companion_decision.md": """
            {
              "companion_action": "stay",
              "companion_mode": "supportive",
              "continue_chat_intent": "weak",
              "answer_status_override": "NOT_RECORDED",
              "reason": "user is wrapping up"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="companion-llm-continue-weak",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "supportive",
        "entered_from_question_id": "question-02",
        "rounds_since_enter": 4,
        "last_turn_continue_chat_intent": "strong",
        "last_trigger_reason": "distress",
    }
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "pullback_chat"

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-llm-continue-weak",
            channel="grpc",
            input_mode="message",
            raw_input="我想找个海边城市放空两天，你推荐去哪",
            language_preference="zh-CN",
        ),
        {"branch_type": "non_content", "state_patch": {}, "response_facts": {}},
    )
    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-llm-continue-weak",
            channel="grpc",
            input_mode="message",
            raw_input=weak_turn_text,
            language_preference="zh-CN",
        ),
        {"branch_type": "non_content", "state_patch": {}, "response_facts": {}},
    )

    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is False
    assert result["response_facts"]["companion_soft_return_to_quiz"] is True
    assert result["response_facts"].get("stay_in_companion") is not True


def test_transition_soft_returns_at_threshold_for_weak_followup_choice_reply(
    companion_question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="companion-weak-choice-soft-return",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "supportive",
        "entered_from_question_id": "question-02",
        "rounds_since_enter": 4,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "distress",
    }
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "pullback_chat"
    graph_state["session_memory"]["recent_turns"] = [
        {
            "turn_index": 0,
            "raw_input": "脑子停不下来",
            "main_branch": "non_content",
            "turn_outcome": "pullback",
            "assistant_mode": "companion",
            "assistant_topic": "sleep_stress",
            "assistant_followup_kind": "open_followup",
        }
    ]

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-weak-choice-soft-return",
            channel="grpc",
            input_mode="message",
            raw_input="我选第二个",
            language_preference="zh-CN",
        ),
        {"branch_type": "non_content", "state_patch": {}, "response_facts": {}},
    )

    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is False
    assert result["response_facts"]["companion_soft_return_to_quiz"] is True
    assert result["response_facts"].get("stay_in_companion") is not True


def test_transition_forces_main_flow_exit_for_control_input_even_when_llm_says_stay(
    companion_question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/companion_decision.md": """
            {
              "companion_action": "stay",
              "companion_mode": "supportive",
              "answer_status_override": "NOT_RECORDED",
              "reason": "keep supportive tone"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="companion-control-exit",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "supportive",
        "entered_from_question_id": "question-02",
        "rounds_since_enter": 2,
        "last_turn_continue_chat_intent": "strong",
        "last_trigger_reason": "distress",
    }
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "skip"

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-control-exit",
            channel="grpc",
            input_mode="message",
            raw_input="跳过",
            language_preference="zh-CN",
        ),
        {
            "branch_type": "non_content",
            "state_patch": {},
            "response_facts": {
                "non_content_mode": "control",
                "control_action": "skip",
                "non_content_action": "skip",
            },
        },
    )

    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is False
    assert result["response_facts"]["companion_force_main_flow"] is True
    assert result["response_facts"].get("stay_in_companion") is not True


def test_transition_marks_completion_wrapup_for_final_question_answered_in_companion(
    companion_question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/companion_decision.md": """
            {
              "companion_action": "stay",
              "companion_mode": "supportive",
              "answer_status_override": "NOT_RECORDED",
              "reason": "user is still talking"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="companion-final-question-wrapup",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "supportive",
        "entered_from_question_id": "question-03",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "strong",
        "last_trigger_reason": "distress",
    }
    graph_state["session_memory"]["current_question_id"] = "question-03"
    graph_state["turn"]["main_branch"] = "content"
    graph_state["turn"]["non_content_intent"] = "none"

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-final-question-wrapup",
            channel="grpc",
            input_mode="message",
            raw_input="需要缓冲，而且我还是有点烦",
            language_preference="zh-CN",
        ),
        {
            "branch_type": "content",
            "state_patch": {
                "session_memory": {
                    "answered_records": {
                        "question-01": {
                            "question_id": "question-01",
                            "selected_options": ["A"],
                            "input_value": "",
                            "field_updates": {},
                        },
                        "question-02": {
                            "question_id": "question-02",
                            "selected_options": [],
                            "input_value": "23点",
                            "field_updates": {},
                        },
                        "question-03": {
                            "question_id": "question-03",
                            "selected_options": ["B"],
                            "input_value": "",
                            "field_updates": {},
                        },
                    },
                    "answered_question_ids": ["question-01", "question-02", "question-03"],
                    "pending_question_ids": [],
                    "current_question_id": None,
                }
            },
            "applied_question_ids": ["question-03"],
            "modified_question_ids": [],
            "partial_question_ids": [],
            "skipped_question_ids": [],
            "rejected_unit_ids": [],
            "clarification_needed": False,
            "response_facts": {},
        },
    )

    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is False
    assert result["response_facts"]["companion_completion_wrapup"] is True
    assert result["response_facts"].get("answer_status_override") is None
