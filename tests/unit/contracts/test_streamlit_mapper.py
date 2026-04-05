"""Tests for Streamlit mapping helpers."""

from somni_graph_quiz.adapters.streamlit.mapper import (
    build_streamlit_view,
    map_streamlit_questionnaire_to_catalog,
)


def test_map_streamlit_questionnaire_to_catalog_preserves_titles() -> None:
    catalog = map_streamlit_questionnaire_to_catalog(
        [
            {"question_id": "question-01", "title": "Q1", "input_type": "text", "tags": [], "options": []},
            {"question_id": "question-02", "title": "Q2", "input_type": "time_range", "tags": [], "options": []},
        ]
    )

    assert catalog["question_order"] == ["question-01", "question-02"]
    assert catalog["question_index"]["question-02"]["title"] == "Q2"


def test_build_streamlit_view_contains_chat_and_pending_question() -> None:
    view = build_streamlit_view(
        session_id="streamlit-1",
        assistant_message="Hello",
        answer_record={"answers": []},
        pending_question={"question_id": "question-01", "title": "Q1"},
        finalized=False,
        final_result=None,
        quiz_mode="dynamic",
        chat_history=[{"role": "assistant", "content": "Hello"}],
    )

    assert view["pending_question"]["question_id"] == "question-01"
    assert view["chat_history"][0]["content"] == "Hello"


def test_map_streamlit_questionnaire_to_catalog_preserves_config() -> None:
    catalog = map_streamlit_questionnaire_to_catalog(
        [
            {
                "question_id": "question-02",
                "title": "Q2",
                "input_type": "time_range",
                "tags": [],
                "options": [],
                "config": {
                    "items": [
                        {"index": 0, "label": "上床时间：", "format": "HH:mm"},
                        {"index": 1, "label": "起床时间：", "format": "HH:mm"},
                    ]
                },
            }
        ]
    )

    assert catalog["question_index"]["question-02"]["config"] == {
        "items": [
            {"index": 0, "label": "上床时间：", "format": "HH:mm"},
            {"index": 1, "label": "起床时间：", "format": "HH:mm"},
        ]
    }
