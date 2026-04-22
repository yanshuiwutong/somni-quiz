"""Streamlit adapter tests for weather default city behavior."""

from somni_graph_quiz.adapters.streamlit.controller import StreamlitQuizController


def _build_questionnaire() -> list[dict]:
    return [
        {
            "question_id": "question-01",
            "title": "您的年龄段？",
            "input_type": "radio",
            "tags": ["基础信息"],
            "options": [
                {"option_id": "A", "option_text": "18-24 岁"},
                {"option_id": "B", "option_text": "25-34 岁"},
            ],
        },
        {
            "question_id": "question-02",
            "title": "您平时通常的作息？",
            "input_type": "time_range",
            "tags": ["基础信息"],
            "options": [],
            "config": {"items": []},
        },
    ]


def test_initialize_session_without_default_city_keeps_empty_default_city() -> None:
    controller = StreamlitQuizController()

    view = controller.initialize_session(
        session_id="streamlit-no-default-city",
        questionnaire=_build_questionnaire(),
        language_preference="zh-CN",
        quiz_mode="dynamic",
    )

    assert view["pending_question"]["question_id"] == "question-01"
    assert controller._sessions["streamlit-no-default-city"].graph_state["session"]["default_city"] == ""
