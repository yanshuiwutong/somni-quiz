"""Integration tests for the gRPC adapter."""

from somni_quiz_ai.grpc.generated import somni_quiz_pb2

from somni_graph_quiz.adapters.grpc.service import GrpcQuizService


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
    assert response.pending_question.question_id == "question-02"


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
    assert response.assistant_message
