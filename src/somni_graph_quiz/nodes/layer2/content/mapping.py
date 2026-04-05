"""Text option mapping helpers."""

from __future__ import annotations

import re

from somni_graph_quiz.utils.time_parse import parse_hour_token, parse_schedule_fragment


_TIME_TOKEN_PATTERN = re.compile(
    r"(?P<hour>\d{1,2}|十二|十一|十|两|零|一|二|三|四|五|六|七|八|九)"
    r"(?:[:：](?P<minute>\d{1,2}))?\s*(?:点|时)?\s*(?:左右)?"
)
_AGE_PATTERN = re.compile(r"\d{1,3}")

_TEN_MINUTE_TOKENS = (
    "十来分钟",
    "十几分钟",
    "十分钟",
    "10分钟",
    "10来分钟",
)


def map_content_value(question_id: str, raw_value: object) -> dict:
    """Map a resolved content value into a normalized answer payload."""
    if question_id == "question-02":
        if isinstance(raw_value, dict):
            filled_fields = dict(raw_value)
            missing_fields = [
                field for field in ("bedtime", "wake_time") if field not in filled_fields
            ]
            return {"filled_fields": filled_fields, "missing_fields": missing_fields}
        return parse_schedule_fragment(str(raw_value))

    if isinstance(raw_value, dict):
        selected_options = list(raw_value.get("selected_options", []))
        if selected_options:
            return {
                "selected_options": selected_options,
                "input_value": str(raw_value.get("input_value", "")),
            }
        raw_text = str(raw_value.get("input_value", "")).strip()
    else:
        raw_text = str(raw_value).strip()

    if question_id == "question-01":
        option_id = _map_age_option(raw_text)
        if option_id:
            return {"selected_options": [option_id], "input_value": ""}
    if question_id == "question-03":
        option_id = _map_free_sleep_option(raw_text)
        if option_id:
            return {"selected_options": [option_id], "input_value": ""}
    if question_id == "question-04":
        option_id = _map_free_wake_option(raw_text)
        if option_id:
            return {"selected_options": [option_id], "input_value": ""}
    if question_id == "question-08":
        if any(token in raw_text for token in _TEN_MINUTE_TOKENS):
            return {"selected_options": ["A"], "input_value": ""}

    return {"selected_options": [], "input_value": raw_text}


def _map_free_sleep_option(raw_text: str) -> str | None:
    time_parts = _extract_time(raw_text)
    if time_parts is None:
        return None
    hour, minute = time_parts
    if hour < 12:
        hour += 24
    total_minutes = hour * 60 + minute
    if total_minutes < 22 * 60:
        return "A"
    if total_minutes <= 23 * 60 + 15:
        return "B"
    if total_minutes <= 24 * 60 + 30:
        return "C"
    return "D"


def _map_free_wake_option(raw_text: str) -> str | None:
    time_parts = _extract_time(raw_text)
    if time_parts is None:
        return None
    hour, minute = time_parts
    total_minutes = hour * 60 + minute
    if total_minutes < 6 * 60:
        return "A"
    if total_minutes <= 7 * 60 + 45:
        return "B"
    if total_minutes <= 9 * 60 + 45:
        return "C"
    return "D"


def _extract_time(raw_text: str) -> tuple[int, int] | None:
    match = _TIME_TOKEN_PATTERN.search(raw_text)
    if not match:
        return None
    hour = parse_hour_token(match.group("hour")) % 24
    minute_text = match.group("minute")
    minute = 0 if minute_text is None else max(0, min(59, int(minute_text)))
    return hour, minute


def _map_age_option(raw_text: str) -> str | None:
    if any(token in raw_text for token in ("不愿透露", "不方便", "保密")):
        return "F"
    numbers = [int(value) for value in _AGE_PATTERN.findall(raw_text)]
    if not numbers:
        return None
    if len(numbers) >= 2 and any(token in raw_text for token in ("-", "~", "到", "至")):
        age = max(numbers[0], numbers[1])
    else:
        age = numbers[-1]
    if age < 25:
        return "A"
    if age < 35:
        return "B"
    if age < 45:
        return "C"
    if age < 55:
        return "D"
    return "E"
