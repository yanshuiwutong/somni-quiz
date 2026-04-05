"""Integration tests for the Streamlit adapter."""

from somni_graph_quiz.app.settings import GraphQuizSettings
from somni_graph_quiz.adapters.streamlit.controller import StreamlitQuizController


def _questionnaire() -> list[dict]:
    return [
        {
            "question_id": "question-01",
            "title": "How old are you?",
            "input_type": "text",
            "tags": ["profile"],
            "options": [],
            "description": "",
        },
        {
            "question_id": "question-02",
            "title": "What time do you usually sleep and wake?",
            "input_type": "time_range",
            "tags": ["schedule"],
            "options": [],
            "description": "",
        },
    ]


def test_controller_initialize_creates_assistant_message() -> None:
    controller = StreamlitQuizController()

    view = controller.initialize_session(
        session_id="streamlit-1",
        questionnaire=_questionnaire(),
        language_preference="en",
        quiz_mode="dynamic",
    )

    assert view["chat_history"][0]["role"] == "assistant"
    assert view["pending_question"]["question_id"] == "question-01"


def test_controller_submit_message_updates_chat_history() -> None:
    controller = StreamlitQuizController()
    controller.initialize_session(
        session_id="streamlit-1",
        questionnaire=_questionnaire(),
        language_preference="en",
        quiz_mode="dynamic",
    )

    view = controller.submit_message(session_id="streamlit-1", message="22")

    assert view["chat_history"][-2]["content"] == "22"
    assert view["chat_history"][-1]["role"] == "assistant"
    assert view["pending_question"]["question_id"] == "question-02"


def test_controller_submit_direct_answer_uses_runtime() -> None:
    controller = StreamlitQuizController()
    controller.initialize_session(
        session_id="streamlit-2",
        questionnaire=_questionnaire(),
        language_preference="zh-CN",
        quiz_mode="dynamic",
    )

    view = controller.submit_direct_answer(
        session_id="streamlit-2",
        answer={"question_id": "question-01", "input_value": "29", "selected_options": []},
    )

    assert view["answer_record"]["answers"][0]["question_id"] == "question-01"
    assert view["assistant_message"]


def test_controller_refresh_runtime_reinjects_provider(monkeypatch) -> None:
    controller = StreamlitQuizController()
    controller.initialize_session(
        session_id="streamlit-3",
        questionnaire=_questionnaire(),
        language_preference="zh-CN",
        quiz_mode="dynamic",
    )
    seen_models: list[str] = []

    def _fake_apply_runtime_dependencies(graph_state: dict, settings=None) -> None:
        model_name = "default" if settings is None else settings.llm_model
        seen_models.append(model_name)
        graph_state["runtime"]["llm_provider"] = model_name

    monkeypatch.setattr(
        "somni_graph_quiz.adapters.streamlit.controller.apply_runtime_dependencies",
        _fake_apply_runtime_dependencies,
    )

    controller.refresh_runtime(
        session_id="streamlit-3",
        settings=GraphQuizSettings(
            llm_base_url="https://ark.cn-beijing.volces.com/api/v3",
            llm_api_key="test-key",
            llm_model="doubao-online",
        ),
    )

    assert seen_models == ["doubao-online"]
    assert controller._sessions["streamlit-3"].graph_state["runtime"]["llm_provider"] == "doubao-online"
