"""Tests for standalone Streamlit app helper functions."""

from somni_graph_quiz.app.streamlit_app import (
    build_direct_answer_payload,
    format_answer_status,
)


def test_build_direct_answer_payload_for_time_range_joins_non_empty_fields() -> None:
    payload = build_direct_answer_payload(
        {
            "question_id": "question-02",
            "input_type": "time_range",
            "config": {
                "items": [
                    {"index": 0, "label": "上床时间：", "format": "HH:mm"},
                    {"index": 1, "label": "起床时间：", "format": "HH:mm"},
                ]
            },
        },
        field_values={0: "23:00", 1: "07:00"},
    )

    assert payload == {
        "question_id": "question-02",
        "selected_options": [],
        "input_value": "23点睡 7点起",
    }


def test_build_direct_answer_payload_for_text_keeps_raw_input() -> None:
    payload = build_direct_answer_payload(
        {
            "question_id": "question-05",
            "input_type": "text",
            "config": None,
        },
        input_value="最近总是醒得早",
    )

    assert payload == {
        "question_id": "question-05",
        "selected_options": [],
        "input_value": "最近总是醒得早",
    }


def test_format_answer_status_localizes_known_codes() -> None:
    assert format_answer_status("RECORDED", language_preference="zh-CN") == "本轮状态：已记录答案"
    assert format_answer_status("UPDATED", language_preference="en") == "Turn status: answer updated"
