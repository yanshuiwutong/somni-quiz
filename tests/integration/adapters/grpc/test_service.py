"""Integration tests for the gRPC adapter."""

import grpc

from somni_quiz_ai.grpc.generated import somni_quiz_pb2

from somni_graph_quiz.adapters.grpc.service import GrpcQuizService, SessionSnapshot


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


def test_chat_quiz_falls_back_to_recorded_when_turn_metadata_is_missing(monkeypatch) -> None:
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
    assert response.answer_status_code == "RECORDED"
