"""Consistency checks across adapter layers."""

from somni_quiz_ai.grpc.generated import somni_quiz_pb2

from somni_graph_quiz.adapters.grpc.service import GrpcQuizService
from somni_graph_quiz.adapters.streamlit.controller import StreamlitQuizController


def _grpc_questionnaire() -> list:
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


def _streamlit_questionnaire() -> list[dict]:
    return [
        {"question_id": "question-01", "title": "How old are you?", "input_type": "text", "tags": [], "options": []},
        {
            "question_id": "question-02",
            "title": "What time do you usually sleep and wake?",
            "input_type": "time_range",
            "tags": [],
            "options": [],
        },
    ]


def test_grpc_and_streamlit_share_core_turn_results() -> None:
    grpc_service = GrpcQuizService()
    streamlit_controller = StreamlitQuizController()

    grpc_service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="session-grpc",
            language="en",
            questionnaire=_grpc_questionnaire(),
            quiz_mode="dynamic",
        ),
        context=None,
    )
    streamlit_controller.initialize_session(
        session_id="session-streamlit",
        questionnaire=_streamlit_questionnaire(),
        language_preference="en",
        quiz_mode="dynamic",
    )

    grpc_response = grpc_service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(session_id="session-grpc", message="22"),
        context=None,
    )
    streamlit_view = streamlit_controller.submit_message(session_id="session-streamlit", message="22")

    assert grpc_response.pending_question.question_id == streamlit_view["pending_question"]["question_id"]
    assert grpc_response.answer_record.answers[0].question_id == streamlit_view["answer_record"]["answers"][0]["question_id"]
    assert grpc_response.progress_percent == streamlit_view["progress_percent"] == 50.0
