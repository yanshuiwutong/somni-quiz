"""Integration tests for the gRPC adapter."""

import grpc

from somni_quiz_ai.grpc.generated import somni_quiz_pb2

from somni_graph_quiz.adapters.grpc.service import GrpcQuizService, SessionSnapshot
from somni_graph_quiz.contracts.graph_state import create_graph_state
from somni_graph_quiz.llm.client import FakeLLMProvider


def _build_questionnaire() -> list:
    return [
        somni_quiz_pb2.BusinessQuestion(
            question_id="question-01",
            title="How old are you?",
            input_type="text",
        ),
        somni_quiz_pb2.BusinessQuestion(
            question_id="question-02",
            title="What time do you usually sleep and wake?",
            input_type="time_range",
            config=somni_quiz_pb2.PendingQuestionConfig(
                items=[
                    somni_quiz_pb2.PendingQuestionConfigItem(index=0, label="上床时间：", format="HH:mm"),
                    somni_quiz_pb2.PendingQuestionConfigItem(index=1, label="起床时间：", format="HH:mm"),
                ]
            ),
        ),
    ]


def test_init_quiz_returns_pending_question_and_shape() -> None:
    service = GrpcQuizService()
    request = somni_quiz_pb2.InitQuizRequest(
        session_id="session-1",
        language="en",
        questionnaire=_build_questionnaire(),
        quiz_mode="dynamic",
    )

    response = service.InitQuiz(request, context=None)

    assert response.success is True
    assert response.initialized is True
    assert response.pending_question.question_id == "question-01"
    assert response.quiz_mode == "dynamic"
    assert response.progress_percent == 0.0


def test_init_quiz_stores_default_city_in_session_snapshot() -> None:
    service = GrpcQuizService()
    request = somni_quiz_pb2.InitQuizRequest(
        session_id="session-default-city",
        language="zh-CN",
        questionnaire=_build_questionnaire(),
        quiz_mode="dynamic",
        default_city="上海",
    )

    response = service.InitQuiz(request, context=None)

    assert response.success is True
    assert service._sessions["session-default-city"].graph_state["session"]["default_city"] == "上海"


def test_init_quiz_with_existing_session_restores_current_snapshot() -> None:
    service = GrpcQuizService()
    questionnaire = _build_questionnaire()
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="session-restore-existing",
            language="en",
            questionnaire=questionnaire,
            quiz_mode="dynamic",
        ),
        context=None,
    )
    answered = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-restore-existing",
            direct_answer=somni_quiz_pb2.DirectAnswer(
                question_id="question-01",
                input_value="29",
            ),
        ),
        context=None,
    )

    restored = service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="session-restore-existing",
            language="zh-CN",
            questionnaire=questionnaire,
            quiz_mode="fixed",
            default_city="上海",
        ),
        context=None,
    )

    assert answered.success is True
    assert answered.pending_question.question_id == "question-02"
    assert restored.success is True
    assert restored.pending_question.question_id == "question-02"
    assert restored.answer_record.answers[0].question_id == "question-01"
    assert restored.answer_record.answers[0].direct_answer.input_value == "29"
    assert restored.progress_percent == 50.0
    assert restored.quiz_mode == "dynamic"
    assert service._sessions["session-restore-existing"].graph_state["session"]["default_city"] == ""


def test_chat_quiz_message_updates_answer_record() -> None:
    service = GrpcQuizService()
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="session-1",
            language="en",
            questionnaire=_build_questionnaire(),
            quiz_mode="dynamic",
        ),
        context=None,
    )

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-1",
            message="22",
        ),
        context=None,
    )

    assert response.success is True
    assert response.answer_record.answers[0].question_id == "question-01"
    assert response.answer_status_code == "RECORDED"
    assert response.pending_question.question_id == "question-02"
    assert response.pending_question.config.items[0].label == "上床时间："
    assert response.pending_question.config.items[1].format == "HH:mm"
    assert response.progress_percent == 50.0


def test_chat_quiz_reports_partial_after_age_then_schedule_wake_fragment() -> None:
    service = GrpcQuizService()
    questionnaire = [
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
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="session-age-then-partial",
            language="zh-CN",
            questionnaire=questionnaire,
            quiz_mode="dynamic",
        ),
        context=None,
    )
    first = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-age-then-partial",
            direct_answer=somni_quiz_pb2.DirectAnswer(
                question_id="question-01",
                selected_options=["A"],
            ),
        ),
        context=None,
    )

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-age-then-partial",
            message="11点起",
        ),
        context=None,
    )
    recent_turn = service._sessions["session-age-then-partial"].graph_state["session_memory"]["recent_turns"][-1]
    session_memory = service._sessions["session-age-then-partial"].graph_state["session_memory"]

    assert first.answer_status_code == "RECORDED"
    assert response.success is True
    assert session_memory["pending_partial_answers"]["question-02"]["filled_fields"] == {
        "wake_time": "11:00"
    }
    assert session_memory["partial_question_ids"] == ["question-02"]
    assert recent_turn["partial_question_ids"] == ["question-02"]
    assert response.answer_status_code == "PARTIAL"
    assert response.pending_question.question_id == "question-02"
    assert len(response.answer_record.answers) == 1
    assert response.answer_record.answers[0].question_id == "question-01"
    assert response.progress_percent > 50.0
    assert any(token in response.assistant_message for token in ("入睡", "几点睡", "作息"))


def test_chat_quiz_direct_answer_routes_to_runtime() -> None:
    service = GrpcQuizService()
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="session-2",
            language="zh-CN",
            questionnaire=_build_questionnaire(),
            quiz_mode="dynamic",
        ),
        context=None,
    )

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-2",
            direct_answer=somni_quiz_pb2.DirectAnswer(
                question_id="question-01",
                input_value="29",
            ),
        ),
        context=None,
    )

    assert response.success is True
    assert response.answer_record.answers[0].question_id == "question-01"
    assert response.answer_status_code == "RECORDED"
    assert response.assistant_message


def test_chat_quiz_missing_session_returns_failed_precondition() -> None:
    service = GrpcQuizService()

    class _Context:
        def __init__(self) -> None:
            self.code = None
            self.details = None

        def set_code(self, code) -> None:
            self.code = code

        def set_details(self, details: str) -> None:
            self.details = details

    context = _Context()

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="missing-session",
            message="22",
        ),
        context=context,
    )

    assert response.success is False
    assert response.session_id == "missing-session"
    assert response.assistant_message == "Session not initialized. Call InitQuiz first."
    assert response.answer_status_code == "NOT_RECORDED"
    assert context.code == grpc.StatusCode.FAILED_PRECONDITION
    assert context.details == "Session not initialized. Call InitQuiz first."


def test_chat_quiz_direct_answer_followup_keeps_status_for_out_of_order_answers() -> None:
    service = GrpcQuizService()
    questionnaire = [
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
        somni_quiz_pb2.BusinessQuestion(
            question_id="question-09",
            title="早上醒来后，多久能彻底清醒？",
            input_type="radio",
            tags=["核心锚点"],
            options=[
                somni_quiz_pb2.BusinessOption(option_id="A", option_text="几乎立刻清醒，满血复活"),
                somni_quiz_pb2.BusinessOption(option_id="B", option_text="需要洗漱或咖啡缓冲"),
                somni_quiz_pb2.BusinessOption(option_id="C", option_text="1-2 小时都不太清醒，身体沉重"),
            ],
        ),
    ]
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="session-out-of-order",
            language="zh-CN",
            questionnaire=questionnaire,
            quiz_mode="dynamic",
        ),
        context=None,
    )

    first = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-out-of-order",
            direct_answer=somni_quiz_pb2.DirectAnswer(
                question_id="question-09",
                selected_options=["C"],
            ),
        ),
        context=None,
    )
    second = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-out-of-order",
            direct_answer=somni_quiz_pb2.DirectAnswer(
                question_id="question-01",
                selected_options=["A"],
            ),
        ),
        context=None,
    )

    assert first.success is True
    assert first.answer_status_code == "RECORDED"
    assert second.success is True
    assert second.answer_status_code == "RECORDED"
    assert second.pending_question.question_id == "question-02"


def test_chat_quiz_reports_not_recorded_when_turn_metadata_is_missing(monkeypatch) -> None:
    service = GrpcQuizService()
    service._sessions["session-missing-turn-metadata"] = SessionSnapshot(
        graph_state={"session_memory": {"recent_turns": []}},
        quiz_mode="dynamic",
        language="zh-CN",
    )

    monkeypatch.setattr(
        service._engine,
        "run_turn",
        lambda graph_state, turn_input: {
            "updated_graph_state": {
                "session_memory": {
                    "recent_turns": [{}],
                }
            },
            "assistant_message": "好的，我记下了你的年龄。",
            "pending_question": {
                "question_id": "question-02",
                "title": "您平时通常的作息？",
                "input_type": "time_range",
                "tags": ["基础信息"],
                "options": [],
                "config": {
                    "items": [
                        {"index": 0, "label": "上床时间：", "format": "HH:mm"},
                        {"index": 1, "label": "起床时间：", "format": "HH:mm"},
                    ]
                },
            },
            "finalized": False,
            "answer_record": {
                "answers": [
                    {
                        "question_id": "question-01",
                        "selected_options": ["A"],
                        "input_value": "",
                        "field_updates": {},
                    }
                ]
            },
            "final_result": None,
        },
    )

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-missing-turn-metadata",
            direct_answer=somni_quiz_pb2.DirectAnswer(
                question_id="question-01",
                selected_options=["A"],
            ),
        ),
        context=None,
    )

    assert response.success is True
    assert response.answer_status_code == "NOT_RECORDED"


def test_chat_quiz_applies_answer_status_override_from_turn_metadata(monkeypatch) -> None:
    service = GrpcQuizService()
    service._sessions["session-answer-status-override"] = SessionSnapshot(
        graph_state={"session_memory": {"recent_turns": []}},
        quiz_mode="dynamic",
        language="zh-CN",
    )

    monkeypatch.setattr(
        service._engine,
        "run_turn",
        lambda graph_state, turn_input: {
            "updated_graph_state": {
                "session_memory": {
                    "recent_turns": [
                        {
                            "turn_index": 0,
                            "raw_input": "好，继续",
                            "turn_outcome": "answered",
                            "recorded_question_ids": ["question-01"],
                            "metadata": {
                                "answer_status_override": "NOT_RECORDED",
                            },
                        }
                    ],
                }
            },
            "assistant_message": "我来继续引导你。",
            "pending_question": {
                "question_id": "question-02",
                "title": "您平时通常的作息？",
                "input_type": "time_range",
                "tags": ["基础信息"],
                "options": [],
                "config": {
                    "items": [
                        {"index": 0, "label": "上床时间：", "format": "HH:mm"},
                        {"index": 1, "label": "起床时间：", "format": "HH:mm"},
                    ]
                },
            },
            "finalized": False,
            "answer_record": {
                "answers": [
                    {
                        "question_id": "question-01",
                        "selected_options": ["A"],
                        "input_value": "",
                        "field_updates": {},
                    }
                ]
            },
            "final_result": None,
            "progress_percent": 50.0,
        },
    )

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-answer-status-override",
            message="好，继续",
        ),
        context=None,
    )

    assert response.success is True
    assert response.answer_status_code == "NOT_RECORDED"
    assert len(response.answer_record.answers) == 1
    assert response.answer_record.answers[0].question_id == "question-01"
    assert response.pending_question.question_id == "question-02"
    assert response.progress_percent == 50.0


def test_chat_quiz_completed_turn_without_override_reports_recorded(monkeypatch) -> None:
    service = GrpcQuizService()
    service._sessions["session-completed-recorded"] = SessionSnapshot(
        graph_state={"session_memory": {"recent_turns": []}},
        quiz_mode="dynamic",
        language="zh-CN",
    )

    monkeypatch.setattr(
        service._engine,
        "run_turn",
        lambda graph_state, turn_input: {
            "updated_graph_state": {
                "session_memory": {
                    "recent_turns": [
                        {
                            "turn_index": 0,
                            "raw_input": "需要缓冲，而且我还是有点烦",
                            "turn_outcome": "completed",
                            "recorded_question_ids": ["question-03"],
                            "modified_question_ids": [],
                            "partial_question_ids": [],
                            "skipped_question_ids": [],
                            "answer_status_override": None,
                        }
                    ],
                }
            },
            "assistant_message": "这一路辛苦了，感谢你的分享。我已经大致了解了你的睡眠习惯。",
            "pending_question": None,
            "finalized": True,
            "answer_record": {
                "answers": [
                    {
                        "question_id": "question-01",
                        "selected_options": ["A"],
                        "input_value": "",
                        "field_updates": {},
                    },
                    {
                        "question_id": "question-02",
                        "selected_options": [],
                        "input_value": "23点",
                        "field_updates": {},
                    },
                    {
                        "question_id": "question-03",
                        "selected_options": ["B"],
                        "input_value": "",
                        "field_updates": {},
                    },
                ]
            },
            "final_result": {
                "completion_message": "这一路辛苦了，感谢你的分享。我已经大致了解了你的睡眠习惯。",
                "finalized": True,
            },
            "progress_percent": 100.0,
        },
    )

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-completed-recorded",
            message="需要缓冲，而且我还是有点烦",
        ),
        context=None,
    )

    assert response.success is True
    assert response.finalized is True
    assert response.answer_status_code == "RECORDED"


def test_chat_quiz_greeting_does_not_report_recorded_with_existing_history() -> None:
    service = GrpcQuizService()
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="session-greeting-status",
            language="zh-CN",
            questionnaire=_build_questionnaire(),
            quiz_mode="dynamic",
        ),
        context=None,
    )
    first = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-greeting-status",
            message="22",
        ),
        context=None,
    )

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-greeting-status",
            message="你好",
        ),
        context=None,
    )

    assert first.answer_status_code == "RECORDED"
    assert response.success is True
    assert len(response.answer_record.answers) == 1
    assert response.answer_status_code == "NOT_RECORDED"


def test_chat_quiz_answering_current_question_in_companion_returns_recorded_status() -> None:
    service = GrpcQuizService()
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="session-companion-return-wording",
            language="zh-CN",
            questionnaire=_build_questionnaire(),
            quiz_mode="dynamic",
        ),
        context=None,
    )

    greeting = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-companion-return-wording",
            message="你好",
        ),
        context=None,
    )
    service._sessions["session-companion-return-wording"].graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "smalltalk",
        "entered_from_question_id": "question-01",
        "rounds_since_enter": 0,
        "last_turn_continue_chat_intent": None,
        "last_trigger_reason": "test_seed",
    }
    service._sessions["session-companion-return-wording"].graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
        responses={
            "layer1/companion_decision.md": """
            {
              "companion_action": "exit",
              "companion_mode": "none",
              "answer_status_override": "NOT_RECORDED",
              "reason": "answering current quiz question should return to quiz"
            }
            """
        }
    )
    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-companion-return-wording",
            message="22",
        ),
        context=None,
    )

    assert greeting.answer_status_code == "NOT_RECORDED"
    assert response.success is True
    assert response.answer_status_code == "RECORDED"
    assert response.pending_question.question_id == "question-02"
    assert response.assistant_message
    assert "问卷" not in response.assistant_message
    assert "陪你" not in response.assistant_message


def test_chat_quiz_answer_plus_distress_stays_in_companion_without_record_wording() -> None:
    service = GrpcQuizService()
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="session-answer-plus-distress-wording",
            language="zh-CN",
            questionnaire=_build_questionnaire(),
            quiz_mode="dynamic",
        ),
        context=None,
    )
    first = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-answer-plus-distress-wording",
            message="22",
        ),
        context=None,
    )

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-answer-plus-distress-wording",
            message="我一般11点睡，但最近总头疼睡不着",
        ),
        context=None,
    )

    assert first.answer_status_code == "RECORDED"
    assert response.success is True
    assert response.answer_status_code == "NOT_RECORDED"
    assert len(response.answer_record.answers) >= 1
    assert response.assistant_message
    assert "已记录" not in response.assistant_message
    assert "已记下" not in response.assistant_message


def test_chat_quiz_llm_orphan_emotion_tail_is_silently_recorded_in_companion_mode() -> None:
    service = GrpcQuizService()
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="session-llm-orphan-tail",
            language="zh-CN",
            questionnaire=[
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
            ],
            quiz_mode="dynamic",
        ),
        context=None,
    )
    snapshot = service._sessions["session-llm-orphan-tail"]
    snapshot.graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
        responses={
            "layer2/content_understand.md": """
            {
              "content_units": [
                {
                  "unit_id": "unit-1",
                  "unit_text": "18岁",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-01"],
                  "winner_question_id": "question-01",
                  "needs_attribution": false,
                  "raw_extracted_value": "18",
                  "selected_options": ["A"],
                  "input_value": "",
                  "field_updates": {},
                  "missing_fields": []
                },
                {
                  "unit_id": "unit-2",
                  "unit_text": "今天我很不开心",
                  "action_mode": "answer",
                  "candidate_question_ids": [],
                  "winner_question_id": null,
                  "needs_attribution": false,
                  "raw_extracted_value": "今天我很不开心",
                  "selected_options": [],
                  "input_value": "今天我很不开心",
                  "field_updates": {},
                  "missing_fields": []
                }
              ],
              "clarification_needed": true,
              "clarification_reason": "content_understand"
            }
            """
        }
    )
    snapshot.graph_state["runtime"]["llm_available"] = True

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-llm-orphan-tail",
            message="18岁，但是今天我很不开心",
        ),
        context=None,
    )

    assert response.success is True
    assert response.answer_status_code == "NOT_RECORDED"
    assert response.pending_question.question_id == "question-02"
    assert len(response.answer_record.answers) == 1
    assert response.answer_record.answers[0].question_id == "question-01"
    assert response.answer_record.answers[0].value.option_codes == ["A"]
    assert "已记录" not in response.assistant_message
    assert "recorded" not in response.assistant_message.lower()
    assert "updated" not in response.assistant_message.lower()


def test_chat_quiz_high_risk_distress_tail_records_answer_and_uses_supportive_reply() -> None:
    service = GrpcQuizService()
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="session-high-risk-distress-tail",
            language="zh-CN",
            questionnaire=[
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
            ],
            quiz_mode="dynamic",
        ),
        context=None,
    )
    snapshot = service._sessions["session-high-risk-distress-tail"]
    snapshot.graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
        responses={
            "layer2/content_understand.md": """
            {
              "content_units": [
                {
                  "unit_id": "unit-1",
                  "unit_text": "我18岁",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-01"],
                  "winner_question_id": "question-01",
                  "needs_attribution": false,
                  "raw_extracted_value": "18",
                  "selected_options": ["A"],
                  "input_value": "",
                  "field_updates": {},
                  "missing_fields": []
                },
                {
                  "unit_id": "unit-2",
                  "unit_text": "我好难受我想死",
                  "action_mode": "answer",
                  "candidate_question_ids": [],
                  "winner_question_id": null,
                  "needs_attribution": false,
                  "raw_extracted_value": "我好难受我想死",
                  "selected_options": [],
                  "input_value": "我好难受我想死",
                  "field_updates": {},
                  "missing_fields": []
                }
              ],
              "clarification_needed": true,
              "clarification_reason": "content_understand"
            }
            """,
            "layer3/companion_response.md": """
            {
              "assistant_message": "你先别一个人扛着，尽快找个你信任的人陪着你，好吗？"
            }
            """,
        }
    )
    snapshot.graph_state["runtime"]["llm_available"] = True

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-high-risk-distress-tail",
            message="我18岁，我好难受我想死",
        ),
        context=None,
    )

    assert response.success is True
    assert response.answer_status_code == "NOT_RECORDED"
    assert response.pending_question.question_id == "question-02"
    assert len(response.answer_record.answers) == 1
    assert response.answer_record.answers[0].question_id == "question-01"
    assert response.answer_record.answers[0].value.option_codes == ["A"]
    assert "信任的人" in response.assistant_message or "别一个人" in response.assistant_message
    assert "已记录" not in response.assistant_message


def test_chat_quiz_normal_distress_tail_records_schedule_and_stays_supportive() -> None:
    service = GrpcQuizService()
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="session-normal-distress-tail",
            language="zh-CN",
            questionnaire=[
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
            ],
            quiz_mode="dynamic",
        ),
        context=None,
    )
    first = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-normal-distress-tail",
            direct_answer=somni_quiz_pb2.DirectAnswer(
                question_id="question-01",
                selected_options=["A"],
            ),
        ),
        context=None,
    )
    snapshot = service._sessions["session-normal-distress-tail"]
    snapshot.graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "content",
              "non_content_intent": "none",
              "normalized_input": "早十晚七，好烦啊",
              "reason": "mixed turn with answer content"
            }
            """,
            "layer2/content_understand.md": """
            {
              "content_units": [
                {
                  "unit_id": "unit-1",
                  "unit_text": "早十晚七",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-02"],
                  "winner_question_id": "question-02",
                  "needs_attribution": false,
                  "raw_extracted_value": {
                    "bedtime": "19:00",
                    "wake_time": "10:00"
                  },
                  "selected_options": [],
                  "input_value": "19:00-10:00",
                  "field_updates": {
                    "bedtime": "19:00",
                    "wake_time": "10:00"
                  },
                  "missing_fields": []
                },
                {
                  "unit_id": "unit-2",
                  "unit_text": "好烦啊",
                  "action_mode": "answer",
                  "candidate_question_ids": [],
                  "winner_question_id": null,
                  "needs_attribution": false,
                  "raw_extracted_value": "好烦啊",
                  "selected_options": [],
                  "input_value": "好烦啊",
                  "field_updates": {},
                  "missing_fields": []
                }
              ],
              "clarification_needed": true,
              "clarification_reason": "content_understand"
            }
            """,
            "layer3/companion_response.md": """
            {
              "assistant_message": "听起来你这会儿真的有点烦，我在这儿陪你。"
            }
            """,
        }
    )
    snapshot.graph_state["runtime"]["llm_available"] = True

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-normal-distress-tail",
            message="早十晚七，好烦啊",
        ),
        context=None,
    )

    assert first.answer_status_code == "RECORDED"
    assert response.success is True
    answers = {answer.question_id: answer for answer in response.answer_record.answers}
    assert "question-02" in answers
    assert answers["question-02"].value.bedtime == "19:00"
    assert answers["question-02"].value.wake_time == "10:00"
    assert "信任的人" not in response.assistant_message
    assert "别一个人" not in response.assistant_message
    assert "烦" in response.assistant_message
    assert "已记录" not in response.assistant_message


def test_chat_quiz_records_schedule_when_identity_tail_still_requires_clarification() -> None:
    service = GrpcQuizService()
    questionnaire = [
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
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="session-schedule-plus-identity-tail",
            language="zh-CN",
            questionnaire=questionnaire,
            quiz_mode="dynamic",
        ),
        context=None,
    )
    first = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-schedule-plus-identity-tail",
            direct_answer=somni_quiz_pb2.DirectAnswer(
                question_id="question-01",
                selected_options=["A"],
            ),
        ),
        context=None,
    )
    snapshot = service._sessions["session-schedule-plus-identity-tail"]
    snapshot.graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "content",
              "non_content_intent": "none",
              "normalized_input": "早七晚十，你是谁",
              "reason": "mixed turn with answer content"
            }
            """,
            "layer2/content_understand.md": """
            {
              "content_units": [
                {
                  "unit_id": "unit-1",
                  "unit_text": "早七晚十",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-02"],
                  "winner_question_id": "question-02",
                  "needs_attribution": false,
                  "raw_extracted_value": {
                    "bedtime": "22:00",
                    "wake_time": "07:00"
                  },
                  "selected_options": [],
                  "input_value": "22:00-07:00",
                  "field_updates": {
                    "bedtime": "22:00",
                    "wake_time": "07:00"
                  },
                  "missing_fields": []
                },
                {
                  "unit_id": "unit-2",
                  "unit_text": "你是谁",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-02"],
                  "winner_question_id": null,
                  "needs_attribution": false,
                  "raw_extracted_value": "你是谁",
                  "selected_options": [],
                  "input_value": "你是谁",
                  "field_updates": {},
                  "missing_fields": []
                }
              ],
              "clarification_needed": true,
              "clarification_reason": "content_understand"
            }
            """,
        }
    )
    snapshot.graph_state["runtime"]["llm_available"] = True

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-schedule-plus-identity-tail",
            message="早七晚十，你是谁",
        ),
        context=None,
    )

    assert first.answer_status_code == "RECORDED"
    assert response.success is True
    answers = {answer.question_id: answer for answer in response.answer_record.answers}
    assert "question-02" in answers
    assert answers["question-02"].value.bedtime == "22:00"
    assert answers["question-02"].value.wake_time == "07:00"
    assert response.pending_question.question_id == ""


def test_chat_quiz_uses_llm_companion_decision_for_topic_chat() -> None:
    service = GrpcQuizService()
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="session-llm-companion-topic-chat",
            language="zh-CN",
            questionnaire=_build_questionnaire(),
            quiz_mode="dynamic",
        ),
        context=None,
    )
    snapshot = service._sessions["session-llm-companion-topic-chat"]
    provider = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "non_content",
              "non_content_intent": "pullback_chat",
              "normalized_input": "我想去旅游，你有什么建议吗",
              "reason": "free topic chat"
            }
            """,
            "layer1/companion_decision.md": """
            {
              "companion_action": "enter",
              "companion_mode": "smalltalk",
              "answer_status_override": "NOT_RECORDED",
              "reason": "topic chat should stay conversational"
            }
            """,
            "layer3/companion_response.md": """
            {
              "assistant_message": "如果你想轻松一点，可以先挑交通方便、节奏没那么赶的地方。"
            }
            """,
        }
    )
    snapshot.graph_state["runtime"]["llm_provider"] = provider
    snapshot.graph_state["runtime"]["llm_available"] = True
    snapshot.graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "smalltalk",
        "entered_from_question_id": "question-01",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "test_seed",
    }

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-llm-companion-topic-chat",
            message="我想去旅游，你有什么建议吗",
        ),
        context=None,
    )

    assert response.success is True
    assert response.answer_status_code == "NOT_RECORDED"
    assert response.assistant_message
    assert "交通方便" in response.assistant_message
    prompt_keys = [call[0] for call in provider.calls]
    assert "layer1/turn_classify.md" in prompt_keys
    assert "layer1/companion_decision.md" in prompt_keys
    assert "layer3/companion_response.md" in prompt_keys


def test_chat_quiz_answering_current_question_exits_companion_with_recorded_status() -> None:
    service = GrpcQuizService()
    questionnaire = [
        somni_quiz_pb2.BusinessQuestion(
            question_id="question-01",
            title="您的年龄段？",
            input_type="radio",
            options=[
                somni_quiz_pb2.BusinessOption(option_id="A", option_text="18-24 岁"),
                somni_quiz_pb2.BusinessOption(option_id="B", option_text="25-34 岁"),
            ],
        ),
        somni_quiz_pb2.BusinessQuestion(
            question_id="question-02",
            title="您平时通常的作息？",
            input_type="time_range",
            config=somni_quiz_pb2.PendingQuestionConfig(
                items=[
                    somni_quiz_pb2.PendingQuestionConfigItem(index=0, label="上床时间", format="HH:mm"),
                    somni_quiz_pb2.PendingQuestionConfigItem(index=1, label="起床时间", format="HH:mm"),
                ]
            ),
        ),
        somni_quiz_pb2.BusinessQuestion(
            question_id="question-03",
            title="完全自由安排时，您最自然的入睡时间是？",
            input_type="radio",
            options=[
                somni_quiz_pb2.BusinessOption(option_id="A", option_text="22:00 前"),
                somni_quiz_pb2.BusinessOption(option_id="B", option_text="22:00-23:30"),
            ],
        ),
    ]
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="session-companion-current-answer",
            language="zh-CN",
            questionnaire=questionnaire,
            quiz_mode="dynamic",
        ),
        context=None,
    )
    first = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-companion-current-answer",
            direct_answer=somni_quiz_pb2.DirectAnswer(
                question_id="question-01",
                selected_options=["B"],
            ),
        ),
        context=None,
    )
    snapshot = service._sessions["session-companion-current-answer"]
    snapshot.graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "supportive",
        "entered_from_question_id": "question-02",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "strong",
        "last_trigger_reason": "distress",
    }

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-companion-current-answer",
            message="晚上7点睡，早上10点起",
        ),
        context=None,
    )

    assert first.answer_status_code == "RECORDED"
    assert response.success is True
    assert response.answer_status_code == "RECORDED"
    assert response.pending_question.question_id == "question-03"
    answers = {answer.question_id: answer for answer in response.answer_record.answers}
    assert answers["question-02"].value.bedtime == "19:00"
    assert answers["question-02"].value.wake_time == "10:00"
    assert "问卷" not in response.assistant_message
    assert "陪你" not in response.assistant_message


def test_chat_quiz_view_control_does_not_report_recorded_with_existing_history() -> None:
    service = GrpcQuizService()
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="session-view-status",
            language="zh-CN",
            questionnaire=_build_questionnaire(),
            quiz_mode="dynamic",
        ),
        context=None,
    )
    service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-view-status",
            message="22",
        ),
        context=None,
    )

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-view-status",
            message="查看上一题记录",
        ),
        context=None,
    )

    assert response.success is True
    assert len(response.answer_record.answers) == 1
    assert response.answer_status_code == "NOT_RECORDED"


def test_chat_quiz_weather_query_uses_default_city_without_changing_progress() -> None:
    service = GrpcQuizService()
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="session-weather-query",
            language="zh-CN",
            questionnaire=_build_questionnaire(),
            quiz_mode="dynamic",
            default_city="北京",
        ),
        context=None,
    )

    class _WeatherTool:
        def get_current_weather(self, city: str) -> dict:
            return {"ok": True, "city": city, "summary": "晴，22C"}

    service._sessions["session-weather-query"].graph_state["runtime"]["weather_tool"] = _WeatherTool()

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-weather-query",
            message="今天天气怎么样",
        ),
        context=None,
    )

    assert response.success is True
    assert response.answer_status_code == "NOT_RECORDED"
    assert response.progress_percent == 0.0
    assert response.pending_question.question_id == "question-01"
    assert "北京" in response.assistant_message


def test_chat_quiz_undo_reports_updated_status() -> None:
    service = GrpcQuizService()
    service._sessions["session-undo-status"] = SessionSnapshot(
        graph_state={"session_memory": {"recent_turns": []}},
        quiz_mode="dynamic",
        language="zh-CN",
    )

    service._engine.run_turn = lambda graph_state, turn_input: {  # type: ignore[method-assign]
        "updated_graph_state": {
            "session_memory": {
                "recent_turns": [
                    {
                        "turn_index": 0,
                        "raw_input": "撤回",
                        "main_branch": "non_content",
                        "turn_outcome": "undo_applied",
                        "recorded_question_ids": [],
                        "modified_question_ids": [],
                        "partial_question_ids": [],
                        "skipped_question_ids": [],
                    }
                ]
            }
        },
        "assistant_message": "已恢复到上一次答案，我们继续回答当前这题。",
        "pending_question": None,
        "finalized": False,
        "answer_record": {
            "answers": [
                {
                    "question_id": "question-01",
                    "selected_options": ["A"],
                    "input_value": "",
                    "field_updates": {},
                }
            ]
        },
        "final_result": None,
    }

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-undo-status",
            message="撤回",
        ),
        context=None,
    )

    assert response.success is True
    assert response.answer_status_code == "UPDATED"


def test_chat_quiz_prefers_current_free_wake_question_over_regular_schedule_partial() -> None:
    service = GrpcQuizService()
    question_catalog = {
        "question_order": ["question-01", "question-02", "question-03", "question-04"],
        "question_index": {
            "question-01": {
                "question_id": "question-01",
                "title": "How old are you?",
                "description": "",
                "input_type": "text",
                "options": [],
                "tags": ["profile"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": None,
                    "response_style": "default",
                    "matching_hints": ["age"],
                },
            },
            "question-02": {
                "question_id": "question-02",
                "title": "What time do you usually sleep and wake?",
                "description": "",
                "input_type": "time_range",
                "options": [],
                "tags": ["schedule"],
                "config": {"items": []},
                "metadata": {
                    "allow_partial": True,
                    "structured_kind": "time_range",
                    "response_style": "followup",
                    "matching_hints": ["sleep", "bedtime"],
                },
            },
            "question-03": {
                "question_id": "question-03",
                "title": "What time do you fall asleep on free days?",
                "description": "",
                "input_type": "time_point",
                "options": [],
                "tags": ["relaxed_schedule"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "time_point",
                    "response_style": "followup",
                    "matching_hints": ["free day", "relaxed", "weekend sleep"],
                },
            },
            "question-04": {
                "question_id": "question-04",
                "title": "What time do you wake on free days?",
                "description": "",
                "input_type": "time_point",
                "options": [],
                "tags": ["relaxed_schedule"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "time_point",
                    "response_style": "followup",
                    "matching_hints": ["free day", "relaxed", "weekend wake"],
                },
            },
        },
    }
    graph_state = create_graph_state(
        session_id="session-current-free-wake-service",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-04"
    graph_state["session_memory"]["pending_question_ids"] = ["question-04"]
    graph_state["session_memory"]["unanswered_question_ids"] = ["question-01", "question-03", "question-04"]
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
        "last_action_mode": "partial_completion",
    }
    service._sessions["session-current-free-wake-service"] = SessionSnapshot(
        graph_state=graph_state,
        quiz_mode="dynamic",
        language="zh-CN",
    )

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-current-free-wake-service",
            message="11点起",
        ),
        context=None,
    )

    assert response.success is True
    assert response.answer_status_code == "RECORDED"
    assert [answer.question_id for answer in response.answer_record.answers] == ["question-04"]
    assert response.answer_record.answers[0].value.option_codes == ["D"]
