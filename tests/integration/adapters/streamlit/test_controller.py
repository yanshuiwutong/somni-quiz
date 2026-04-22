"""Integration tests for the Streamlit controller adapter."""

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
            "config": {
                "items": [
                    {"index": 0, "label": "上床时间：", "format": "HH:mm"},
                    {"index": 1, "label": "起床时间：", "format": "HH:mm"},
                ]
            },
        },
    ]


def test_initialize_session_stores_default_city() -> None:
    controller = StreamlitQuizController()

    view = controller.initialize_session(
        session_id="streamlit-default-city",
        questionnaire=_build_questionnaire(),
        language_preference="zh-CN",
        quiz_mode="dynamic",
        default_city="上海",
    )

    assert view["pending_question"]["question_id"] == "question-01"
    assert view["initialized"] is True
    assert view["success"] is True
    assert view["answer_status_code"] == "NOT_RECORDED"
    assert controller._sessions["streamlit-default-city"].graph_state["session"]["default_city"] == "上海"


def test_submit_message_weather_query_uses_default_city_without_changing_progress() -> None:
    controller = StreamlitQuizController()
    controller.initialize_session(
        session_id="streamlit-weather",
        questionnaire=_build_questionnaire(),
        language_preference="zh-CN",
        quiz_mode="dynamic",
        default_city="北京",
    )

    class _WeatherTool:
        def get_current_weather(self, city: str) -> dict:
            return {"ok": True, "city": city, "summary": "晴，22C"}

    controller._sessions["streamlit-weather"].graph_state["runtime"]["weather_tool"] = _WeatherTool()

    view = controller.submit_message(session_id="streamlit-weather", message="今天天气怎么样")

    assert view["progress_percent"] == 0.0
    assert view["pending_question"]["question_id"] == "question-01"
    assert view["answer_status_code"] == "NOT_RECORDED"
    assert "北京" in view["assistant_message"]


def test_initialize_session_restores_existing_snapshot() -> None:
    controller = StreamlitQuizController()
    controller.initialize_session(
        session_id="streamlit-restore",
        questionnaire=_build_questionnaire(),
        language_preference="zh-CN",
        quiz_mode="dynamic",
        default_city="上海",
    )
    answered_view = controller.submit_message(session_id="streamlit-restore", message="22")

    restored_view = controller.initialize_session(
        session_id="streamlit-restore",
        questionnaire=_build_questionnaire(),
        language_preference="en",
        quiz_mode="fixed",
        default_city="北京",
    )

    assert answered_view["answer_status_code"] == "RECORDED"
    assert restored_view["success"] is True
    assert restored_view["initialized"] is True
    assert restored_view["pending_question"]["question_id"] == "question-02"
    assert restored_view["answer_record"]["answers"][0]["question_id"] == "question-01"
    assert restored_view["progress_percent"] == 50.0
    assert restored_view["quiz_mode"] == "dynamic"
    assert controller._sessions["streamlit-restore"].graph_state["session"]["default_city"] == "上海"


def test_submit_message_returns_failed_view_when_session_missing() -> None:
    controller = StreamlitQuizController()

    view = controller.submit_message(session_id="missing-streamlit-session", message="22")

    assert view["success"] is False
    assert view["initialized"] is False
    assert view["answer_status_code"] == "NOT_RECORDED"
    assert view["assistant_message"] == "Session not initialized. Call initialize_session first."


def test_submit_direct_answer_supports_time_range_completion() -> None:
    controller = StreamlitQuizController()
    controller.initialize_session(
        session_id="streamlit-direct-answer",
        questionnaire=_build_questionnaire(),
        language_preference="zh-CN",
        quiz_mode="dynamic",
    )
    first = controller.submit_direct_answer(
        session_id="streamlit-direct-answer",
        answer={
            "question_id": "question-01",
            "selected_options": ["A"],
            "input_value": "",
        },
    )

    second = controller.submit_direct_answer(
        session_id="streamlit-direct-answer",
        answer={
            "question_id": "question-02",
            "selected_options": [],
            "input_value": "23点睡 7点起",
        },
    )

    assert first["answer_status_code"] == "RECORDED"
    assert second["success"] is True
    assert second["finalized"] is True
    answers = {answer["question_id"]: answer for answer in second["answer_record"]["answers"]}
    assert answers["question-02"]["field_updates"] == {"bedtime": "23:00", "wake_time": "07:00"}
