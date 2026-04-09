"""Integration tests for the gRPC adapter."""

import grpc

from somni_quiz_ai.grpc.generated import somni_quiz_pb2

from somni_graph_quiz.adapters.grpc.service import GrpcQuizService, SessionSnapshot
from somni_graph_quiz.contracts.graph_state import create_graph_state


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
    assert "入睡" in response.assistant_message or "几点睡" in response.assistant_message


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
