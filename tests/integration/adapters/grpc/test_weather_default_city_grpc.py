"""gRPC adapter tests for weather default city behavior."""

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


def test_init_quiz_without_default_city_keeps_empty_session_default_city() -> None:
    service = GrpcQuizService()
    request = somni_quiz_pb2.InitQuizRequest(
        session_id="session-no-default-city",
        language="zh-CN",
        questionnaire=_build_questionnaire(),
        quiz_mode="dynamic",
    )

    response = service.InitQuiz(request, context=None)

    assert response.success is True
    assert service._sessions["session-no-default-city"].graph_state["session"]["default_city"] == ""


def test_chat_quiz_weather_query_without_default_city_asks_for_city() -> None:
    service = GrpcQuizService()
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="session-weather-no-city",
            language="zh-CN",
            questionnaire=_build_questionnaire(),
            quiz_mode="dynamic",
        ),
        context=None,
    )
    service._sessions["session-weather-no-city"].graph_state["runtime"]["llm_provider"] = None
    service._sessions["session-weather-no-city"].graph_state["runtime"]["llm_available"] = False

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-weather-no-city",
            message="今天天气怎么样",
        ),
        context=None,
    )

    assert response.success is True
    assert response.answer_status_code == "NOT_RECORDED"
    assert response.progress_percent == 0.0
    assert response.pending_question.question_id == "question-01"
    assert "城市" in response.assistant_message
