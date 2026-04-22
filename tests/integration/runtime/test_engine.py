"""Integration tests for the minimal runtime engine."""

import json
from pathlib import Path

import pytest

from somni_quiz_ai.grpc.generated import somni_quiz_pb2

from somni_graph_quiz.adapters.grpc.mapper import map_questionnaire_to_catalog
from somni_graph_quiz.adapters.streamlit.mapper import map_streamlit_questionnaire_to_catalog
from somni_graph_quiz.app.bootstrap import build_llm_provider
from somni_graph_quiz.app.settings import get_settings
from somni_graph_quiz.contracts.graph_state import create_graph_state
from somni_graph_quiz.contracts.turn_input import TurnInput
from somni_graph_quiz.llm.client import FakeLLMProvider
from somni_graph_quiz.runtime.engine import GraphRuntimeEngine

OPEN_TRAVEL_CHAT = (
    "\u6211\u60f3\u53bb\u65c5\u6e38\uff0c\u4f60\u6709\u4ec0\u4e48"
    "\u63a8\u8350\u7684\u5730\u65b9\u5417"
)
CASUAL_SMALLTALK = "\u4f60\u597d\u5440"


class _SequencedProvider:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def generate(self, prompt_key: str, prompt_text: str) -> str:
        self.calls.append((prompt_key, prompt_text))
        next_item = self._responses.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return str(next_item)


class _PromptSequencedProvider:
    def __init__(self, responses: dict[str, list[object]]) -> None:
        self._responses = {key: list(items) for key, items in responses.items()}
        self.calls: list[tuple[str, str]] = []

    def generate(self, prompt_key: str, prompt_text: str) -> str:
        self.calls.append((prompt_key, prompt_text))
        queue = self._responses.get(prompt_key)
        if not queue:
            raise ValueError(f"No fake response configured for {prompt_key!r}")
        next_item = queue.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return str(next_item)


class _HybridRealProvider:
    def __init__(self, *, real_provider: object, fake_responses: dict[str, str], real_prompt_keys: set[str]) -> None:
        self._real_provider = real_provider
        self._fake_responses = dict(fake_responses)
        self._real_prompt_keys = set(real_prompt_keys)
        self.calls: list[tuple[str, str]] = []

    def generate(self, prompt_key: str, prompt_text: str) -> str:
        self.calls.append((prompt_key, prompt_text))
        if prompt_key in self._real_prompt_keys:
            return self._real_provider.generate(prompt_key, prompt_text)
        try:
            return self._fake_responses[prompt_key]
        except KeyError as exc:
            raise ValueError(f"No fake response configured for {prompt_key!r}") from exc


def _business9_question_catalog() -> dict:
    payload = json.loads(
        (Path(__file__).resolve().parents[3] / "data" / "streamlit_dynamic_questionnaire.json").read_text(
            encoding="utf-8"
        )
    )
    return map_streamlit_questionnaire_to_catalog(payload["questionnaire"])


def _configured_real_provider_or_skip() -> object:
    settings = get_settings()
    provider = build_llm_provider(settings)
    if provider is None:
        missing = ",".join(settings.missing_llm_config_keys)
        pytest.skip(f"real llm not configured: {missing}")
    return provider


@pytest.mark.xfail(
    reason="companion pullback now stays in smalltalk instead of immediately re-anchoring to the quiz",
    strict=False,
)
def test_engine_routes_non_content_turn_to_pullback_response(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-1",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-1",
        channel="grpc",
        input_mode="message",
        raw_input="谢谢你",
        language_preference="zh-CN",
    ))

    assert result["finalized"] is False
    assert result["pending_question"]["question_id"] == "question-01"
    assert "谢谢" in result["assistant_message"] or "不客气" in result["assistant_message"]
    assert "How old are you?" in result["assistant_message"]


@pytest.mark.xfail(
    reason="companion pullback now stays in smalltalk instead of immediately re-anchoring to the quiz",
    strict=False,
)
def test_engine_greeting_pullback_does_not_record_answer(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-greeting",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-greeting",
        channel="grpc",
        input_mode="message",
        raw_input="你好",
        language_preference="zh-CN",
    ))

    assert result["answer_record"]["answers"] == []
    assert result["pending_question"]["question_id"] == "question-01"
    assert "你好" in result["assistant_message"]
    assert "How old are you?" in result["assistant_message"]


def test_engine_routes_content_turn_and_updates_answer_record(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-1",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="en",
    )
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-1",
        channel="grpc",
        input_mode="message",
        raw_input="22",
        language_preference="en",
    ))

    assert result["answer_record"]["answers"] == [
        {
            "question_id": "question-01",
            "selected_options": [],
            "input_value": "22",
            "field_updates": {},
        }
    ]
    assert result["pending_question"]["question_id"] == "question-02"
    assert "what time do you usually sleep and wake?" in result["assistant_message"].lower()


def test_engine_answered_response_ignores_llm_hallucinated_copy(question_catalog: dict) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/response_composer.md": """
            {
              "assistant_message": "已记下你关于睡眠受压力影响的相关选择，接下来请回答下一题。"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="session-grounded-copy",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-grounded-copy",
        channel="grpc",
        input_mode="message",
        raw_input="22",
        language_preference="zh-CN",
    ))

    assert result["answer_record"]["answers"] == [
        {
            "question_id": "question-01",
            "selected_options": [],
            "input_value": "22",
            "field_updates": {},
        }
    ]
    assert result["pending_question"]["question_id"] == "question-02"
    assert "压力" not in result["assistant_message"]
    assert "What time do you usually sleep and wake?" in result["assistant_message"]
    assert [call[0] for call in provider.calls].count("layer3/response_composer.md") == 1


def test_engine_records_direct_answer_time_range_full(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-direct-full",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-direct-full",
        channel="grpc",
        input_mode="direct_answer",
        raw_input="23点睡，7点起",
        direct_answer_payload={
            "question_id": "question-02",
            "selected_options": [],
            "input_value": "23点睡，7点起",
        },
        language_preference="zh-CN",
    ))

    assert result["answer_record"]["answers"] == [
        {
            "question_id": "question-02",
            "selected_options": [],
            "input_value": "23:00-07:00",
            "field_updates": {"bedtime": "23:00", "wake_time": "07:00"},
        }
    ]
    assert result["pending_question"]["question_id"] == "question-03"


def test_engine_keeps_direct_answer_time_range_partial_and_asks_followup(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-direct-partial",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-direct-partial",
        channel="grpc",
        input_mode="direct_answer",
        raw_input="11点睡",
        direct_answer_payload={
            "question_id": "question-02",
            "selected_options": [],
            "input_value": "11点睡",
        },
        language_preference="zh-CN",
    ))

    assert result["answer_record"]["answers"] == []
    assert result["pending_question"]["question_id"] == "question-02"
    assert result["updated_graph_state"]["session_memory"]["pending_partial_answers"]["question-02"]["filled_fields"] == {
        "bedtime": "23:00"
    }
    assert "起床" in result["assistant_message"]


def test_engine_keeps_partial_schedule_and_asks_for_missing_field(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-1",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-1",
        channel="grpc",
        input_mode="message",
        raw_input="11点睡",
        language_preference="zh-CN",
    ))

    assert result["answer_record"]["answers"] == []
    assert result["pending_question"]["question_id"] == "question-02"
    assert result["updated_graph_state"]["session_memory"]["pending_partial_answers"]["question-02"]["filled_fields"] == {
        "bedtime": "23:00"
    }
    assert "起床" in result["assistant_message"]


def test_engine_partial_recorded_rejects_generic_llm_copy_and_reasks_missing_wake_time(
    question_catalog: dict,
) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/response_composer.md": """
            {
              "assistant_message": "好的，那您平时通常的作息是怎样的呢？"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="session-partial-generic-llm-copy",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-partial-generic-llm-copy",
        channel="grpc",
        input_mode="message",
        raw_input="十点睡",
        language_preference="zh-CN",
    ))

    assert result["answer_record"]["answers"] == []
    assert result["pending_question"]["question_id"] == "question-02"
    assert result["updated_graph_state"]["session_memory"]["pending_partial_answers"]["question-02"]["filled_fields"] == {
        "bedtime": "22:00"
    }
    assert "起床" in result["assistant_message"]
    assert "作息" not in result["assistant_message"]
    assert [call[0] for call in provider.calls].count("layer3/response_composer.md") == 1


def test_engine_keeps_wake_only_partial_schedule_and_asks_for_bedtime(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-wake-only-partial",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-wake-only-partial",
        channel="grpc",
        input_mode="message",
        raw_input="11点起",
        language_preference="zh-CN",
    ))

    assert result["answer_record"]["answers"] == []
    assert result["pending_question"]["question_id"] == "question-02"
    assert result["updated_graph_state"]["session_memory"]["pending_partial_answers"]["question-02"]["filled_fields"] == {
        "wake_time": "11:00"
    }
    assert "几点睡" in result["assistant_message"]
    assert "几点起床" not in result["assistant_message"]


def test_engine_keeps_companion_for_single_partial_unit_and_stays_in_companion_reply() -> None:
    question_catalog = {
        "question_order": ["question-01", "question-02", "question-03"],
        "question_index": {
            "question-01": {
                "question_id": "question-01",
                "title": "您的年龄段？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "18-24 岁", "aliases": []},
                    {"option_id": "B", "label": "25-34 岁", "aliases": []},
                ],
                "tags": ["基础信息"],
                "metadata": {"allow_partial": False, "structured_kind": "radio", "matching_hints": ["年龄"]},
            },
            "question-02": {
                "question_id": "question-02",
                "title": "您平时通常的作息？",
                "description": "",
                "input_type": "time_range",
                "options": [],
                "tags": ["基础信息"],
                "config": {"items": []},
                "metadata": {"allow_partial": True, "structured_kind": "time_range", "matching_hints": ["作息"]},
            },
            "question-03": {
                "question_id": "question-03",
                "title": "您对卧室环境的敏感度更接近哪种情况？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "不太敏感", "aliases": []},
                    {"option_id": "B", "label": "一般", "aliases": []},
                    {"option_id": "C", "label": "比较敏感", "aliases": []},
                ],
                "tags": ["睡眠环境"],
                "metadata": {"allow_partial": False, "structured_kind": "radio", "matching_hints": ["敏感"]},
            },
        },
    }
    graph_state = create_graph_state(
        session_id="session-companion-single-partial-exit",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["answered_records"] = {
        "question-01": {
            "question_id": "question-01",
            "selected_options": ["A"],
            "input_value": "",
            "field_updates": {},
        }
    }
    graph_state["session_memory"]["answered_question_ids"] = ["question-01"]
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03"]
    graph_state["session_memory"]["current_question_id"] = "question-03"
    graph_state["session_memory"]["unanswered_question_ids"] = ["question-02", "question-03"]
    graph_state["session_memory"]["question_states"]["question-01"]["status"] = "answered"
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "supportive",
        "entered_from_question_id": "question-03",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "distress",
    }
    graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "content",
              "non_content_intent": "none",
              "normalized_input": "11点起"
            }
            """,
            "layer2/content_understand.md": """
            {
              "content_units": [
                {
                  "unit_id": "unit-1",
                  "unit_text": "11点起",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-02"],
                  "winner_question_id": "question-02",
                  "needs_attribution": false,
                  "raw_extracted_value": "11点起",
                  "selected_options": [],
                  "input_value": "",
                  "field_updates": {"wake_time": "11:00"},
                  "missing_fields": ["bedtime"]
                }
              ],
              "clarification_needed": false,
              "clarification_reason": null
            }
            """,
            "layer1/companion_decision.md": """
            {
              "companion_action": "stay",
              "companion_mode": "supportive",
              "continue_chat_intent": "weak",
              "answer_status_override": "NOT_RECORDED",
              "reason": "keep companion tone"
            }
            """,
        }
    )
    graph_state["runtime"]["llm_available"] = True
    engine = GraphRuntimeEngine()

    result = engine.run_turn(
        graph_state,
        TurnInput(
            session_id="session-companion-single-partial-exit",
            channel="grpc",
            input_mode="message",
            raw_input="11点起",
            language_preference="zh-CN",
        ),
    )

    assert result["updated_graph_state"]["session_memory"]["companion_context"]["active"] is True
    assert result["updated_graph_state"]["session_memory"]["recent_turns"][-1]["answer_status_override"] == "NOT_RECORDED"
    assert result["pending_question"]["question_id"] == "question-02"
    assert "作息" not in result["assistant_message"]
    assert "几点睡" not in result["assistant_message"]


def test_engine_records_partial_schedule_after_answering_age_question(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-age-then-schedule-partial",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    engine = GraphRuntimeEngine()

    answered_age = engine.run_turn(graph_state, TurnInput(
        session_id="session-age-then-schedule-partial",
        channel="grpc",
        input_mode="message",
        raw_input="22",
        language_preference="zh-CN",
    ))
    result = engine.run_turn(answered_age["updated_graph_state"], TurnInput(
        session_id="session-age-then-schedule-partial",
        channel="grpc",
        input_mode="message",
        raw_input="11点起",
        language_preference="zh-CN",
    ))

    assert result["answer_record"]["answers"] == [
        {
            "question_id": "question-01",
            "selected_options": [],
            "input_value": "22",
            "field_updates": {},
        }
    ]
    assert result["pending_question"]["question_id"] == "question-02"
    assert result["updated_graph_state"]["session_memory"]["pending_partial_answers"]["question-02"]["filled_fields"] == {
        "wake_time": "11:00"
    }
    assert result["updated_graph_state"]["session_memory"]["partial_question_ids"] == ["question-02"]
    assert result["progress_percent"] > 25.0
    assert "几点睡" in result["assistant_message"]


def test_engine_records_partial_schedule_after_radio_age_answer_with_grpc_catalog() -> None:
    question_catalog = map_questionnaire_to_catalog(
        [
            somni_quiz_pb2.BusinessQuestion(
                question_id="question-01",
                title="您的年龄段？",
                input_type="radio",
                tags=["基础信息"],
                options=[
                    somni_quiz_pb2.BusinessOption(option_id="A", option_text="18-24 岁"),
                    somni_quiz_pb2.BusinessOption(option_id="B", option_text="25-34 岁"),
                ],
            ),
            somni_quiz_pb2.BusinessQuestion(
                question_id="question-02",
                title="您平时通常的作息？",
                input_type="time_range",
                tags=["基础信息"],
                config=somni_quiz_pb2.PendingQuestionConfig(
                    items=[
                        somni_quiz_pb2.PendingQuestionConfigItem(index=0, label="上床时间：", format="HH:mm"),
                        somni_quiz_pb2.PendingQuestionConfigItem(index=1, label="起床时间：", format="HH:mm"),
                    ]
                ),
            ),
        ]
    )
    graph_state = create_graph_state(
        session_id="session-radio-age-then-schedule-partial",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    engine = GraphRuntimeEngine()

    answered_age = engine.run_turn(graph_state, TurnInput(
        session_id="session-radio-age-then-schedule-partial",
        channel="grpc",
        input_mode="direct_answer",
        raw_input="A",
        direct_answer_payload={
            "question_id": "question-01",
            "selected_options": ["A"],
            "input_value": "",
        },
        language_preference="zh-CN",
    ))
    result = engine.run_turn(answered_age["updated_graph_state"], TurnInput(
        session_id="session-radio-age-then-schedule-partial",
        channel="grpc",
        input_mode="message",
        raw_input="11点起",
        language_preference="zh-CN",
    ))

    assert result["pending_question"]["question_id"] == "question-02"
    assert result["updated_graph_state"]["session_memory"]["pending_partial_answers"]["question-02"]["filled_fields"] == {
        "wake_time": "11:00"
    }
    assert result["updated_graph_state"]["session_memory"]["partial_question_ids"] == ["question-02"]
    assert "几点睡" in result["assistant_message"]


def test_engine_records_partial_schedule_from_llm_understand_payload_after_radio_age_answer() -> None:
    question_catalog = map_questionnaire_to_catalog(
        [
            somni_quiz_pb2.BusinessQuestion(
                question_id="question-01",
                title="您的年龄段？",
                input_type="radio",
                tags=["基础信息"],
                options=[
                    somni_quiz_pb2.BusinessOption(option_id="A", option_text="18-24 岁"),
                    somni_quiz_pb2.BusinessOption(option_id="B", option_text="25-34 岁"),
                ],
            ),
            somni_quiz_pb2.BusinessQuestion(
                question_id="question-02",
                title="您平时通常的作息？",
                input_type="time_range",
                tags=["基础信息"],
                config=somni_quiz_pb2.PendingQuestionConfig(
                    items=[
                        somni_quiz_pb2.PendingQuestionConfigItem(index=0, label="上床时间：", format="HH:mm"),
                        somni_quiz_pb2.PendingQuestionConfigItem(index=1, label="起床时间：", format="HH:mm"),
                    ]
                ),
            ),
        ]
    )
    graph_state = create_graph_state(
        session_id="session-radio-age-llm-partial",
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
                  "unit_text": "11点起",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-02"],
                  "winner_question_id": "question-02",
                  "needs_attribution": false,
                  "raw_extracted_value": "11点起",
                  "selected_options": [],
                  "input_value": "11点起",
                  "field_updates": {"wake_time": "11:00"},
                  "missing_fields": ["bedtime"]
                }
              ],
              "clarification_needed": false,
              "clarification_reason": null
            }
            """
        }
    )
    engine = GraphRuntimeEngine()

    answered_age = engine.run_turn(graph_state, TurnInput(
        session_id="session-radio-age-llm-partial",
        channel="grpc",
        input_mode="direct_answer",
        raw_input="A",
        direct_answer_payload={
            "question_id": "question-01",
            "selected_options": ["A"],
            "input_value": "",
        },
        language_preference="zh-CN",
    ))
    result = engine.run_turn(answered_age["updated_graph_state"], TurnInput(
        session_id="session-radio-age-llm-partial",
        channel="grpc",
        input_mode="message",
        raw_input="11点起",
        language_preference="zh-CN",
    ))

    assert result["pending_question"]["question_id"] == "question-02"
    assert result["updated_graph_state"]["session_memory"]["pending_partial_answers"]["question-02"]["filled_fields"] == {
        "wake_time": "11:00"
    }
    assert result["updated_graph_state"]["session_memory"]["partial_question_ids"] == ["question-02"]
    assert "几点睡" in result["assistant_message"]


def test_engine_normalizes_invalid_llm_modify_action_to_partial_schedule_recording() -> None:
    question_catalog = map_questionnaire_to_catalog(
        [
            somni_quiz_pb2.BusinessQuestion(
                question_id="question-01",
                title="您的年龄段？",
                input_type="radio",
                tags=["基础信息"],
                options=[
                    somni_quiz_pb2.BusinessOption(option_id="A", option_text="18-24 岁"),
                    somni_quiz_pb2.BusinessOption(option_id="B", option_text="25-34 岁"),
                ],
            ),
            somni_quiz_pb2.BusinessQuestion(
                question_id="question-02",
                title="您平时通常的作息？",
                input_type="time_range",
                tags=["基础信息"],
                config=somni_quiz_pb2.PendingQuestionConfig(
                    items=[
                        somni_quiz_pb2.PendingQuestionConfigItem(index=0, label="上床时间：", format="HH:mm"),
                        somni_quiz_pb2.PendingQuestionConfigItem(index=1, label="起床时间：", format="HH:mm"),
                    ]
                ),
            ),
        ]
    )
    graph_state = create_graph_state(
        session_id="session-radio-age-llm-invalid-action",
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
                  "unit_text": "11点起",
                  "action_mode": "modify",
                  "candidate_question_ids": ["question-02"],
                  "winner_question_id": "question-02",
                  "needs_attribution": false,
                  "raw_extracted_value": "11点起",
                  "selected_options": [],
                  "input_value": "",
                  "field_updates": {"wake_time": "11:00"},
                  "missing_fields": ["bedtime"]
                }
              ],
              "clarification_needed": false,
              "clarification_reason": null
            }
            """
        }
    )
    engine = GraphRuntimeEngine()

    answered_age = engine.run_turn(graph_state, TurnInput(
        session_id="session-radio-age-llm-invalid-action",
        channel="grpc",
        input_mode="direct_answer",
        raw_input="A",
        direct_answer_payload={
            "question_id": "question-01",
            "selected_options": ["A"],
            "input_value": "",
        },
        language_preference="zh-CN",
    ))
    result = engine.run_turn(answered_age["updated_graph_state"], TurnInput(
        session_id="session-radio-age-llm-invalid-action",
        channel="grpc",
        input_mode="message",
        raw_input="11点起",
        language_preference="zh-CN",
    ))

    assert result["pending_question"]["question_id"] == "question-02"
    assert result["updated_graph_state"]["session_memory"]["pending_partial_answers"]["question-02"]["filled_fields"] == {
        "wake_time": "11:00"
    }
    assert result["updated_graph_state"]["session_memory"]["partial_question_ids"] == ["question-02"]
    assert "几点睡" in result["assistant_message"]


def test_engine_completes_partial_schedule_on_followup(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-1",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]
    graph_state["session_memory"]["pending_partial_answers"]["question-02"] = {
        "question_id": "question-02",
        "filled_fields": {"bedtime": "23:00"},
        "missing_fields": ["wake_time"],
        "source_question_state": "partial",
    }
    graph_state["session_memory"]["partial_question_ids"] = ["question-02"]
    graph_state["session_memory"]["question_states"]["question-02"] = {
        "status": "partial",
        "attempt_count": 0,
        "last_action_mode": "answer",
    }
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-1",
        channel="grpc",
        input_mode="message",
        raw_input="7点起",
        language_preference="zh-CN",
    ))

    assert result["answer_record"]["answers"][0]["question_id"] == "question-02"
    assert result["answer_record"]["answers"][0]["input_value"] == "23:00-07:00"
    assert result["pending_question"]["question_id"] == "question-03"


def test_engine_auto_skips_partial_after_two_invalid_followups(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-1",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]
    graph_state["session_memory"]["pending_partial_answers"]["question-02"] = {
        "question_id": "question-02",
        "filled_fields": {"bedtime": "23:00"},
        "missing_fields": ["wake_time"],
        "source_question_state": "partial",
    }
    graph_state["session_memory"]["partial_question_ids"] = ["question-02"]
    graph_state["session_memory"]["question_states"]["question-02"] = {
        "status": "partial",
        "attempt_count": 0,
        "last_action_mode": "answer",
    }
    engine = GraphRuntimeEngine()

    first = engine.run_turn(graph_state, TurnInput(
        session_id="session-1",
        channel="grpc",
        input_mode="message",
        raw_input="不知道",
        language_preference="zh-CN",
    ))
    second = engine.run_turn(first["updated_graph_state"], TurnInput(
        session_id="session-1",
        channel="grpc",
        input_mode="message",
        raw_input="还是不知道",
        language_preference="zh-CN",
    ))

    assert second["updated_graph_state"]["session_memory"]["skipped_question_ids"] == ["question-02"]
    assert second["updated_graph_state"]["session_memory"]["pending_partial_answers"]["question-02"]["filled_fields"] == {
        "bedtime": "23:00"
    }
    assert second["pending_question"]["question_id"] == "question-03"


def test_engine_resumes_skipped_partial_schedule_on_later_followup(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-skip-resume",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    engine = GraphRuntimeEngine()

    first = engine.run_turn(graph_state, TurnInput(
        session_id="session-skip-resume",
        channel="grpc",
        input_mode="message",
        raw_input="11点睡",
        language_preference="zh-CN",
    ))
    skipped = engine.run_turn(first["updated_graph_state"], TurnInput(
        session_id="session-skip-resume",
        channel="grpc",
        input_mode="message",
        raw_input="跳过",
        language_preference="zh-CN",
    ))
    resumed = engine.run_turn(skipped["updated_graph_state"], TurnInput(
        session_id="session-skip-resume",
        channel="grpc",
        input_mode="message",
        raw_input="9点起",
        language_preference="zh-CN",
    ))

    answers = {item["question_id"]: item for item in resumed["answer_record"]["answers"]}
    assert answers["question-02"]["input_value"] == "23:00-09:00"
    assert resumed["updated_graph_state"]["session_memory"]["pending_partial_answers"] == {}
    assert resumed["updated_graph_state"]["session_memory"]["skipped_question_ids"] == []
    assert resumed["pending_question"]["question_id"] == "question-01"


def test_engine_keeps_skipped_partial_when_followup_input_targets_other_question(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-skip-keep",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    engine = GraphRuntimeEngine()

    first = engine.run_turn(graph_state, TurnInput(
        session_id="session-skip-keep",
        channel="grpc",
        input_mode="message",
        raw_input="11点睡",
        language_preference="zh-CN",
    ))
    skipped = engine.run_turn(first["updated_graph_state"], TurnInput(
        session_id="session-skip-keep",
        channel="grpc",
        input_mode="message",
        raw_input="跳过",
        language_preference="zh-CN",
    ))
    answered_age = engine.run_turn(skipped["updated_graph_state"], TurnInput(
        session_id="session-skip-keep",
        channel="grpc",
        input_mode="message",
        raw_input="29岁",
        language_preference="zh-CN",
    ))

    answers = {item["question_id"]: item for item in answered_age["answer_record"]["answers"]}
    assert answers["question-01"]["input_value"] == "29"
    assert "question-02" not in answers
    assert answered_age["updated_graph_state"]["session_memory"]["pending_partial_answers"]["question-02"][
        "filled_fields"
    ] == {"bedtime": "23:00"}
    assert answered_age["updated_graph_state"]["session_memory"]["skipped_question_ids"] == ["question-02"]
    assert answered_age["pending_question"]["question_id"] == "question-03"


def test_engine_free_sleep_answer_moves_forward_without_reasking_regular_schedule(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-free-sleep-followup",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["answered_records"]["question-02"] = {
        "question_id": "question-02",
        "selected_options": [],
        "input_value": "23:00-07:00",
        "field_updates": {"bedtime": "23:00", "wake_time": "07:00"},
    }
    graph_state["session_memory"]["answered_question_ids"] = ["question-02"]
    graph_state["session_memory"]["unanswered_question_ids"] = ["question-01", "question-03", "question-04"]
    graph_state["session_memory"]["question_states"]["question-02"] = {
        "status": "answered",
        "attempt_count": 0,
        "last_action_mode": "answer",
    }
    graph_state["session_memory"]["current_question_id"] = "question-03"
    graph_state["session_memory"]["pending_question_ids"] = ["question-03", "question-04"]
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-free-sleep-followup",
        channel="grpc",
        input_mode="message",
        raw_input="7点",
        language_preference="zh-CN",
    ))

    answers = {item["question_id"]: item for item in result["answer_record"]["answers"]}
    assert answers["question-03"]["selected_options"] == ["D"]
    assert result["pending_question"]["question_id"] == "question-04"
    assert "作息" not in result["assistant_message"]
    assert "wake" in result["assistant_message"].lower() or "起床" in result["assistant_message"]


def test_engine_prefers_current_free_sleep_question_over_regular_partial_after_navigate_next() -> None:
    graph_state = create_graph_state(
        session_id="session-partial-then-next-free-sleep",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=_business9_question_catalog(),
        language_preference="zh-CN",
    )
    engine = GraphRuntimeEngine()

    answered_age = engine.run_turn(graph_state, TurnInput(
        session_id="session-partial-then-next-free-sleep",
        channel="grpc",
        input_mode="message",
        raw_input="我18岁",
        language_preference="zh-CN",
    ))
    partial_schedule = engine.run_turn(answered_age["updated_graph_state"], TurnInput(
        session_id="session-partial-then-next-free-sleep",
        channel="grpc",
        input_mode="message",
        raw_input="11点起",
        language_preference="zh-CN",
    ))
    navigated = engine.run_turn(partial_schedule["updated_graph_state"], TurnInput(
        session_id="session-partial-then-next-free-sleep",
        channel="grpc",
        input_mode="message",
        raw_input="下一题",
        language_preference="zh-CN",
    ))
    result = engine.run_turn(navigated["updated_graph_state"], TurnInput(
        session_id="session-partial-then-next-free-sleep",
        channel="grpc",
        input_mode="message",
        raw_input="23点睡",
        language_preference="zh-CN",
    ))

    answers = {item["question_id"]: item for item in result["answer_record"]["answers"]}
    assert answers["question-03"]["selected_options"] == ["B"]
    assert "question-02" not in answers
    assert result["updated_graph_state"]["session_memory"]["pending_partial_answers"]["question-02"] == {
        "question_id": "question-02",
        "filled_fields": {"wake_time": "11:00"},
        "missing_fields": ["bedtime"],
        "source_question_state": "partial",
    }
    assert result["pending_question"]["question_id"] == "question-04"
    assert "作息" not in result["assistant_message"]
    assert "入睡时间" in result["assistant_message"]
    assert "起床时间" in result["assistant_message"]


def test_engine_undo_restores_previous_answer(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-1",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="en",
    )
    graph_state["session_memory"]["answered_records"]["question-01"] = {
        "question_id": "question-01",
        "selected_options": [],
        "input_value": "29",
        "field_updates": {},
    }
    graph_state["session_memory"]["previous_answer_record"] = {
        "question-01": {
            "question_id": "question-01",
            "selected_options": [],
            "input_value": "22",
            "field_updates": {},
        }
    }
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-1",
        channel="grpc",
        input_mode="message",
        raw_input="undo",
        language_preference="en",
    ))

    assert result["updated_graph_state"]["session_memory"]["answered_records"]["question-01"]["input_value"] == "22"
    assert "continue" in result["assistant_message"].lower() or "restored" in result["assistant_message"].lower()


def test_engine_view_records_keeps_current_question(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-1",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="en",
    )
    graph_state["session_memory"]["answered_records"]["question-01"] = {
        "question_id": "question-01",
        "selected_options": [],
        "input_value": "22",
        "field_updates": {},
    }
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-1",
        channel="grpc",
        input_mode="message",
        raw_input="view",
        language_preference="en",
    ))

    assert result["pending_question"]["question_id"] == graph_state["session_memory"]["current_question_id"]
    assert "summary" in result["assistant_message"].lower()


def test_engine_routes_modify_previous_control_to_last_answered_question(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-modify-prev",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["answered_records"]["question-01"] = {
        "question_id": "question-01",
        "selected_options": [],
        "input_value": "22",
        "field_updates": {},
    }
    graph_state["session_memory"]["answered_question_ids"] = ["question-01"]
    graph_state["session_memory"]["unanswered_question_ids"] = ["question-02", "question-03", "question-04"]
    graph_state["session_memory"]["question_states"]["question-01"] = {
        "status": "answered",
        "attempt_count": 0,
        "last_action_mode": "answer",
    }
    graph_state["session_memory"]["recent_turns"] = [
        {
            "turn_index": 0,
            "recorded_question_ids": ["question-01"],
            "modified_question_ids": [],
            "raw_input": "22",
        }
    ]
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-modify-prev",
        channel="grpc",
        input_mode="message",
        raw_input="改上一题",
        language_preference="zh-CN",
    ))

    assert result["pending_question"]["question_id"] == "question-01"
    assert result["updated_graph_state"]["session_memory"]["pending_modify_context"]["question_id"] == "question-01"


def test_engine_handles_same_turn_modify_and_answer(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-mixed",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["answered_records"]["question-01"] = {
        "question_id": "question-01",
        "selected_options": [],
        "input_value": "28",
        "field_updates": {},
    }
    graph_state["session_memory"]["answered_question_ids"] = ["question-01"]
    graph_state["session_memory"]["unanswered_question_ids"] = ["question-02", "question-03", "question-04"]
    graph_state["session_memory"]["question_states"]["question-01"] = {
        "status": "answered",
        "attempt_count": 0,
        "last_action_mode": "answer",
    }
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-mixed",
        channel="grpc",
        input_mode="message",
        raw_input="年龄不是28，是29；每天11点睡觉，7点起床",
        language_preference="zh-CN",
    ))

    answers = {item["question_id"]: item for item in result["answer_record"]["answers"]}
    assert answers["question-01"]["input_value"] == "29"
    assert answers["question-02"]["input_value"] == "23:00-07:00"
    assert result["updated_graph_state"]["session_memory"]["previous_answer_record"]["question-01"]["input_value"] == "28"
    assert result["pending_question"]["question_id"] == "question-03"


@pytest.mark.xfail(
    reason="identity pullback currently uses the same smalltalk companion reply style as other pullbacks",
    strict=False,
)
def test_engine_identity_pullback_keeps_current_question(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-identity-pullback",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-identity-pullback",
        channel="grpc",
        input_mode="message",
        raw_input="你是谁",
        language_preference="zh-CN",
    ))

    assert result["pending_question"]["question_id"] == "question-02"
    assert "睡眠" in result["assistant_message"]


def test_engine_view_previous_keeps_current_question_and_mentions_previous_answer(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-view-previous",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["answered_records"]["question-01"] = {
        "question_id": "question-01",
        "selected_options": ["B"],
        "input_value": "",
        "field_updates": {},
    }
    graph_state["session_memory"]["answered_question_ids"] = ["question-01"]
    graph_state["session_memory"]["recent_turns"] = [
        {
            "turn_index": 0,
            "recorded_question_ids": ["question-01"],
            "modified_question_ids": [],
            "raw_input": "B",
        }
    ]
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-view-previous",
        channel="grpc",
        input_mode="message",
        raw_input="查看上一题记录",
        language_preference="zh-CN",
    ))

    assert result["pending_question"]["question_id"] == "question-02"
    assert "上一题" in result["assistant_message"]
    assert "B" in result["assistant_message"]


@pytest.mark.xfail(
    reason="when unrelated sleep distress is recorded, the current companion flow prioritizes companion copy over quiz re-anchoring",
    strict=False,
)
def test_engine_does_not_force_unrelated_content_into_current_age_question() -> None:
    question_catalog = {
        "question_order": ["question-01", "question-05", "question-06"],
        "question_index": {
            "question-01": {
                "question_id": "question-01",
                "title": "您的年龄段？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "18-24 岁", "aliases": []},
                    {"option_id": "B", "label": "25-34 岁", "aliases": []},
                ],
                "tags": ["基础信息"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["年龄"],
                },
            },
            "question-05": {
                "question_id": "question-05",
                "title": "遇到压力或重要事情，您的睡眠会受影响吗？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "毫无影响，倒头就睡", "aliases": []},
                    {"option_id": "E", "label": "大脑停不下来，几乎睡不着", "aliases": []},
                ],
                "tags": ["人格判定"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["压力", "睡眠"],
                },
            },
            "question-06": {
                "question_id": "question-06",
                "title": "您对卧室里的光线、声音敏感度如何？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "B", "label": "轻微敏感，但影响不大", "aliases": []},
                    {"option_id": "D", "label": "一点微光或细小声音就会惊醒", "aliases": []},
                ],
                "tags": ["人格判定"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["声光", "敏感"],
                },
            },
        },
    }
    graph_state = create_graph_state(
        session_id="session-unrelated-age",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    engine = GraphRuntimeEngine()

    pressure_result = engine.run_turn(graph_state, TurnInput(
        session_id="session-unrelated-age",
        channel="grpc",
        input_mode="message",
        raw_input="大脑停不下来，几乎睡不着",
        language_preference="zh-CN",
    ))

    pressure_answers = {item["question_id"]: item for item in pressure_result["answer_record"]["answers"]}
    assert pressure_answers["question-05"]["selected_options"] == ["E"]
    assert pressure_result["pending_question"]["question_id"] == "question-01"
    assert "年龄" in pressure_result["assistant_message"]

    sensitivity_result = engine.run_turn(pressure_result["updated_graph_state"], TurnInput(
        session_id="session-unrelated-age",
        channel="grpc",
        input_mode="message",
        raw_input="对声光轻微敏感，但影响不大",
        language_preference="zh-CN",
    ))

    sensitivity_answers = {item["question_id"]: item for item in sensitivity_result["answer_record"]["answers"]}
    assert sensitivity_answers["question-06"]["selected_options"] == ["B"]
    assert sensitivity_result["pending_question"]["question_id"] == "question-01"
    assert "年龄" in sensitivity_result["assistant_message"]


def test_engine_pullback_chat_keeps_reanswer_context_for_sensitivity_question() -> None:
    question_catalog = {
        "question_order": ["question-06", "question-07"],
        "question_index": {
            "question-06": {
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
                "tags": ["人格判定"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["声光", "敏感"],
                },
            },
            "question-07": {
                "question_id": "question-07",
                "title": "最影响你睡好的问题是哪一个？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "睡前总想事或刷手机，静不下来", "aliases": []},
                ],
                "tags": ["核心锚点"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["困扰"],
                },
            },
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
        session_id="session-sensitivity-pullback",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    engine = GraphRuntimeEngine()

    pullback_result = engine.run_turn(graph_state, TurnInput(
        session_id="session-sensitivity-pullback",
        channel="grpc",
        input_mode="message",
        raw_input="你好",
        language_preference="zh-CN",
    ))

    assert pullback_result["answer_record"]["answers"] == []
    assert pullback_result["pending_question"]["question_id"] == "question-06"
    assert pullback_result["updated_graph_state"]["session_memory"]["clarification_context"] == {
        "question_id": "question-06",
        "question_title": "您对卧室里的光线、声音敏感度如何？",
        "kind": "pullback_chat",
    }

    answered_result = engine.run_turn(pullback_result["updated_graph_state"], TurnInput(
        session_id="session-sensitivity-pullback",
        channel="grpc",
        input_mode="message",
        raw_input="比较敏感",
        language_preference="zh-CN",
    ))

    answers = {item["question_id"]: item for item in answered_result["answer_record"]["answers"]}
    assert answers["question-06"]["selected_options"] == ["D"]
    assert answered_result["pending_question"]["question_id"] == "question-07"
    assert answered_result["updated_graph_state"]["session_memory"]["clarification_context"] is None


def test_engine_keeps_companion_after_silent_record_for_non_current_question() -> None:
    question_catalog = {
        "question_order": ["question-01", "question-05"],
        "question_index": {
            "question-01": {
                "question_id": "question-01",
                "title": "您的年龄段？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "18-24 岁", "aliases": []},
                    {"option_id": "B", "label": "25-34 岁", "aliases": []},
                ],
                "tags": ["基础信息"],
                "metadata": {"allow_partial": False, "structured_kind": "radio"},
            },
            "question-05": {
                "question_id": "question-05",
                "title": "最影响你睡好的问题是哪一个？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "E", "label": "入睡比较困难", "aliases": []},
                ],
                "tags": ["核心锚点"],
                "metadata": {"allow_partial": False, "structured_kind": "radio", "matching_hints": ["入睡困难"]},
            },
        },
    }
    graph_state = create_graph_state(
        session_id="session-companion-silent-record-keep",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
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
    graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "content",
              "non_content_intent": "none",
              "normalized_input": "入睡比较困难"
            }
            """,
            "layer2/content_understand.md": """
            {
              "content_units": [
                {
                  "unit_id": "unit-1",
                  "unit_text": "入睡比较困难",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-05"],
                  "winner_question_id": "question-05",
                  "needs_attribution": false,
                  "raw_extracted_value": {
                    "selected_options": ["E"],
                    "input_value": ""
                  },
                  "selected_options": ["E"],
                  "input_value": "",
                  "field_updates": {},
                  "missing_fields": []
                }
              ],
              "clarification_needed": false,
              "clarification_reason": null
            }
            """,
            "layer1/companion_decision.md": """
            {
              "companion_action": "stay",
              "companion_mode": "supportive",
              "continue_chat_intent": "weak",
              "answer_status_override": "NOT_RECORDED",
              "reason": "silent record should keep companion tone"
            }
            """,
        }
    )
    graph_state["runtime"]["llm_available"] = True
    engine = GraphRuntimeEngine()

    result = engine.run_turn(
        graph_state,
        TurnInput(
            session_id="session-companion-silent-record-keep",
            channel="grpc",
            input_mode="message",
            raw_input="入睡比较困难",
            language_preference="zh-CN",
        ),
    )

    answers = {item["question_id"]: item for item in result["answer_record"]["answers"]}
    assert answers["question-05"]["selected_options"] == ["E"]
    assert result["updated_graph_state"]["session_memory"]["companion_context"]["active"] is True
    assert "已记下" not in result["assistant_message"]
    assert "您的年龄段" not in result["assistant_message"]
    assert result["assistant_message"] == "我在这儿，我们可以接着刚才的话题慢慢说。"


def test_engine_companion_llm_retry_succeeds_for_short_travel_fragment(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-companion-llm-retry-success",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "smalltalk",
        "entered_from_question_id": "question-01",
        "rounds_since_enter": 0,
        "last_turn_continue_chat_intent": "strong",
        "last_trigger_reason": "smalltalk",
    }
    graph_state["session_memory"]["recent_turns"] = [
        {
            "raw_input": "我想去旅游，你推荐去哪",
            "main_branch": "non_content",
            "turn_outcome": "pullback",
            "assistant_mode": "companion",
            "assistant_topic": "travel",
            "assistant_followup_kind": "open_followup",
        }
    ]
    graph_state["runtime"]["llm_provider"] = _PromptSequencedProvider(
        {
            "layer1/turn_classify.md": [
                """
                {
                  "main_branch": "non_content",
                  "non_content_intent": "pullback_chat",
                  "normalized_input": "北京"
                }
                """
            ],
            "layer3/companion_response.md": [
                '{"assistant_message": "已记下你的回答，我们继续聊聊旅行。"}',
                '{"assistant_message": "北京也不错呀，你是更想逛逛胡同、吃点好吃的，还是更想找个节奏别太赶的地方慢慢待着？"}',
            ],
        }
    )
    graph_state["runtime"]["llm_available"] = True
    engine = GraphRuntimeEngine()

    result = engine.run_turn(
        graph_state,
        TurnInput(
            session_id="session-companion-llm-retry-success",
            channel="grpc",
            input_mode="message",
            raw_input="北京",
            language_preference="zh-CN",
        ),
    )

    assert "北京" in result["assistant_message"]
    assert "胡同" in result["assistant_message"] or "慢慢待着" in result["assistant_message"]
    assert result["assistant_message"] != "我在这儿，我们可以接着刚才的话题慢慢说。"


def test_engine_companion_llm_two_failures_use_fixed_backup(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-companion-llm-fixed-backup",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "smalltalk",
        "entered_from_question_id": "question-01",
        "rounds_since_enter": 0,
        "last_turn_continue_chat_intent": "strong",
        "last_trigger_reason": "smalltalk",
    }
    graph_state["session_memory"]["recent_turns"] = [
        {
            "raw_input": "我想去旅游，你推荐去哪",
            "main_branch": "non_content",
            "turn_outcome": "pullback",
            "assistant_mode": "companion",
            "assistant_topic": "travel",
            "assistant_followup_kind": "open_followup",
        }
    ]
    graph_state["runtime"]["llm_provider"] = _PromptSequencedProvider(
        {
            "layer1/turn_classify.md": [
                """
                {
                  "main_branch": "non_content",
                  "non_content_intent": "pullback_chat",
                  "normalized_input": "北京"
                }
                """
            ],
            "layer3/companion_response.md": [
                '{"assistant_message": "已记下你的回答，我们继续聊聊旅行。"}',
                '{"assistant_message": "已记录了，我们还是先回到睡眠问卷吧。"}',
            ],
        }
    )
    graph_state["runtime"]["llm_available"] = True
    engine = GraphRuntimeEngine()

    result = engine.run_turn(
        graph_state,
        TurnInput(
            session_id="session-companion-llm-fixed-backup",
            channel="grpc",
            input_mode="message",
            raw_input="北京",
            language_preference="zh-CN",
        ),
    )

    assert result["assistant_message"] == "我在这儿，我们可以接着刚才的话题慢慢说。"


def test_engine_reenters_companion_after_smalltalk_soft_return_when_user_keeps_chatting(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-companion-reenter-after-soft-return",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
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
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "smalltalk",
        "entered_from_question_id": "question-01",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "smalltalk",
    }
    engine = GraphRuntimeEngine()

    soft_return_result = engine.run_turn(
        graph_state,
        TurnInput(
            session_id="session-companion-reenter-after-soft-return",
            channel="grpc",
            input_mode="message",
            raw_input="谢谢",
            language_preference="zh-CN",
        ),
    )

    assert soft_return_result["updated_graph_state"]["session_memory"]["companion_context"]["active"] is False
    assert soft_return_result["assistant_message"] == "这段我们先轻轻放着，我陪你顺着刚才的话题再说一点，等你准备好了我们再慢慢往下看。"

    reentered_result = engine.run_turn(
        soft_return_result["updated_graph_state"],
        TurnInput(
            session_id="session-companion-reenter-after-soft-return",
            channel="grpc",
            input_mode="message",
            raw_input="我想去旅游，你有什么推荐的地方吗",
            language_preference="zh-CN",
        ),
    )

    assert reentered_result["updated_graph_state"]["session_memory"]["companion_context"]["active"] is True
    assert reentered_result["updated_graph_state"]["session_memory"]["companion_context"]["mode"] == "smalltalk"
    assert reentered_result["updated_graph_state"]["session_memory"]["companion_context"]["rounds_since_enter"] == 0
    assert "How old are you?" not in reentered_result["assistant_message"]
    assert "问卷" not in reentered_result["assistant_message"]


def test_engine_rejects_companion_llm_pullback_copy_for_strong_food_chat(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-companion-strong-food-chat",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "non_content",
              "non_content_intent": "pullback_chat",
              "normalized_input": "今天中午吃什么，西红柿炒鸡蛋怎么样"
            }
            """,
            "layer1/companion_decision.md": """
            {
              "companion_action": "stay",
              "companion_mode": "smalltalk",
              "continue_chat_intent": "strong",
              "answer_status_override": "NOT_RECORDED",
              "reason": "user is asking an open meal question"
            }
            """,
            "layer3/companion_response.md": """
            {
              "assistant_message": "西红柿炒鸡蛋听起来很家常、很温暖呢。不过，我们还是先回到睡眠问卷吧，聊聊你在完全自由安排时，最自然的入睡时间是几点？"
            }
            """,
        }
    )
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["current_question_id"] = "question-03"
    graph_state["session_memory"]["pending_question_ids"] = ["question-03", "question-04"]
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "smalltalk",
        "entered_from_question_id": "question-01",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "smalltalk",
    }
    engine = GraphRuntimeEngine()

    result = engine.run_turn(
        graph_state,
        TurnInput(
            session_id="session-companion-strong-food-chat",
            channel="grpc",
            input_mode="message",
            raw_input="今天中午吃什么，西红柿炒鸡蛋怎么样",
            language_preference="zh-CN",
        ),
    )

    assert result["updated_graph_state"]["session_memory"]["companion_context"]["active"] is True
    assert result["updated_graph_state"]["session_memory"]["companion_context"]["rounds_since_enter"] == 0
    assert "问卷" not in result["assistant_message"]
    assert "入睡时间" not in result["assistant_message"]
    assert result["assistant_message"] == "我在这儿，我们可以接着刚才的话题慢慢说。"


def test_engine_keeps_smalltalk_for_open_life_topic_when_companion_decision_marks_weak(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-companion-upgrade-weak-to-strong",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "non_content",
              "non_content_intent": "pullback_chat",
              "normalized_input": "\u6211\u60f3\u53bb\u65c5\u6e38\uff0c\u4f60\u6709\u4ec0\u4e48\u63a8\u8350\u7684\u5730\u65b9\u5417"
            }
            """,
            "layer1/companion_decision.md": """
            {
              "companion_action": "stay",
              "companion_mode": "smalltalk",
              "continue_chat_intent": "weak",
              "answer_status_override": "NOT_RECORDED",
              "reason": "user is casually chatting"
            }
            """,
        }
    )
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "smalltalk",
        "entered_from_question_id": "question-01",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "smalltalk",
    }
    engine = GraphRuntimeEngine()

    result = engine.run_turn(
        graph_state,
        TurnInput(
            session_id="session-companion-upgrade-weak-to-strong",
            channel="grpc",
            input_mode="message",
            raw_input=OPEN_TRAVEL_CHAT,
            language_preference="zh-CN",
        ),
    )

    assert result["updated_graph_state"]["session_memory"]["companion_context"]["active"] is True
    assert result["updated_graph_state"]["session_memory"]["companion_context"]["mode"] == "smalltalk"
    assert result["updated_graph_state"]["session_memory"]["companion_context"]["rounds_since_enter"] == 0
    assert "How old are you?" not in result["assistant_message"]
    assert "问卷" not in result["assistant_message"]


def test_engine_uses_recent_topic_fallback_for_short_follow_up_after_companion_llm_rejection(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-companion-follow-up-melatonin",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "non_content",
              "non_content_intent": "pullback_chat",
              "normalized_input": "靠不靠谱"
            }
            """,
            "layer1/companion_decision.md": """
            {
              "companion_action": "stay",
              "companion_mode": "smalltalk",
              "continue_chat_intent": "strong",
              "answer_status_override": "NOT_RECORDED",
              "reason": "user is asking a short follow-up about the same topic"
            }
            """,
            "layer3/companion_response.md": """
            {
              "assistant_message": "褪黑素有人会拿来调整作息，不过我们还是先回到睡眠问卷吧，聊聊你最自然的入睡时间。"
            }
            """,
        }
    )
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["current_question_id"] = "question-03"
    graph_state["session_memory"]["pending_question_ids"] = ["question-03", "question-04"]
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "smalltalk",
        "entered_from_question_id": "question-01",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "smalltalk",
    }
    graph_state["session_memory"]["recent_turns"] = [
        {
            "turn_index": 0,
            "raw_input": "褪黑素怎么样",
            "main_branch": "non_content",
            "turn_outcome": "pullback",
            "recorded_question_ids": [],
            "modified_question_ids": [],
            "partial_question_ids": [],
            "skipped_question_ids": [],
            "answer_status_override": "NOT_RECORDED",
        }
    ]
    engine = GraphRuntimeEngine()

    result = engine.run_turn(
        graph_state,
        TurnInput(
            session_id="session-companion-follow-up-melatonin",
            channel="grpc",
            input_mode="message",
            raw_input="靠不靠谱",
            language_preference="zh-CN",
        ),
    )

    assert result["updated_graph_state"]["session_memory"]["companion_context"]["active"] is True
    assert result["updated_graph_state"]["session_memory"]["companion_context"]["rounds_since_enter"] == 0
    assert result["assistant_message"] == "我在这儿，我们可以接着刚才的话题慢慢说。"
    assert "问卷" not in result["assistant_message"]
    assert "入睡时间" not in result["assistant_message"]


def test_engine_companion_selector_followup_does_not_bind_current_question() -> None:
    question_catalog = {
        "question_order": ["question-01", "question-05"],
        "question_index": {
            "question-01": {
                "question_id": "question-01",
                "title": "您的年龄段？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "18-24 岁", "aliases": []},
                    {"option_id": "B", "label": "25-34 岁", "aliases": []},
                    {"option_id": "C", "label": "35-44 岁", "aliases": []},
                ],
                "tags": ["基础信息"],
                "metadata": {"allow_partial": False, "structured_kind": "radio", "matching_hints": ["年龄"]},
            },
            "question-05": {
                "question_id": "question-05",
                "title": "遇到压力或重要事情，您的睡眠会受影响吗？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "几乎不受影响", "aliases": []},
                    {"option_id": "E", "label": "大脑停不下来，几乎睡不着", "aliases": []},
                ],
                "tags": ["sleep"],
                "metadata": {"allow_partial": False, "structured_kind": "radio", "matching_hints": ["压力", "睡眠"]},
            },
        },
    }
    graph_state = create_graph_state(
        session_id="session-companion-selector-guard-engine",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "content",
              "non_content_intent": "none",
              "normalized_input": "我选第二个"
            }
            """,
            "layer1/companion_decision.md": """
            {
              "companion_action": "stay",
              "companion_mode": "supportive",
              "continue_chat_intent": "weak",
              "answer_status_override": "NOT_RECORDED",
              "reason": "user is answering the companion follow-up, not the quiz question"
            }
            """,
        }
    )
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["current_question_id"] = "question-01"
    graph_state["session_memory"]["pending_question_ids"] = ["question-01", "question-05"]
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "supportive",
        "entered_from_question_id": "question-01",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "distress",
    }
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
    engine = GraphRuntimeEngine()

    result = engine.run_turn(
        graph_state,
        TurnInput(
            session_id="session-companion-selector-guard-engine",
            channel="grpc",
            input_mode="message",
            raw_input="我选第二个",
            language_preference="zh-CN",
        ),
    )

    answers = {item["question_id"]: item for item in result["answer_record"]["answers"]}
    assert "question-01" not in answers
    assert result["updated_graph_state"]["session_memory"]["companion_context"]["active"] is True
    assert "年龄段" not in result["assistant_message"]
    assert "已记录" not in result["assistant_message"]


@pytest.mark.llm
def test_engine_companion_selector_followup_real_llm_does_not_bind_current_question() -> None:
    real_provider = _configured_real_provider_or_skip()
    question_catalog = {
        "question_order": ["question-01", "question-05"],
        "question_index": {
            "question-01": {
                "question_id": "question-01",
                "title": "您的年龄段？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "18-24 岁", "aliases": []},
                    {"option_id": "B", "label": "25-34 岁", "aliases": []},
                    {"option_id": "C", "label": "35-44 岁", "aliases": []},
                ],
                "tags": ["基础信息"],
                "metadata": {"allow_partial": False, "structured_kind": "radio", "matching_hints": ["年龄"]},
            },
            "question-05": {
                "question_id": "question-05",
                "title": "遇到压力或重要事情，您的睡眠会受影响吗？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "几乎不受影响", "aliases": []},
                    {"option_id": "E", "label": "大脑停不下来，几乎睡不着", "aliases": []},
                ],
                "tags": ["sleep"],
                "metadata": {"allow_partial": False, "structured_kind": "radio", "matching_hints": ["压力", "睡眠"]},
            },
        },
    }
    graph_state = create_graph_state(
        session_id="session-companion-selector-guard-real-llm",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = _HybridRealProvider(
        real_provider=real_provider,
        fake_responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "content",
              "non_content_intent": "none",
              "normalized_input": "我选第二个"
            }
            """,
            "layer1/companion_decision.md": """
            {
              "companion_action": "stay",
              "companion_mode": "supportive",
              "continue_chat_intent": "weak",
              "answer_status_override": "NOT_RECORDED",
              "reason": "user is answering the companion follow-up, not the quiz question"
            }
            """,
        },
        real_prompt_keys={"layer3/companion_response.md"},
    )
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["current_question_id"] = "question-01"
    graph_state["session_memory"]["pending_question_ids"] = ["question-01", "question-05"]
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "supportive",
        "entered_from_question_id": "question-01",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "distress",
    }
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
    engine = GraphRuntimeEngine()

    result = engine.run_turn(
        graph_state,
        TurnInput(
            session_id="session-companion-selector-guard-real-llm",
            channel="grpc",
            input_mode="message",
            raw_input="我选第二个",
            language_preference="zh-CN",
        ),
    )

    answers = {item["question_id"]: item for item in result["answer_record"]["answers"]}
    assert "question-01" not in answers
    assert result["updated_graph_state"]["session_memory"]["companion_context"]["active"] is True
    assert "年龄段" not in result["assistant_message"]
    assert "已记录" not in result["assistant_message"]


def test_engine_enters_companion_from_open_life_topic_even_when_turn_classify_returns_content(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-companion-entry-from-content-open-chat",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "content",
              "non_content_intent": "none",
              "normalized_input": "\u6211\u60f3\u53bb\u65c5\u6e38\uff0c\u4f60\u6709\u4ec0\u4e48\u63a8\u8350\u7684\u5730\u65b9\u5417"
            }
            """,
            "layer1/companion_decision.md": """
            {
              "companion_action": "enter",
              "companion_mode": "smalltalk",
              "continue_chat_intent": "strong",
              "answer_status_override": "NOT_RECORDED",
              "reason": "user wants to keep chatting about travel"
            }
            """,
        }
    )
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]
    engine = GraphRuntimeEngine()

    result = engine.run_turn(
        graph_state,
        TurnInput(
            session_id="session-companion-entry-from-content-open-chat",
            channel="grpc",
            input_mode="message",
            raw_input=OPEN_TRAVEL_CHAT,
            language_preference="zh-CN",
        ),
    )

    assert result["updated_graph_state"]["session_memory"]["companion_context"]["active"] is True
    assert result["updated_graph_state"]["session_memory"]["companion_context"]["mode"] == "smalltalk"
    assert result["updated_graph_state"]["session_memory"]["companion_context"]["rounds_since_enter"] == 0
    assert "作息" not in result["assistant_message"]
    assert "入睡时间" not in result["assistant_message"]


def test_engine_enters_companion_from_casual_smalltalk_even_when_turn_classify_returns_content(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-companion-entry-from-content-casual-smalltalk",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "content",
              "non_content_intent": "none",
              "normalized_input": "\u4f60\u597d\u5440"
            }
            """,
            "layer1/companion_decision.md": """
            {
              "companion_action": "enter",
              "companion_mode": "smalltalk",
              "continue_chat_intent": "weak",
              "answer_status_override": "NOT_RECORDED",
              "reason": "user is greeting and should be handled by companion"
            }
            """,
        }
    )
    graph_state["runtime"]["llm_available"] = True
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]
    engine = GraphRuntimeEngine()

    result = engine.run_turn(
        graph_state,
        TurnInput(
            session_id="session-companion-entry-from-content-casual-smalltalk",
            channel="grpc",
            input_mode="message",
            raw_input=CASUAL_SMALLTALK,
            language_preference="zh-CN",
        ),
    )

    assert result["updated_graph_state"]["session_memory"]["companion_context"]["active"] is True
    assert result["updated_graph_state"]["session_memory"]["companion_context"]["mode"] == "smalltalk"
    assert result["updated_graph_state"]["session_memory"]["companion_context"]["rounds_since_enter"] == 0
    assert "作息" not in result["assistant_message"]
    assert "入睡时间" not in result["assistant_message"]


def test_engine_keeps_companion_active_for_answer_plus_chat_mix_on_current_question() -> None:
    question_catalog = {
        "question_order": ["question-01", "question-02", "question-03", "question-04"],
        "question_index": {
            "question-01": {
                "question_id": "question-01",
                "title": "您的年龄段？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "18-24 岁", "aliases": []},
                    {"option_id": "B", "label": "25-34 岁", "aliases": []},
                ],
                "tags": ["基础信息"],
                "metadata": {"allow_partial": False, "structured_kind": "radio", "matching_hints": ["年龄"]},
            },
            "question-02": {
                "question_id": "question-02",
                "title": "您平时通常的作息？",
                "description": "",
                "input_type": "time_range",
                "options": [],
                "tags": ["基础信息"],
                "config": {"items": []},
                "metadata": {"allow_partial": True, "structured_kind": "time_range", "matching_hints": ["作息"]},
            },
            "question-03": {
                "question_id": "question-03",
                "title": "完全自由安排时，您最自然的入睡时间是？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "22:00 前", "aliases": []},
                    {"option_id": "B", "label": "22:00-23:30", "aliases": []},
                ],
                "tags": ["基础信息"],
                "metadata": {"allow_partial": False, "structured_kind": "radio", "matching_hints": ["入睡时间"]},
            },
            "question-04": {
                "question_id": "question-04",
                "title": "完全自由安排时，您最自然的起床时间是？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "07:00 前", "aliases": []},
                    {"option_id": "B", "label": "07:00-09:00", "aliases": []},
                ],
                "tags": ["基础信息"],
                "metadata": {"allow_partial": False, "structured_kind": "radio", "matching_hints": ["起床时间"]},
            },
        },
    }
    graph_state = create_graph_state(
        session_id="session-companion-answer-plus-chat-engine",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["answered_records"] = {
        "question-01": {
            "question_id": "question-01",
            "selected_options": ["B"],
            "input_value": "",
            "field_updates": {},
        },
        "question-02": {
            "question_id": "question-02",
            "selected_options": [],
            "input_value": "19:00-10:00",
            "field_updates": {"bedtime": "19:00", "wake_time": "10:00"},
        },
    }
    graph_state["session_memory"]["answered_question_ids"] = ["question-01", "question-02"]
    graph_state["session_memory"]["pending_question_ids"] = ["question-03", "question-04"]
    graph_state["session_memory"]["current_question_id"] = "question-03"
    graph_state["session_memory"]["unanswered_question_ids"] = ["question-03", "question-04"]
    graph_state["session_memory"]["question_states"]["question-01"]["status"] = "answered"
    graph_state["session_memory"]["question_states"]["question-02"]["status"] = "answered"
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "smalltalk",
        "entered_from_question_id": "question-03",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "smalltalk",
    }
    graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "content",
              "non_content_intent": "none",
              "normalized_input": "我想去旅游，不过 22:00 前"
            }
            """,
            "layer2/content_understand.md": """
            {
              "content_units": [
                {
                  "unit_id": "unit-1",
                  "unit_text": "22:00 前",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-03"],
                  "winner_question_id": "question-03",
                  "needs_attribution": false,
                  "raw_extracted_value": {
                    "selected_options": ["A"],
                    "input_value": ""
                  },
                  "selected_options": ["A"],
                  "input_value": "",
                  "field_updates": {},
                  "missing_fields": []
                }
              ],
              "clarification_needed": false,
              "clarification_reason": null
            }
            """,
            "layer1/companion_decision.md": """
            {
              "companion_action": "stay",
              "companion_mode": "smalltalk",
              "continue_chat_intent": "strong",
              "answer_status_override": "NOT_RECORDED",
              "reason": "answer and travel chat are both present"
            }
            """,
        }
    )
    graph_state["runtime"]["llm_available"] = True
    engine = GraphRuntimeEngine()

    result = engine.run_turn(
        graph_state,
        TurnInput(
            session_id="session-companion-answer-plus-chat-engine",
            channel="grpc",
            input_mode="message",
            raw_input="我想去旅游，不过 22:00 前",
            language_preference="zh-CN",
        ),
    )

    answers = {item["question_id"]: item for item in result["answer_record"]["answers"]}
    assert answers["question-03"]["selected_options"] == ["A"]
    assert result["updated_graph_state"]["session_memory"]["companion_context"]["active"] is True
    assert result["updated_graph_state"]["session_memory"]["recent_turns"][-1]["answer_status_override"] == "NOT_RECORDED"
