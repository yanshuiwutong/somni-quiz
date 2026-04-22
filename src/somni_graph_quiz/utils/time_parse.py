"""Time parsing helpers."""

from __future__ import annotations

import re


_HOUR_TOKEN_PATTERN = r"(?P<hour>\d{1,2}|十二|十一|十|两|零|一|二|三|四|五|六|七|八|九)"

SLEEP_PATTERN = re.compile(rf"{_HOUR_TOKEN_PATTERN}\s*点\s*睡")
WAKE_PATTERN = re.compile(rf"{_HOUR_TOKEN_PATTERN}\s*点\s*起")
TIME_POINT_PATTERN = re.compile(rf"^\s*{_HOUR_TOKEN_PATTERN}\s*点\s*$")

_CHINESE_HOUR_VALUES = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "十一": 11,
    "十二": 12,
}


def parse_schedule_fragment(raw_text: str) -> dict:
    """Parse a sleep schedule fragment into filled and missing fields."""
    filled_fields: dict[str, str] = {}
    sleep_match = SLEEP_PATTERN.search(raw_text)
    wake_match = WAKE_PATTERN.search(raw_text)
    if sleep_match:
        filled_fields["bedtime"] = _normalize_sleep_hour(parse_hour_token(sleep_match.group("hour")))
    if wake_match:
        filled_fields["wake_time"] = _format_hour(parse_hour_token(wake_match.group("hour")))
    missing_fields = [
        field for field in ("bedtime", "wake_time") if field not in filled_fields
    ]
    return {
        "filled_fields": filled_fields,
        "missing_fields": missing_fields,
        "is_time_point_only": bool(TIME_POINT_PATTERN.match(raw_text)),
    }


def build_time_range_input_value(filled_fields: dict[str, str]) -> str:
    """Build a time range string from filled fields."""
    return f'{filled_fields["bedtime"]}-{filled_fields["wake_time"]}'


def parse_hour_token(raw_hour: str) -> int:
    """Parse an Arabic or common Chinese hour token."""
    raw_hour = raw_hour.strip()
    if raw_hour.isdigit():
        return int(raw_hour)
    if raw_hour in _CHINESE_HOUR_VALUES:
        return _CHINESE_HOUR_VALUES[raw_hour]
    raise ValueError(f"Unsupported hour token: {raw_hour}")


def _normalize_sleep_hour(hour: int) -> str:
    if hour < 12:
        hour += 12
    return _format_hour(hour)


def _format_hour(hour: int) -> str:
    return f"{hour % 24:02d}:00"
