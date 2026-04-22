"""Diagnostics tests for companion response composition."""

from __future__ import annotations

import json
import logging

from somni_graph_quiz.contracts.finalized_turn_context import create_finalized_turn_context
from somni_graph_quiz.nodes.layer3.respond import ResponseComposerNode


def _parse_diagnostic_messages(caplog) -> list[dict]:
    records: list[dict] = []
    for record in caplog.records:
        if record.name != "somni_graph_quiz.diagnostics.companion_response":
            continue
        records.append(json.loads(record.getMessage()))
    return records


class _RaisingProvider:
    def generate(self, prompt_key: str, prompt_text: str) -> str:
        del prompt_key
        del prompt_text
        raise TimeoutError("companion llm timed out")


class _StaticProvider:
    def __init__(self, response_text: str) -> None:
        self._response_text = response_text

    def generate(self, prompt_key: str, prompt_text: str) -> str:
        del prompt_key
        del prompt_text
        return self._response_text


class _SequencedProvider:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def generate(self, prompt_key: str, prompt_text: str) -> str:
        self.calls.append((prompt_key, prompt_text))
        if not self._responses:
            raise AssertionError("No sequenced response left")
        next_item = self._responses.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return str(next_item)


def _companion_finalized(*, raw_input: str, response_facts: dict) -> object:
    return create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-03",
        current_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        next_question={"question_id": "question-03", "title": "完全自由安排时，您最自然的入睡时间是？"},
        finalized=False,
        response_language="zh-CN",
        raw_input=raw_input,
        response_facts=response_facts,
    )


def test_response_composer_logs_companion_llm_not_attempted_when_unavailable(caplog) -> None:
    finalized = _companion_finalized(
        raw_input="褪黑素怎么样",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "smalltalk",
            "continue_chat_intent": "strong",
            "llm_available": False,
        },
    )

    with caplog.at_level(logging.WARNING, logger="somni_graph_quiz.diagnostics.companion_response"):
        ResponseComposerNode().run(finalized)

    diagnostics = _parse_diagnostic_messages(caplog)

    assert diagnostics[0]["event"] == "llm_not_attempted"
    assert diagnostics[0]["reason"] == "llm_unavailable"


def test_response_composer_logs_companion_llm_exception(caplog) -> None:
    finalized = _companion_finalized(
        raw_input="褪黑素怎么样",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "smalltalk",
            "continue_chat_intent": "strong",
            "llm_provider": _RaisingProvider(),
            "llm_available": True,
        },
    )

    with caplog.at_level(logging.WARNING, logger="somni_graph_quiz.diagnostics.companion_response"):
        ResponseComposerNode().run(finalized)

    diagnostics = _parse_diagnostic_messages(caplog)
    events = [entry["event"] for entry in diagnostics]

    assert "llm_attempt_started" in events
    assert "llm_exception" in events
    exception_entry = next(entry for entry in diagnostics if entry["event"] == "llm_exception")
    assert exception_entry["error_type"] == "TimeoutError"


def test_response_composer_logs_companion_llm_empty_message(caplog) -> None:
    finalized = _companion_finalized(
        raw_input="褪黑素怎么样",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "smalltalk",
            "continue_chat_intent": "strong",
            "llm_provider": _StaticProvider('{"assistant_message": ""}'),
            "llm_available": True,
        },
    )

    with caplog.at_level(logging.WARNING, logger="somni_graph_quiz.diagnostics.companion_response"):
        ResponseComposerNode().run(finalized)

    diagnostics = _parse_diagnostic_messages(caplog)
    events = [entry["event"] for entry in diagnostics]

    assert "llm_result_received" in events
    assert "llm_empty_message" in events


def test_response_composer_logs_companion_llm_rejected_recording_ack(caplog) -> None:
    finalized = _companion_finalized(
        raw_input="褪黑素怎么样",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "smalltalk",
            "continue_chat_intent": "strong",
            "llm_provider": _StaticProvider('{"assistant_message": "已记下你的回答，我们继续聊聊褪黑素。"}'),
            "llm_available": True,
        },
    )

    with caplog.at_level(logging.WARNING, logger="somni_graph_quiz.diagnostics.companion_response"):
        ResponseComposerNode().run(finalized)

    diagnostics = _parse_diagnostic_messages(caplog)
    events = [entry["event"] for entry in diagnostics]

    assert "llm_rejected_recording_ack" in events


def test_response_composer_logs_companion_llm_rejected_pullback_copy(caplog) -> None:
    finalized = _companion_finalized(
        raw_input="褪黑素怎么样",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "smalltalk",
            "continue_chat_intent": "strong",
            "llm_provider": _StaticProvider(
                '{"assistant_message": "褪黑素有人会拿来调整入睡节奏，不过我们还是先回到睡眠问卷吧，聊聊你最自然的入睡时间。"}'
            ),
            "llm_available": True,
        },
    )

    with caplog.at_level(logging.WARNING, logger="somni_graph_quiz.diagnostics.companion_response"):
        ResponseComposerNode().run(finalized)

    diagnostics = _parse_diagnostic_messages(caplog)
    events = [entry["event"] for entry in diagnostics]

    assert "llm_rejected_pullback_copy" in events


def test_response_composer_retries_companion_llm_once_before_using_fallback(caplog) -> None:
    provider = _SequencedProvider(
        [
            '{"assistant_message": "已记下你的回答，我们继续聊聊旅行。"}',
            '{"assistant_message": "北京也不错呀，你是更想逛逛城里，还是更想找个舒服点的地方慢慢待着？"}',
        ]
    )
    finalized = _companion_finalized(
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

    with caplog.at_level(logging.WARNING, logger="somni_graph_quiz.diagnostics.companion_response"):
        message = ResponseComposerNode().run(finalized)

    diagnostics = _parse_diagnostic_messages(caplog)
    events = [entry["event"] for entry in diagnostics]

    assert message.startswith("北京也不错呀")
    assert len(provider.calls) == 2
    assert "llm_rejected_recording_ack" in events
    assert events.count("llm_attempt_started") == 2


def test_response_composer_uses_fixed_companion_backup_after_two_llm_failures(caplog) -> None:
    provider = _SequencedProvider(
        [
            '{"assistant_message": "已记下你的回答，我们继续聊聊旅行。"}',
            '{"assistant_message": "已记录了，我们还是先回到睡眠问卷吧。"}',
        ]
    )
    finalized = _companion_finalized(
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

    with caplog.at_level(logging.WARNING, logger="somni_graph_quiz.diagnostics.companion_response"):
        message = ResponseComposerNode().run(finalized)

    diagnostics = _parse_diagnostic_messages(caplog)
    events = [entry["event"] for entry in diagnostics]

    assert len(provider.calls) == 2
    assert message == "我在这儿，我们可以接着刚才的话题慢慢说。"
    assert "llm_rejected_recording_ack" in events
    assert events.count("llm_rejected_recording_ack") == 2
