"""Online smoke tests for the configured real LLM provider."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from somni_quiz_ai.grpc.generated import somni_quiz_pb2

from somni_graph_quiz.adapters.grpc.service import GrpcQuizService
from somni_graph_quiz.adapters.streamlit.mapper import map_streamlit_questionnaire_to_catalog
from somni_graph_quiz.app.real_llm_check import run_real_llm_check
from somni_graph_quiz.app.bootstrap import build_llm_provider
from somni_graph_quiz.app.settings import GraphQuizSettings
from somni_graph_quiz.contracts.finalized_turn_context import create_finalized_turn_context
from somni_graph_quiz.contracts.graph_state import create_graph_state
from somni_graph_quiz.contracts.turn_input import TurnInput
from somni_graph_quiz.nodes.layer1.turn_classify import TurnClassifyNode
from somni_graph_quiz.nodes.layer3.respond import ResponseComposerNode
from somni_graph_quiz.runtime.engine import GraphRuntimeEngine


pytestmark = pytest.mark.llm

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BUSINESS9_QUESTIONNAIRE_PATH = PROJECT_ROOT / "data" / "streamlit_dynamic_questionnaire.json"


class RecordingProvider:
    """Record prompt keys while delegating to the real provider."""

    def __init__(self, provider: Any) -> None:
        self._provider = provider
        self.calls: list[str] = []

    def generate(self, prompt_key: str, prompt_text: str) -> str:
        self.calls.append(prompt_key)
        return self._provider.generate(prompt_key, prompt_text)


def _require_settings() -> GraphQuizSettings:
    settings = GraphQuizSettings()
    if not settings.llm_ready:
        missing = ", ".join(settings.missing_llm_config_keys) or "SOMNI_LLM_*"
        pytest.skip(f"LLM configuration is not set: missing {missing}")
    return settings


def _business9_catalog() -> dict:
    payload = json.loads(BUSINESS9_QUESTIONNAIRE_PATH.read_text(encoding="utf-8"))
    return map_streamlit_questionnaire_to_catalog(payload["questionnaire"])


def _build_recording_provider() -> RecordingProvider:
    settings = _require_settings()
    provider = build_llm_provider(settings)
    assert provider is not None
    return RecordingProvider(provider)


def _build_minimal_grpc_questionnaire() -> list[somni_quiz_pb2.BusinessQuestion]:
    return [
        somni_quiz_pb2.BusinessQuestion(
            question_id="question-01",
            title="您的年龄段？",
            input_type="radio",
            tags=["基础信息"],
            options=[
                somni_quiz_pb2.BusinessOption(option_id="A", option_text="18-24 岁"),
                somni_quiz_pb2.BusinessOption(option_id="B", option_text="25-34 岁"),
                somni_quiz_pb2.BusinessOption(option_id="C", option_text="35-44 岁"),
                somni_quiz_pb2.BusinessOption(option_id="D", option_text="45-54 岁"),
                somni_quiz_pb2.BusinessOption(option_id="E", option_text="55 岁以上"),
                somni_quiz_pb2.BusinessOption(option_id="F", option_text="不愿透露"),
            ],
        ),
        somni_quiz_pb2.BusinessQuestion(
            question_id="question-02",
            title="您平时通常的作息？",
            input_type="time_range",
            tags=["基础信息"],
            config=somni_quiz_pb2.PendingQuestionConfig(
                items=[
                    somni_quiz_pb2.PendingQuestionConfigItem(index=0, label="上床时间", format="HH:mm"),
                    somni_quiz_pb2.PendingQuestionConfigItem(index=1, label="起床时间", format="HH:mm"),
                ]
            ),
        ),
    ]


def _create_business9_state(session_id: str, provider: RecordingProvider) -> dict:
    graph_state = create_graph_state(
        session_id=session_id,
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=_business9_catalog(),
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = True
    return graph_state


def _run_turn(
    engine: GraphRuntimeEngine,
    graph_state: dict,
    *,
    session_id: str,
    input_mode: str,
    raw_input: str,
    direct_answer_payload: dict | None = None,
) -> tuple[dict, dict]:
    result = engine.run_turn(
        graph_state,
        TurnInput(
            session_id=session_id,
            channel="grpc",
            input_mode=input_mode,
            raw_input=raw_input,
            direct_answer_payload=direct_answer_payload,
            language_preference="zh-CN",
        ),
    )
    return result["updated_graph_state"], result


def _apply_direct_answer(
    engine: GraphRuntimeEngine,
    graph_state: dict,
    *,
    session_id: str,
    question_id: str,
    raw_input: str,
    selected_options: list[str] | None = None,
    input_value: str | None = None,
) -> tuple[dict, dict]:
    payload = {
        "question_id": question_id,
        "selected_options": list(selected_options or []),
        "input_value": raw_input if input_value is None else input_value,
    }
    return _run_turn(
        engine,
        graph_state,
        session_id=session_id,
        input_mode="direct_answer",
        raw_input=raw_input,
        direct_answer_payload=payload,
    )


def _answer_initial_age_and_schedule(
    engine: GraphRuntimeEngine,
    graph_state: dict,
    *,
    session_id: str,
    age_text: str = "25-34 岁",
    schedule_text: str = "11点睡 7点起",
) -> dict:
    graph_state, _ = _apply_direct_answer(
        engine,
        graph_state,
        session_id=session_id,
        question_id="question-01",
        raw_input=age_text,
        input_value=age_text,
    )
    graph_state, _ = _apply_direct_answer(
        engine,
        graph_state,
        session_id=session_id,
        question_id="question-02",
        raw_input=schedule_text,
        input_value=schedule_text,
    )
    return graph_state


def test_real_llm_check_reports_business9_questionnaire_with_missing_config() -> None:
    settings = GraphQuizSettings.model_validate(
        {
            "SOMNI_LLM_BASE_URL": "",
            "SOMNI_LLM_API_KEY": "",
            "SOMNI_LLM_MODEL": "",
        }
    )

    result = run_real_llm_check(settings)

    assert result["ready"] is False
    assert result["success"] is False
    assert result["error"] == "missing_configuration"
    assert result["questionnaire"] == "business9"


def test_real_provider_smoke_turn_classify(question_catalog: dict) -> None:
    settings = _require_settings()
    provider = build_llm_provider(settings)
    assert provider is not None
    graph_state = create_graph_state(
        session_id="smoke-classify",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="smoke-classify",
            channel="grpc",
            input_mode="message",
            raw_input="下一题",
            language_preference="zh-CN",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] in {"content", "non_content"}


def test_real_provider_smoke_response_composer() -> None:
    settings = _require_settings()
    provider = build_llm_provider(settings)
    assert provider is not None
    finalized = create_finalized_turn_context(
        turn_outcome="answered",
        updated_answer_record={"answers": [{"question_id": "question-01"}]},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "您平时通常的作息？"},
        finalized=False,
        response_language="zh-CN",
        response_facts={"llm_provider": provider, "llm_available": True},
    )

    message = ResponseComposerNode().run(finalized)

    assert isinstance(message, str)
    assert message.strip()


def test_real_provider_smoke_content_answer_uses_business9_questionnaire() -> None:
    provider = _build_recording_provider()
    graph_state = _create_business9_state("smoke-content-business9", provider)

    result = GraphRuntimeEngine().run_turn(
        graph_state,
        TurnInput(
            session_id="smoke-content-business9",
            channel="grpc",
            input_mode="message",
            raw_input="我22岁，每天11点睡觉，7点起床",
            language_preference="zh-CN",
        ),
    )

    assert result["answer_record"]["answers"]
    assert result["pending_question"]["question_id"] == "question-03"
    assert "layer2/content_understand.md" in provider.calls


def test_real_provider_docx_partial_followup_business9() -> None:
    provider = _build_recording_provider()
    session_id = "smoke-docx-partial-followup"
    graph_state = _create_business9_state(session_id, provider)
    engine = GraphRuntimeEngine()

    graph_state, _ = _run_turn(
        engine,
        graph_state,
        session_id=session_id,
        input_mode="direct_answer",
        raw_input="25-34 岁",
        direct_answer_payload={
            "question_id": "question-01",
            "selected_options": [],
            "input_value": "25-34 岁",
        },
    )
    graph_state, _ = _run_turn(
        engine,
        graph_state,
        session_id=session_id,
        input_mode="message",
        raw_input="11点睡",
    )
    graph_state, result = _run_turn(
        engine,
        graph_state,
        session_id=session_id,
        input_mode="message",
        raw_input="7点起",
    )

    answers = {item["question_id"]: item for item in result["answer_record"]["answers"]}
    assert answers["question-02"]["input_value"] == "23:00-07:00"
    assert result["pending_question"]["question_id"] == "question-03"
    assert "layer2/content_understand.md" in provider.calls


def test_real_provider_docx_modify_free_wake_answered_business9() -> None:
    provider = _build_recording_provider()
    session_id = "smoke-docx-modify-free-wake"
    graph_state = _create_business9_state(session_id, provider)
    engine = GraphRuntimeEngine()

    setup_turns = [
        (
            "direct_answer",
            "25-34 岁",
            {
                "question_id": "question-01",
                "selected_options": [],
                "input_value": "25-34 岁",
            },
        ),
        (
            "direct_answer",
            "11点睡 7点起",
            {
                "question_id": "question-02",
                "selected_options": [],
                "input_value": "11点睡 7点起",
            },
        ),
        ("message", "23点", None),
        ("message", "8点半", None),
    ]
    for input_mode, raw_input, payload in setup_turns:
        graph_state, _ = _run_turn(
            engine,
            graph_state,
            session_id=session_id,
            input_mode=input_mode,
            raw_input=raw_input,
            direct_answer_payload=payload,
        )

    _, result = _run_turn(
        engine,
        graph_state,
        session_id=session_id,
        input_mode="message",
        raw_input="自由安排的话，我会七点起床",
    )

    answers = {item["question_id"]: item for item in result["answer_record"]["answers"]}
    assert answers["question-04"]["selected_options"] == ["B"]
    assert result["pending_question"]["question_id"] == "question-05"
    assert "layer2/content_understand.md" in provider.calls


def test_real_provider_docx_modify_to_ten_oclock_business9() -> None:
    provider = _build_recording_provider()
    session_id = "smoke-docx-modify-ten"
    graph_state = _create_business9_state(session_id, provider)
    engine = GraphRuntimeEngine()

    setup_turns = [
        (
            "direct_answer",
            "25-34 岁",
            {
                "question_id": "question-01",
                "selected_options": [],
                "input_value": "25-34 岁",
            },
        ),
        (
            "direct_answer",
            "11点睡 7点起",
            {
                "question_id": "question-02",
                "selected_options": [],
                "input_value": "11点睡 7点起",
            },
        ),
        ("message", "23点", None),
        ("message", "8点半", None),
    ]
    for input_mode, raw_input, payload in setup_turns:
        graph_state, _ = _run_turn(
            engine,
            graph_state,
            session_id=session_id,
            input_mode=input_mode,
            raw_input=raw_input,
            direct_answer_payload=payload,
        )

    _, result = _run_turn(
        engine,
        graph_state,
        session_id=session_id,
        input_mode="message",
        raw_input="改成十点",
    )

    answers = {item["question_id"]: item for item in result["answer_record"]["answers"]}
    assert answers["question-04"]["selected_options"] == ["D"]
    assert result["pending_question"]["question_id"] == "question-05"
    assert "layer2/content_understand.md" in provider.calls


def test_real_provider_docx_view_all_business9() -> None:
    provider = _build_recording_provider()
    session_id = "smoke-docx-view-all"
    graph_state = _create_business9_state(session_id, provider)
    engine = GraphRuntimeEngine()

    setup_turns = [
        (
            "direct_answer",
            "25-34 岁",
            {
                "question_id": "question-01",
                "selected_options": [],
                "input_value": "25-34 岁",
            },
        ),
        (
            "direct_answer",
            "11点睡 7点起",
            {
                "question_id": "question-02",
                "selected_options": [],
                "input_value": "11点睡 7点起",
            },
        ),
    ]
    for input_mode, raw_input, payload in setup_turns:
        graph_state, _ = _run_turn(
            engine,
            graph_state,
            session_id=session_id,
            input_mode=input_mode,
            raw_input=raw_input,
            direct_answer_payload=payload,
        )

    _, result = _run_turn(
        engine,
        graph_state,
        session_id=session_id,
        input_mode="message",
        raw_input="查看记录",
    )

    answers = {item["question_id"]: item for item in result["answer_record"]["answers"]}
    assert answers["question-02"]["input_value"] == "23:00-07:00"
    assert result["assistant_message"].strip()
    assert result["pending_question"]["question_id"] == "question-03"
    assert any(
        prompt_key in provider.calls
        for prompt_key in (
            "layer1/turn_classify.md",
            "layer2/non_content_detect.md",
            "layer3/response_composer.md",
        )
    )


def test_real_provider_non_content_identity_pullback_business9() -> None:
    provider = _build_recording_provider()
    session_id = "smoke-non-content-identity"
    graph_state = _create_business9_state(session_id, provider)
    engine = GraphRuntimeEngine()

    graph_state, _ = _apply_direct_answer(
        engine,
        graph_state,
        session_id=session_id,
        question_id="question-01",
        raw_input="25-34 岁",
        selected_options=["B"],
        input_value="25-34 岁",
    )
    _, result = _run_turn(
        engine,
        graph_state,
        session_id=session_id,
        input_mode="message",
        raw_input="你是谁",
    )

    answers = {item["question_id"]: item for item in result["answer_record"]["answers"]}
    assert "question-01" in answers
    assert result["pending_question"]["question_id"] == "question-02"
    assert result["assistant_message"].strip()
    assert any(
        prompt_key in provider.calls
        for prompt_key in (
            "layer1/turn_classify.md",
            "layer2/non_content_detect.md",
            "layer3/response_composer.md",
        )
    )


def test_real_provider_non_content_view_previous_business9() -> None:
    provider = _build_recording_provider()
    session_id = "smoke-non-content-view-previous"
    graph_state = _create_business9_state(session_id, provider)
    engine = GraphRuntimeEngine()

    graph_state, _ = _apply_direct_answer(
        engine,
        graph_state,
        session_id=session_id,
        question_id="question-01",
        raw_input="25-34 岁",
        selected_options=["B"],
        input_value="25-34 岁",
    )
    _, result = _run_turn(
        engine,
        graph_state,
        session_id=session_id,
        input_mode="message",
        raw_input="查看上一题记录",
    )

    answers = {item["question_id"]: item for item in result["answer_record"]["answers"]}
    assert answers["question-01"]["selected_options"] == ["B"]
    assert result["pending_question"]["question_id"] == "question-02"
    assert result["assistant_message"].strip()
    assert any(
        prompt_key in provider.calls
        for prompt_key in (
            "layer1/turn_classify.md",
            "layer2/non_content_detect.md",
            "layer3/response_composer.md",
        )
    )


def test_real_provider_docx_free_sleep_23_business9() -> None:
    provider = _build_recording_provider()
    session_id = "smoke-docx-free-sleep-23"
    graph_state = _create_business9_state(session_id, provider)
    engine = GraphRuntimeEngine()

    graph_state = _answer_initial_age_and_schedule(engine, graph_state, session_id=session_id)
    graph_state, result = _run_turn(
        engine,
        graph_state,
        session_id=session_id,
        input_mode="message",
        raw_input="23点",
    )

    answers = {item["question_id"]: item for item in result["answer_record"]["answers"]}
    assert answers["question-03"]["selected_options"] == ["B"]
    assert result["pending_question"]["question_id"] == "question-04"
    assert "layer2/content_understand.md" in provider.calls


def test_real_provider_docx_free_wake_around_7_business9() -> None:
    provider = _build_recording_provider()
    session_id = "smoke-docx-free-wake-7"
    graph_state = _create_business9_state(session_id, provider)
    engine = GraphRuntimeEngine()

    graph_state = _answer_initial_age_and_schedule(engine, graph_state, session_id=session_id)
    graph_state, _ = _apply_direct_answer(
        engine,
        graph_state,
        session_id=session_id,
        question_id="question-03",
        raw_input="22:00-23:15",
        selected_options=["B"],
        input_value="22:00-23:15",
    )
    graph_state, result = _run_turn(
        engine,
        graph_state,
        session_id=session_id,
        input_mode="message",
        raw_input="那7左右",
    )

    answers = {item["question_id"]: item for item in result["answer_record"]["answers"]}
    assert answers["question-04"]["selected_options"] == ["B"]
    assert result["pending_question"]["question_id"] == "question-05"
    assert "layer2/content_understand.md" in provider.calls


def test_real_provider_docx_wake_back_ten_minutes_business9() -> None:
    provider = _build_recording_provider()
    session_id = "smoke-docx-wake-back-ten"
    graph_state = _create_business9_state(session_id, provider)
    engine = GraphRuntimeEngine()

    graph_state = _answer_initial_age_and_schedule(engine, graph_state, session_id=session_id)
    for question_id, raw_input, option_id, input_value in (
        ("question-03", "22:00-23:15", "B", "22:00-23:15"),
        ("question-04", "06:00-07:45", "B", "06:00-07:45"),
        ("question-05", "毫无影响，倒头就睡", "A", "毫无影响，倒头就睡"),
        ("question-06", "完全不敏感，在哪都能睡", "A", "完全不敏感，在哪都能睡"),
        ("question-07", "睡前总想事或刷手机，静不下来", "A", "睡前总想事或刷手机，静不下来"),
    ):
        graph_state, _ = _apply_direct_answer(
            engine,
            graph_state,
            session_id=session_id,
            question_id=question_id,
            raw_input=raw_input,
            selected_options=[option_id],
            input_value=input_value,
        )
    graph_state, result = _run_turn(
        engine,
        graph_state,
        session_id=session_id,
        input_mode="message",
        raw_input="十来分钟",
    )

    answers = {item["question_id"]: item for item in result["answer_record"]["answers"]}
    assert answers["question-08"]["selected_options"] == ["A"]
    assert result["pending_question"]["question_id"] == "question-09"
    assert "layer2/content_understand.md" in provider.calls


def test_real_provider_answer_plus_unhappy_tail_is_silently_recorded_in_companion_mode() -> None:
    provider = _build_recording_provider()
    service = GrpcQuizService()
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="smoke-real-llm-answer-plus-unhappy-tail",
            language="zh-CN",
            questionnaire=_build_minimal_grpc_questionnaire(),
            quiz_mode="dynamic",
        ),
        context=None,
    )
    snapshot = service._sessions["smoke-real-llm-answer-plus-unhappy-tail"]
    snapshot.graph_state["runtime"]["llm_provider"] = provider
    snapshot.graph_state["runtime"]["llm_available"] = True

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="smoke-real-llm-answer-plus-unhappy-tail",
            message="18岁，但是今天我很不开心",
        ),
        context=None,
    )

    assert response.success is True
    assert response.answer_status_code == "NOT_RECORDED"
    assert response.pending_question.question_id == "question-02"
    assert response.assistant_message.strip()
    assert "已记录" not in response.assistant_message
    assert "recorded" not in response.assistant_message.lower()
    assert "updated" not in response.assistant_message.lower()
    assert "noted" not in response.assistant_message.lower()
    assert "layer2/content_understand.md" in provider.calls

    answered_record = snapshot.graph_state["session_memory"]["answered_records"]["question-01"]
    assert answered_record["selected_options"] == ["A"]
    assert snapshot.graph_state["session_memory"]["current_question_id"] == "question-02"


def test_real_provider_answer_plus_high_risk_tail_is_silently_recorded_in_companion_mode() -> None:
    provider = _build_recording_provider()
    service = GrpcQuizService()
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="smoke-real-llm-answer-plus-high-risk-tail",
            language="zh-CN",
            questionnaire=_build_minimal_grpc_questionnaire(),
            quiz_mode="dynamic",
        ),
        context=None,
    )
    snapshot = service._sessions["smoke-real-llm-answer-plus-high-risk-tail"]
    snapshot.graph_state["runtime"]["llm_provider"] = provider
    snapshot.graph_state["runtime"]["llm_available"] = True

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="smoke-real-llm-answer-plus-high-risk-tail",
            message="我18岁，我好难受我想死",
        ),
        context=None,
    )

    assert response.success is True
    assert response.answer_status_code == "NOT_RECORDED"
    assert response.pending_question.question_id == "question-02"
    assert response.assistant_message.strip()
    assert "已记录" not in response.assistant_message
    assert "recorded" not in response.assistant_message.lower()
    assert "updated" not in response.assistant_message.lower()
    assert "noted" not in response.assistant_message.lower()
    assert "layer2/content_understand.md" in provider.calls
    assert "layer1/companion_decision.md" in provider.calls
    assert "layer3/companion_response.md" in provider.calls

    answered_record = snapshot.graph_state["session_memory"]["answered_records"]["question-01"]
    assert answered_record["selected_options"] == ["A"]
    assert snapshot.graph_state["session_memory"]["current_question_id"] == "question-02"


def test_real_provider_companion_decision_prompt_is_used_for_topic_chat() -> None:
    provider = _build_recording_provider()
    service = GrpcQuizService()
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="smoke-real-llm-topic-chat",
            language="zh-CN",
            questionnaire=_build_minimal_grpc_questionnaire(),
            quiz_mode="dynamic",
        ),
        context=None,
    )
    snapshot = service._sessions["smoke-real-llm-topic-chat"]
    snapshot.graph_state["runtime"]["llm_provider"] = provider
    snapshot.graph_state["runtime"]["llm_available"] = True

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="smoke-real-llm-topic-chat",
            message="我想去旅游，你有什么建议吗",
        ),
        context=None,
    )

    assert response.success is True
    assert response.answer_status_code == "NOT_RECORDED"
    assert response.assistant_message.strip()
    assert "layer1/companion_decision.md" in provider.calls
