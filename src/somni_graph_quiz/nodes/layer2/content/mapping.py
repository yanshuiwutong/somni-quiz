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
        if not raw_text and question_id == "question-03":
            bedtime = raw_value.get("bedtime")
            if bedtime:
                raw_text = str(bedtime).strip()
        if not raw_text and question_id == "question-04":
            wake_time = raw_value.get("wake_time")
            if wake_time:
                raw_text = str(wake_time).strip()
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


def map_content_answer(question: dict, raw_value: object, *, raw_text: str = "") -> dict:
    """Map an extracted content value into a normalized answer payload."""
    if isinstance(raw_value, dict):
        selected_options = list(raw_value.get("selected_options", []))
        if selected_options:
            return {
                "selected_options": selected_options,
                "input_value": str(raw_value.get("input_value", "")),
                "field_updates": dict(raw_value.get("field_updates", {})),
                "missing_fields": list(raw_value.get("missing_fields", [])),
            }
        field_updates = dict(raw_value.get("field_updates", raw_value.get("filled_fields", {})))
        missing_fields = list(raw_value.get("missing_fields", []))
        if field_updates or missing_fields:
            return {
                "selected_options": [],
                "input_value": str(raw_value.get("input_value", "")),
                "field_updates": field_updates,
                "missing_fields": missing_fields,
            }

    question_id = str(question.get("question_id", ""))
    mapped = map_content_value(question_id, raw_value)
    selected_options = list(mapped.get("selected_options", []))
    field_updates = dict(mapped.get("filled_fields", {}))
    missing_fields = list(mapped.get("missing_fields", []))
    input_value = str(mapped.get("input_value", ""))
    if selected_options or field_updates or missing_fields:
        return {
            "selected_options": selected_options,
            "input_value": input_value,
            "field_updates": field_updates,
            "missing_fields": missing_fields,
        }

    generic = _map_generic_question_options(question, raw_text or str(raw_value))
    if generic["selected_options"]:
        return generic
    return {
        "selected_options": [],
        "input_value": raw_text or str(raw_value).strip(),
        "field_updates": {},
        "missing_fields": [],
    }


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


def _map_generic_question_options(question: dict, raw_text: str) -> dict:
    input_type = str(question.get("input_type", "")).lower()
    if input_type not in {"radio", "single", "select", "time_point"}:
        return {
            "selected_options": [],
            "input_value": raw_text.strip(),
            "field_updates": {},
            "missing_fields": [],
        }

    options = list(question.get("options", []))
    normalized_input = _normalize_text(raw_text)
    if not normalized_input:
        return {
            "selected_options": [],
            "input_value": "",
            "field_updates": {},
            "missing_fields": [],
        }

    best_score = 0
    best_option_id: str | None = None
    has_tie = False
    for index, option in enumerate(options):
        option_id = str(option.get("option_id", ""))
        score = _score_option_match(question, option, normalized_input, index=index, option_count=len(options))
        if score > best_score:
            best_score = score
            best_option_id = option_id
            has_tie = False
        elif score > 0 and score == best_score:
            has_tie = True
    if best_option_id and not has_tie:
        return {
            "selected_options": [best_option_id],
            "input_value": "",
            "field_updates": {},
            "missing_fields": [],
        }
    return {
        "selected_options": [],
        "input_value": raw_text.strip(),
        "field_updates": {},
        "missing_fields": [],
    }


def _score_option_match(question: dict, option: dict, normalized_input: str, *, index: int, option_count: int) -> int:
    variants = []
    label = str(option.get("label", option.get("option_text", ""))).strip()
    if label:
        variants.append(label)
    variants.extend(str(alias).strip() for alias in option.get("aliases", []) if str(alias).strip())
    best_score = 0
    for variant in variants:
        normalized_variant = _normalize_text(variant)
        if not normalized_variant:
            continue
        if normalized_input == normalized_variant:
            best_score = max(best_score, 100)
        elif normalized_variant in normalized_input:
            best_score = max(best_score, 90)
        elif normalized_input in normalized_variant and len(normalized_input) >= 4:
            best_score = max(best_score, 80)

    best_score = max(
        best_score,
        _score_sensitivity_scale(question, option, normalized_input, index=index, option_count=option_count),
    )
    return best_score


def _score_sensitivity_scale(
    question: dict,
    option: dict,
    normalized_input: str,
    *,
    index: int,
    option_count: int,
) -> int:
    title = _normalize_text(str(question.get("title", "")))
    label = _normalize_text(str(option.get("label", option.get("option_text", ""))))
    if "敏感" not in title:
        return 0
    if any(token in normalized_input for token in ("不敏感", "完全不敏感")):
        return 85 if "不敏感" in label else 0
    if any(token in normalized_input for token in ("轻微敏感", "有点敏感", "稍微敏感")):
        return 85 if "轻微敏感" in label else 0
    if any(token in normalized_input for token in ("需要安静", "避光", "安静", "黑一点")):
        return 85 if any(token in label for token in ("安静", "避光")) else 0
    if any(token in normalized_input for token in ("很敏感", "比较敏感", "容易醒", "易惊醒")):
        if any(token in label for token in ("惊醒", "细小声音", "微光")):
            return 86
        if option_count >= 5 and index == option_count - 2:
            return 84
    if any(token in normalized_input for token in ("必须绝对", "绝对安静", "绝对黑暗", "一点都不能", "完全黑暗")):
        if any(token in label for token in ("必须", "绝对")):
            return 88
        if option_count >= 5 and index == option_count - 1:
            return 84
    return 0


def _normalize_text(value: str) -> str:
    return re.sub(r"[\s,，。；;：:、.!?？“”\"'`~\-_/]+", "", value).lower()
