"""Tests for response composition."""

import json
from types import SimpleNamespace

from somni_graph_quiz.contracts.finalized_turn_context import create_finalized_turn_context
from somni_graph_quiz.llm.client import FakeLLMProvider
from somni_graph_quiz.nodes.layer3.respond import ResponseComposerNode


def _extract_payload_from_prompt(prompt_text: str) -> dict:
    marker = "## Input Payload"
    start = prompt_text.rindex(marker)
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


def test_response_composer_stay_in_companion_overrides_answered_message() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="answered",
        updated_answer_record={"answers": [{"question_id": "question-01", "selected_options": ["B"]}]},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "您平时通常几点睡？"},
        finalized=False,
        response_language="zh-CN",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "supportive",
            "recorded_question_summaries": [{"question_id": "question-01", "title": "您的年龄段？"}],
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "已记录" not in message
    assert "下一题" not in message
    assert "慢慢说" in message or "继续" in message or "聊" in message


def test_response_composer_uses_companion_prompt_when_staying_in_companion() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/companion_response.md": """
            {
              "assistant_message": "想出去走走也不错呀。你是更想看海、看山，还是只想找个能放松一点的地方？"
            }
            """
        }
    )
    finalized = create_finalized_turn_context(
        turn_outcome="answered",
        updated_answer_record={"answers": [{"question_id": "question-01", "selected_options": ["B"]}]},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "您平时通常几点睡？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="我想明天去旅游，你推荐去哪",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "supportive",
            "silent_recorded_question_ids": ["question-01"],
            "llm_provider": provider,
            "llm_available": True,
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert message == "想出去走走也不错呀。你是更想看海、看山，还是只想找个能放松一点的地方？"
    assert len(provider.calls) == 1
    assert provider.calls[0][0] == "layer3/companion_response.md"


def test_response_composer_companion_prompt_payload_includes_continue_chat_constraints() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/companion_response.md": """
            {
              "assistant_message": "西红柿炒鸡蛋挺合适的，酸甜一点也比较下饭。要是你中午想吃得更舒服点，再配个青菜或者热汤会更顺口。"
            }
            """
        }
    )
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-03",
        current_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        next_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="今天中午吃什么，西红柿炒鸡蛋怎么样",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "smalltalk",
            "continue_chat_intent": "strong",
            "llm_provider": provider,
            "llm_available": True,
        },
    )

    message = ResponseComposerNode().run(finalized)
    payload = _extract_payload_from_prompt(provider.calls[0][1])

    assert "西红柿炒鸡蛋" in message
    assert payload["continue_chat_intent"] == "strong"
    assert payload["companion_can_soft_return"] is False
    assert payload["stay_in_companion"] is True


def test_response_composer_companion_prompt_instructs_language_adaptation_from_current_turn() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/companion_response.md": """
            {
              "assistant_message": "That sounds like a lot to carry. Want to talk through what felt heaviest today?"
            }
            """
        }
    )
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-03",
        current_question={"question_id": "question-03", "title": "Sleep question"},
        next_question={"question_id": "question-03", "title": "Sleep question"},
        finalized=False,
        response_language="zh-CN",
        raw_input="Actually can we talk in English for a bit?",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "smalltalk",
            "continue_chat_intent": "strong",
            "llm_provider": provider,
            "llm_available": True,
        },
    )

    ResponseComposerNode().run(finalized)

    prompt_text = provider.calls[0][1]

    assert "若用户本轮明显切换语言，自然跟随该语言回复。" in prompt_text
    assert "若用户混合使用多种语言，优先使用其中的主要语言回复。" in prompt_text


def test_response_composer_companion_prompt_encourages_natural_pacing_and_gradual_return() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/companion_response.md": """
            {
              "assistant_message": "这听起来确实有点累。我们可以先顺着这个感觉聊一点，再慢慢往下看。"
            }
            """
        }
    )
    finalized = create_finalized_turn_context(
        turn_outcome="answered",
        updated_answer_record={"answers": [{"question_id": "question-01", "selected_options": ["B"]}]},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "您平时通常几点睡？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="今天真的有点烦",
        response_facts={
            "companion_soft_return_to_quiz": True,
            "companion_mode": "supportive",
            "silent_recorded_question_ids": ["question-01"],
            "llm_provider": provider,
            "llm_available": True,
        },
    )

    ResponseComposerNode().run(finalized)

    prompt_text = provider.calls[0][1]

    assert "回复可以比纯短句稍微展开一点，让语气更自然、更像真实聊天" in prompt_text
    assert "不要为了显得简洁而把回复压缩得生硬" in prompt_text
    assert "先接住用户当前的话题、情绪或感受，再顺势慢慢带回问卷" in prompt_text
    assert "不要把回问卷写成任务切换或突然抛出下一个问题" in prompt_text


def test_response_composer_companion_prompt_allows_light_follow_up_to_keep_chat_flowing() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/companion_response.md": """
            {
              "assistant_message": "这听起来确实挺累的。要是你愿意，也可以和我说说今天最卡住你的那一段。"
            }
            """
        }
    )
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-03",
        current_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        next_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="今天真有点烦",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "supportive",
            "continue_chat_intent": "strong",
            "llm_provider": provider,
            "llm_available": True,
        },
    )

    ResponseComposerNode().run(finalized)

    prompt_text = provider.calls[0][1]

    assert "可视情况在回复结尾加入一句轻量、开放式、容易接话的询问" in prompt_text
    assert "不是每轮都问" in prompt_text
    assert "每次回复最多只加一个问题" in prompt_text
    assert "这个问题不一定要直接对应当前问卷题" in prompt_text
    assert "但要和用户刚聊的话题、状态、作息感受或睡眠相关感受保持相邻" in prompt_text
    assert "在需要回到问卷时，可以先承接一句或轻问一句，再自然点回继续问卷的方向" in prompt_text


def test_response_composer_companion_prompt_expands_topic_scope_and_allows_slightly_longer_replies() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/companion_response.md": """
            {
              "assistant_message": "这段时间听起来你确实有点被很多事情一起压着。要是你愿意，也可以先从最近最让你烦的一件事慢慢说。"
            }
            """
        }
    )
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-03",
        current_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        next_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="最近工作和人际关系都挺烦的",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "supportive",
            "continue_chat_intent": "strong",
            "llm_provider": provider,
            "llm_available": True,
        },
    )

    ResponseComposerNode().run(finalized)

    prompt_text = provider.calls[0][1]

    assert "大多数生活与情绪话题都可以自然接住并继续聊" in prompt_text
    assert "工作学习、家庭琐事、人际关系、兴趣爱好、购物消费、影视音乐、宠物、周末安排、碎碎念、一般压力和烦躁" in prompt_text
    assert "回复可以比现在稍微长一些" in prompt_text
    assert "允许多一句承接、多一句细化或多一句轻追问" in prompt_text
    assert "不要求每轮都挂问卷" in prompt_text


def test_response_composer_companion_prompt_supports_short_contextual_fragments() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/companion_response.md": """
            {
              "assistant_message": "北京也不错呀，你是更想找热闹一点的地方，还是更想轻松散散心？"
            }
            """
        }
    )
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-03",
        current_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        next_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="北京",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "smalltalk",
            "continue_chat_intent": "weak",
            "llm_provider": provider,
            "llm_available": True,
            "companion_recent_turns": [
                {
                    "raw_input": "我想去旅游，你推荐去哪",
                    "turn_outcome": "pullback",
                    "main_branch": "non_content",
                }
            ],
        },
    )

    ResponseComposerNode().run(finalized)

    prompt_text = provider.calls[0][1]

    assert "像“北京”“三天”“安静点”“工作忙的时候”这样的短片段输入" in prompt_text
    assert "优先理解成对上一轮知心话题的补充" in prompt_text
    assert "不要轻易退回“你想接着聊什么都可以”这类空泛模板" in prompt_text


def test_response_composer_companion_prompt_deescalates_after_one_follow_up() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/companion_response.md": """
            {
              "assistant_message": "听起来更多是在工作忙的时候冒出来。我们先把这点放在这儿，后面也可以慢慢顺着看看你的作息和状态。"
            }
            """
        }
    )
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-03",
        current_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        next_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="工作忙的时候",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "supportive",
            "continue_chat_intent": "weak",
            "llm_provider": provider,
            "llm_available": True,
            "companion_recent_turns": [
                {
                    "raw_input": "我最近晚上总是睡不着",
                    "turn_outcome": "pullback",
                    "main_branch": "non_content",
                    "assistant_mode": "companion",
                    "assistant_topic": "sleep_stress",
                    "assistant_followup_kind": "open_followup",
                }
            ],
        },
    )

    ResponseComposerNode().run(finalized)

    prompt_text = provider.calls[0][1]

    assert "同一话题里可以先追问一次，但后续默认不再持续深挖" in prompt_text
    assert "如果上一轮已经追问过，这一轮用户只是短确认或短片段，默认不要再追问" in prompt_text
    assert "优先总结一句、接一句，再轻轻往作息、状态或问卷方向带" in prompt_text


def test_response_composer_companion_prompt_allows_weak_turns_to_begin_gentle_pullback() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/companion_response.md": """
            {
              "assistant_message": "听起来这段时间确实有点打乱你了。要是你愿意，我们也可以慢慢从作息这部分继续往下看。"
            }
            """
        }
    )
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-02",
        current_question={"question_id": "question-02", "title": "您平时通常的作息？"},
        next_question={"question_id": "question-02", "title": "您平时通常的作息？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="好啊",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "supportive",
            "continue_chat_intent": "weak",
            "llm_provider": provider,
            "llm_available": True,
            "companion_recent_turns": [
                {
                    "raw_input": "我最近晚上总是睡不着",
                    "turn_outcome": "pullback",
                    "main_branch": "non_content",
                    "assistant_mode": "companion",
                    "assistant_topic": "sleep_stress",
                    "assistant_followup_kind": "open_followup",
                }
            ],
        },
    )

    ResponseComposerNode().run(finalized)

    prompt_text = provider.calls[0][1]

    assert "如果 `continue_chat_intent` 是 `weak`，可以视情况开始轻轻带回问卷" in prompt_text
    assert "不要把 `weak` 理解成继续同层深挖的邀请" in prompt_text
    assert "优先先承接一句，再自然点到下一题或当前要继续看的那部分" in prompt_text


def test_response_composer_companion_prompt_treats_choice_reply_as_followup_wrapup() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/companion_response.md": """
            {
              "assistant_message": "那更像是脑子停不下来这一边。我们先把这点放在这儿，后面也可以慢慢顺着看看你的作息和状态。"
            }
            """
        }
    )
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-03",
        current_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        next_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="我选第二个",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "supportive",
            "continue_chat_intent": "weak",
            "llm_provider": provider,
            "llm_available": True,
            "companion_recent_turns": [
                {
                    "raw_input": "脑子停不下来",
                    "turn_outcome": "pullback",
                    "main_branch": "non_content",
                    "assistant_mode": "companion",
                    "assistant_topic": "sleep_stress",
                    "assistant_followup_kind": "open_followup",
                }
            ],
        },
    )

    ResponseComposerNode().run(finalized)

    prompt_text = provider.calls[0][1]

    assert "如果上一轮是二选一式的轻追问，用户回“第一个”“第二个”“前者”“后者”或“我选第二个”" in prompt_text
    assert "把它理解成对上一轮追问的承接或收口补充" in prompt_text
    assert "不要继续追加同层追问，更不要再问一个新的“还是……还是……”" in prompt_text


def test_response_composer_stay_in_companion_deescalates_sleep_fragment_after_open_followup() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-03",
        current_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        next_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="工作忙的时候",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "supportive",
            "continue_chat_intent": "weak",
            "companion_recent_turns": [
                {
                    "raw_input": "我最近晚上总是睡不着",
                    "turn_outcome": "pullback",
                    "main_branch": "non_content",
                    "assistant_mode": "companion",
                    "assistant_topic": "sleep_stress",
                    "assistant_followup_kind": "open_followup",
                }
            ],
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "工作忙" in message or "压力" in message or "睡不着" in message
    assert "作息" in message or "状态" in message or "先放在这儿" in message
    assert "还是" not in message
    assert "？" not in message
    assert "?" not in message


def test_response_composer_stay_in_companion_weak_followup_can_gently_name_next_question() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-02",
        current_question={"question_id": "question-02", "title": "您平时通常的作息？"},
        next_question={"question_id": "question-02", "title": "您平时通常的作息？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="好啊",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "supportive",
            "continue_chat_intent": "weak",
            "companion_recent_turns": [
                {
                    "raw_input": "我最近晚上总是睡不着",
                    "turn_outcome": "pullback",
                    "main_branch": "non_content",
                    "assistant_mode": "companion",
                    "assistant_topic": "sleep_stress",
                    "assistant_followup_kind": "open_followup",
                }
            ],
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "作息" in message
    assert "我在这儿" not in message
    assert "想吐槽两句" not in message


def test_response_composer_explains_recent_pullback_anchor_instead_of_generic_companion_fallback() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-02",
        current_question={"question_id": "question-02", "title": "您平时通常的作息？"},
        next_question={"question_id": "question-02", "title": "您平时通常的作息？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="哪些基础信息啊",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "supportive",
            "continue_chat_intent": "weak",
            "companion_recent_turns": [
                {
                    "raw_input": "最近开始的",
                    "turn_outcome": "pullback",
                    "main_branch": "non_content",
                    "assistant_mode": "companion",
                    "assistant_topic": "sleep_stress",
                    "assistant_followup_kind": None,
                    "assistant_pullback_anchor": "您平时通常的作息？",
                }
            ],
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "作息" in message
    assert "基础信息" in message or "这一题" in message
    assert "我在这儿" not in message
    assert "慢慢说" not in message


def test_response_composer_stay_in_companion_deescalates_sleep_choice_reply_after_open_followup() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-03",
        current_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        next_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="我选第二个",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "supportive",
            "continue_chat_intent": "weak",
            "companion_recent_turns": [
                {
                    "raw_input": "脑子停不下来",
                    "turn_outcome": "pullback",
                    "main_branch": "non_content",
                    "assistant_mode": "companion",
                    "assistant_topic": "sleep_stress",
                    "assistant_followup_kind": "open_followup",
                }
            ],
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "脑子" in message or "停不下来" in message or "思绪" in message
    assert "作息" in message or "状态" in message or "先放在这儿" in message
    assert "还是" not in message
    assert "？" not in message
    assert "?" not in message


def test_response_composer_stay_in_companion_deescalates_long_sleep_followup_after_open_followup() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-03",
        current_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        next_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="就是压力大睡不着的时候，有的时候可能明天有安排",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "supportive",
            "continue_chat_intent": "weak",
            "companion_recent_turns": [
                {
                    "raw_input": "脑子停不下来",
                    "turn_outcome": "pullback",
                    "main_branch": "non_content",
                    "assistant_mode": "companion",
                    "assistant_topic": "sleep_stress",
                    "assistant_followup_kind": "open_followup",
                }
            ],
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "压力" in message or "安排" in message or "睡不着" in message
    assert "作息" in message or "状态" in message or "先放在这儿" in message
    assert "还是" not in message
    assert "？" not in message
    assert "?" not in message


def test_response_composer_stay_in_companion_deescalates_travel_fragment_after_open_followup() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-03",
        current_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        next_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="北京",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "smalltalk",
            "continue_chat_intent": "weak",
            "companion_recent_turns": [
                {
                    "raw_input": "我想去旅游，你推荐去哪",
                    "turn_outcome": "pullback",
                    "main_branch": "non_content",
                    "assistant_mode": "companion",
                    "assistant_topic": "travel",
                    "assistant_followup_kind": "open_followup",
                }
            ],
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "北京" in message
    assert "放松" in message or "节奏" in message or "先放在这儿" in message
    assert "还是" not in message
    assert "？" not in message
    assert "?" not in message


def test_response_composer_rejects_companion_llm_pullback_copy_for_strong_food_chat() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/companion_response.md": """
            {
              "assistant_message": "西红柿炒鸡蛋听起来很家常、很温暖呢。不过，我们还是先回到睡眠问卷吧，聊聊你在完全自由安排时，最自然的入睡时间是几点？"
            }
            """
        }
    )
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-03",
        current_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        next_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="今天中午吃什么，西红柿炒鸡蛋怎么样",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "smalltalk",
            "continue_chat_intent": "strong",
            "llm_provider": provider,
            "llm_available": True,
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "问卷" not in message
    assert "入睡时间" not in message
    assert message == "我在这儿，我们可以接着刚才的话题慢慢说。"


def test_response_composer_stay_in_companion_uses_topical_fallback_for_melatonin_question() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-03",
        current_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        next_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="褪黑素怎么样",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "smalltalk",
            "continue_chat_intent": "strong",
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "褪黑素" in message
    assert "问卷" not in message
    assert "入睡时间" not in message
    assert message != "我在呢，你想接着聊什么都可以。"


def test_response_composer_stay_in_companion_uses_recent_topic_for_follow_up_question() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/companion_response.md": """
            {
              "assistant_message": "褪黑素有人会拿来调整作息，不过我们还是先回到睡眠问卷吧，聊聊你最自然的入睡时间。"
            }
            """
        }
    )
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-03",
        current_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        next_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="靠不靠谱",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "smalltalk",
            "continue_chat_intent": "strong",
            "llm_provider": provider,
            "llm_available": True,
            "companion_recent_turns": [
                {
                    "raw_input": "褪黑素怎么样",
                    "turn_outcome": "pullback",
                    "main_branch": "non_content",
                }
            ],
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert message == "我在这儿，我们可以接着刚才的话题慢慢说。"
    assert "问卷" not in message
    assert "入睡时间" not in message


def test_response_composer_stay_in_companion_prefers_current_topic_over_recent_topic() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-03",
        current_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        next_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="奶茶有什么坏处吗",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "smalltalk",
            "continue_chat_intent": "strong",
            "companion_recent_turns": [
                {
                    "raw_input": "褪黑素怎么样",
                    "turn_outcome": "pullback",
                    "main_branch": "non_content",
                }
            ],
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "奶茶" in message
    assert "褪黑素" not in message
    assert "问卷" not in message


def test_response_composer_stay_in_companion_uses_sleep_stress_context_for_fragment_follow_up() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-03",
        current_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        next_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="我压力比较大的时候",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "supportive",
            "continue_chat_intent": "strong",
            "companion_recent_turns": [
                {
                    "raw_input": "我有的时候晚上会睡不着很晚才能睡着",
                    "turn_outcome": "pullback",
                    "main_branch": "non_content",
                }
            ],
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "压力" in message or "睡不着" in message or "晚上" in message
    assert message != "我在这儿，你可以慢慢说。不管是想吐槽两句，还是想换个话题聊聊，都可以。"
    assert "问卷" not in message
    assert "入睡时间" not in message


def test_response_composer_stay_in_companion_uses_recent_topic_for_contextual_assent() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-03",
        current_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        next_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="好的",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "supportive",
            "continue_chat_intent": "weak",
            "companion_recent_turns": [
                {
                    "raw_input": "我有的时候晚上会睡不着很晚才能睡着",
                    "turn_outcome": "pullback",
                    "main_branch": "non_content",
                }
            ],
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "睡不着" in message or "晚上" in message or "那种感觉" in message or "入睡时间" in message
    assert message != "我在这儿，你可以慢慢说。不管是想吐槽两句，还是想换个话题聊聊，都可以。"
    assert "问卷" not in message
    assert "先放在这儿" not in message
    assert "慢慢顺着看看" not in message
    assert "？" in message or "?" in message


def test_response_composer_stay_in_companion_weak_pullback_uses_question_style() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-03",
        current_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        next_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="好的",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "supportive",
            "continue_chat_intent": "weak",
            "companion_recent_turns": [
                {
                    "raw_input": "最近开始的",
                    "turn_outcome": "pullback",
                    "main_branch": "non_content",
                    "assistant_mode": "companion",
                    "assistant_topic": "sleep_stress",
                    "assistant_followup_kind": "open_followup",
                }
            ],
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "入睡时间" in message or "几点睡" in message or "什么时候睡" in message
    assert "先放在这儿" not in message
    assert "慢慢顺着看看" not in message
    assert "？" in message or "?" in message


def test_response_composer_stay_in_companion_uses_recent_sleep_topic_for_short_contextual_fragment() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-03",
        current_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        next_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="工作忙的时候",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "supportive",
            "continue_chat_intent": "weak",
            "companion_recent_turns": [
                {
                    "raw_input": "我最近晚上总是睡不着",
                    "turn_outcome": "pullback",
                    "main_branch": "non_content",
                }
            ],
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "工作" in message or "睡不着" in message or "晚上" in message or "压力" in message
    assert message != "我在这儿，你可以慢慢说。不管是想吐槽两句，还是想换个话题聊聊，都可以。"
    assert "问卷" not in message


def test_response_composer_stay_in_companion_uses_recent_travel_topic_for_short_place_answer() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-03",
        current_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        next_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="北京",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "smalltalk",
            "continue_chat_intent": "weak",
            "companion_recent_turns": [
                {
                    "raw_input": "我想去旅游，你推荐去哪",
                    "turn_outcome": "pullback",
                    "main_branch": "non_content",
                }
            ],
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "北京" in message
    assert "旅游" in message or "逛" in message or "地方" in message or "待几天" in message
    assert message != "我在呢，你想接着聊什么都可以。"
    assert "问卷" not in message
    assert "入睡时间" not in message


def test_response_composer_llm_available_uses_fixed_companion_backup_after_two_failures() -> None:
    class _SequencedProvider:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []
            self._responses = [
                '{"assistant_message": "已记下你的回答，我们继续聊聊旅行。"}',
                '{"assistant_message": "已记录了，我们还是先回到睡眠问卷吧。"}',
            ]

        def generate(self, prompt_key: str, prompt_text: str) -> str:
            self.calls.append((prompt_key, prompt_text))
            return self._responses.pop(0)

    provider = _SequencedProvider()
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-03",
        current_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        next_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="北京",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "smalltalk",
            "continue_chat_intent": "weak",
            "companion_recent_turns": [
                {
                    "raw_input": "我想去旅游，你推荐去哪",
                    "turn_outcome": "pullback",
                    "main_branch": "non_content",
                }
            ],
            "llm_provider": provider,
            "llm_available": True,
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert len(provider.calls) == 2
    assert message == "我在这儿，我们可以接着刚才的话题慢慢说。"


def test_response_composer_stay_in_companion_after_silent_record_uses_companion_tone() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="answered",
        updated_answer_record={"answers": [{"question_id": "question-05", "selected_options": ["E"]}]},
        updated_question_states={},
        current_question_id="question-01",
        next_question={"question_id": "question-01", "title": "您的年龄段？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="入睡比较困难",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "supportive",
            "continue_chat_intent": "weak",
            "silent_recorded_question_ids": ["question-05"],
            "companion_recent_turns": [
                {
                    "raw_input": "我最近睡眠确实不太好",
                    "turn_outcome": "pullback",
                    "main_branch": "non_content",
                }
            ],
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "已记录" not in message
    assert "已记下" not in message
    assert "接下来请回答" not in message
    assert "入睡" in message or "睡眠" in message or "困难" in message or "睡不着" in message


def test_response_composer_companion_prompt_payload_masks_silent_recording_language() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/companion_response.md": """
            {
              "assistant_message": "我在呢，你如果想聊聊最近想去哪里，我可以陪你一起想。"
            }
            """
        }
    )
    finalized = create_finalized_turn_context(
        turn_outcome="answered",
        updated_answer_record={"answers": [{"question_id": "question-01", "selected_options": ["B"]}]},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "您平时通常几点睡？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="我想明天去旅游，你推荐去哪",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "supportive",
            "silent_recorded_question_ids": ["question-01"],
            "llm_provider": provider,
            "llm_available": True,
        },
    )

    message = ResponseComposerNode().run(finalized)
    payload = _extract_payload_from_prompt(provider.calls[0][1])

    assert "已记录" not in message
    assert "已记下" not in message
    assert payload["silent_answer_event"] is True
    assert payload["must_not_acknowledge_recording"] is True
    assert payload["companion_mode"] == "supportive"


def test_response_composer_companion_prompt_payload_includes_high_risk_distress_level() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/companion_response.md": """
            {
              "assistant_message": "先别一个人扛着，尽快找个你信任的人陪着你。"
            }
            """
        }
    )
    finalized = create_finalized_turn_context(
        turn_outcome="answered",
        updated_answer_record={"answers": [{"question_id": "question-01", "selected_options": ["A"]}]},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "您平时通常几点睡？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="我18岁，我好难受我想死",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "supportive",
            "companion_distress_level": "high_risk",
            "silent_recorded_question_ids": ["question-01"],
            "llm_provider": provider,
            "llm_available": True,
        },
    )

    message = ResponseComposerNode().run(finalized)
    payload = _extract_payload_from_prompt(provider.calls[0][1])

    assert "信任的人" in message
    assert payload["companion_distress_level"] == "high_risk"


def test_response_composer_fallback_high_risk_supportive_message_encourages_real_world_support() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="answered",
        updated_answer_record={"answers": [{"question_id": "question-01", "selected_options": ["A"]}]},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "您平时通常几点睡？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="我18岁，我好难受我想死",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "supportive",
            "companion_distress_level": "high_risk",
            "silent_recorded_question_ids": ["question-01"],
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "信任的人" in message or "别一个人" in message or "陪着你" in message
    assert "已记录" not in message


def test_response_composer_return_to_quiz_uses_companion_prompt_without_record_language() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/companion_response.md": """
            {
              "assistant_message": "我们先把这件事放一放，我陪你继续往下看。接下来想请你回答您平时通常几点睡？"
            }
            """
        }
    )
    finalized = create_finalized_turn_context(
        turn_outcome="answered",
        updated_answer_record={"answers": [{"question_id": "question-01", "selected_options": ["B"]}]},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "您平时通常几点睡？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="我25到34岁",
        response_facts={
            "return_to_quiz": True,
            "companion_mode": "supportive",
            "silent_recorded_question_ids": ["question-01"],
            "llm_provider": provider,
            "llm_available": True,
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "几点睡" in message
    assert "已记录" not in message
    assert "已记下" not in message
    assert len(provider.calls) == 1
    assert provider.calls[0][0] == "layer3/companion_response.md"


def test_response_composer_soft_return_to_quiz_uses_companion_prompt_with_topic_then_question() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/companion_response.md": """
            {
              "assistant_message": "要是想放松一点，海边或者节奏慢一点的小城都会舒服些。等你想好了，我们也顺手把年龄段这题答一下，好帮我更贴近你的情况。"
            }
            """
        }
    )
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-01",
        current_question={"question_id": "question-01", "title": "您的年龄段？"},
        next_question={"question_id": "question-01", "title": "您的年龄段？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="我想找个安静点的海边待两天",
        response_facts={
            "companion_soft_return_to_quiz": True,
            "companion_mode": "supportive",
            "llm_provider": provider,
            "llm_available": True,
        },
    )

    message = ResponseComposerNode().run(finalized)
    payload = _extract_payload_from_prompt(provider.calls[0][1])

    assert "海边" in message or "小城" in message
    assert "年龄段" in message
    assert "请问您的年龄段是" not in message
    assert payload["soft_return_to_quiz"] is True
    assert payload["return_to_quiz"] is not True


def test_response_composer_fallback_soft_return_to_quiz_mentions_topic_before_question() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-01",
        current_question={"question_id": "question-01", "title": "您的年龄段？"},
        next_question={"question_id": "question-01", "title": "您的年龄段？"},
        finalized=False,
        response_language="zh-CN",
        raw_input="我想找个安静点的海边待两天",
        response_facts={
            "companion_soft_return_to_quiz": True,
            "companion_mode": "supportive",
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "海边" in message or "放松" in message or "散散心" in message
    assert "年龄段" in message
    assert "请问您的年龄段是" not in message
    assert "等你想好了" not in message
    assert "顺手把" not in message
    assert "？" in message or "?" in message


def test_response_composer_stay_in_companion_smalltalk_uses_specific_message() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="answered",
        updated_answer_record={"answers": [{"question_id": "question-01", "selected_options": ["B"]}]},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "您平时通常几点睡？"},
        finalized=False,
        response_language="zh-CN",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "smalltalk",
            "recorded_question_summaries": [{"question_id": "question-01", "title": "您的年龄段？"}],
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "我在" in message
    assert "下一题" not in message


def test_response_composer_return_to_quiz_overrides_modified_message() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="modified",
        updated_answer_record={"answers": [{"question_id": "question-01", "selected_options": ["C"]}]},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "您平时通常几点睡？"},
        finalized=False,
        response_language="zh-CN",
        response_facts={
            "return_to_quiz": True,
            "companion_mode": "supportive",
            "modified_question_summaries": [{"question_id": "question-01", "title": "您的年龄段？"}],
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "问卷" in message
    assert "几点睡" in message
    assert "已记录" not in message
    assert "已记下" not in message


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


def test_response_composer_partial_recorded_rejects_generic_llm_copy_for_missing_wake_time() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/response_composer.md": """
            {
              "assistant_message": "好的，那您平时通常的作息是怎样的呢？"
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
            "partial_followup": {"missing_fields": ["wake_time"]},
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert message == "已先记下你的入睡时间，请再告诉我你通常几点起床。"
    assert len(provider.calls) == 1


def test_response_composer_partial_recorded_accepts_llm_copy_that_targets_missing_wake_time() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/response_composer.md": """
            {
              "assistant_message": "已先记下你的入睡时间，请再告诉我你通常几点起床。"
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
            "partial_followup": {"missing_fields": ["wake_time"]},
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert message == "已先记下你的入睡时间，请再告诉我你通常几点起床。"
    assert len(provider.calls) == 1


def test_response_composer_partial_recorded_rejects_generic_llm_copy_for_missing_bedtime() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/response_composer.md": """
            {
              "assistant_message": "好的，那您平时通常的作息是怎样的呢？"
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
            "partial_followup": {"missing_fields": ["bedtime"]},
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert message == "已先记下你的起床时间，请告诉我你通常几点睡吧。"
    assert len(provider.calls) == 1

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


def test_response_composer_answered_does_not_use_companion_copy_after_companion_exit() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="answered",
        updated_answer_record={"answers": [{"question_id": "question-02", "input_value": "19:00-10:00"}]},
        updated_question_states={},
        current_question_id="question-03",
        current_question={"question_id": "question-02", "title": "您平时通常的作息？"},
        next_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        finalized=False,
        response_language="zh-CN",
        response_facts={
            "companion_mode": "supportive",
            "silent_recorded_question_ids": ["question-02"],
            "recorded_question_summaries": [
                {
                    "question_id": "question-02",
                    "title": "您平时通常的作息？",
                }
            ],
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "作息" in message
    assert "入睡时间" in message
    assert "问卷" not in message
    assert "慢慢说" not in message
    assert "继续聊" not in message


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


def test_response_composer_companion_smalltalk_overrides_pullback_message() -> None:
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
            "stay_in_companion": True,
            "companion_mode": "smalltalk",
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "我在" in message
    assert "作息" not in message


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


def test_response_composer_completion_wrapup_overrides_plain_completed_message() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="completed",
        updated_answer_record={
            "answers": [
                {"question_id": "question-01", "selected_options": ["A"]},
                {"question_id": "question-02", "input_value": "23点"},
                {"question_id": "question-03", "selected_options": ["B"]},
            ]
        },
        updated_question_states={},
        current_question_id=None,
        next_question=None,
        finalized=True,
        response_language="zh-CN",
        raw_input="需要缓冲，而且我还是有点烦",
        response_facts={
            "companion_completion_wrapup": True,
            "companion_mode": "supportive",
            "silent_recorded_question_ids": ["question-03"],
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "感谢" in message
    assert "睡眠" in message
    assert "已记录" not in message
    assert "慢慢说" not in message
    assert "继续聊" not in message


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
