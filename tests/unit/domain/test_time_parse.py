"""Tests for simple time parsing helpers."""

from somni_graph_quiz.utils.time_parse import parse_schedule_fragment


def test_parse_schedule_fragment_returns_partial_bedtime() -> None:
    parsed = parse_schedule_fragment("11点睡")

    assert parsed["filled_fields"] == {"bedtime": "23:00"}
    assert parsed["missing_fields"] == ["wake_time"]


def test_parse_schedule_fragment_returns_complete_range() -> None:
    parsed = parse_schedule_fragment("11点睡7点起")

    assert parsed["filled_fields"] == {"bedtime": "23:00", "wake_time": "07:00"}
    assert parsed["missing_fields"] == []
