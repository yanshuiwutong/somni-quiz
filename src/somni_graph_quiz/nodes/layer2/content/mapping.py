"""Text option mapping helpers."""

from __future__ import annotations

import re

from somni_graph_quiz.utils.time_parse import parse_hour_token, parse_schedule_fragment


_TIME_TOKEN_PATTERN = re.compile(
    r"(?P<hour>\d{1,2}|十二|十一|十|两|零|一|二|三|四|五|六|七|八|九)"
    r"(?:[:：](?P<minute>\d{1,2}))?\s*(?:点|时)?\s*(?:左右)?"
)
_AGE_PATTERN = re.compile(r"\d{1,3}")
_ORDINAL_SELECTOR_PATTERN = re.compile(
    r"第\s*(?P<ordinal>\d{1,2}|十[一二三四五六七八九]?|[一二两三四五六七八九十])\s*(?:个|项|条|种)?"
)
_OPTION_ID_SELECTOR_TEMPLATE = r"(?:我选|选|就选|选择|答案是|答|是|就)\s*{option_id}(?:选项|项|个)?"

_TEN_MINUTE_TOKENS = (
    "十来分钟",
    "十几分钟",
    "十分钟",
    "10分钟",
    "10来分钟",
)
_SINGLE_CHOICE_INPUT_TYPES = {"radio", "single", "select", "time_point"}
_SELECTOR_TEXT_STRIP_PATTERN = re.compile(r"[\s,，。；;：:、.!?？“”\"'`~\-_/()（）]+")
_SEMANTIC_TEXT_PATTERN = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+")
_CHINESE_ORDINAL_MAP = {
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
}
_NON_ANSWER_TOKENS = (
    "你好",
    "您好",
    "哈哈",
    "哈哈哈",
    "hi",
    "hello",
    "hey",
    "thanks",
    "thankyou",
    "谢谢",
    "上一题",
    "下一题",
    "跳过",
    "查看记录",
    "看记录",
    "重新开始",
    "重来",
)
_SEMANTIC_STOP_TOKENS = {
    "什么",
    "怎么",
    "怎样",
    "多久",
    "一般",
    "完全",
    "需要",
    "情况",
    "时候",
    "早上",
    "晚上",
    "安排",
    "影响",
}


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


def map_content_answer(
    question: dict,
    raw_value: object,
    *,
    raw_text: str = "",
    allow_explicit_selectors: bool = True,
    allow_custom_empty_option_fallback: bool = False,
) -> dict:
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
    selector_text = raw_text or str(raw_value)
    if allow_explicit_selectors:
        explicit_option_id = extract_explicit_option_selector(question, selector_text)
        if explicit_option_id is not None:
            return {
                "selected_options": [explicit_option_id],
                "input_value": "",
                "field_updates": {},
                "missing_fields": [],
            }
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
    if allow_custom_empty_option_fallback:
        custom_fallback = _map_empty_option_custom_fallback(question, raw_text or str(raw_value))
        if custom_fallback is not None:
            return custom_fallback
    return {
        "selected_options": [],
        "input_value": raw_text or str(raw_value).strip(),
        "field_updates": {},
        "missing_fields": [],
    }


def map_empty_option_custom_fallback(question: dict | None, raw_text: str) -> dict | None:
    if not isinstance(question, dict):
        return None
    return _map_empty_option_custom_fallback(question, raw_text)


def should_prefer_empty_option_custom_fallback(question: dict | None, raw_text: str) -> bool:
    if not isinstance(question, dict):
        return False
    stripped_text = raw_text.strip()
    if not stripped_text:
        return False
    if extract_explicit_option_selector(question, stripped_text) is not None:
        return False
    fallback = _map_empty_option_custom_fallback(question, stripped_text)
    if fallback is None:
        return False
    return not _looks_like_clear_non_empty_option_match(question, stripped_text)


def extract_explicit_option_selector(question: dict | None, raw_text: str) -> str | None:
    if not _is_single_choice_question(question):
        return None

    options = list((question or {}).get("options", []))
    if not options:
        return None

    normalized_raw_text = _normalize_selector_text(raw_text)
    if not normalized_raw_text:
        return None

    ordinal_index = _extract_ordinal_selector_index(raw_text)
    if ordinal_index is not None and 0 <= ordinal_index < len(options):
        option_id = str(options[ordinal_index].get("option_id", "")).strip()
        if option_id:
            return option_id

    for option in options:
        option_id = str(option.get("option_id", "")).strip()
        if not option_id:
            continue
        if _matches_option_id_selector(raw_text, normalized_raw_text, option_id):
            return option_id
    return None


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
    if not _is_single_choice_question(question):
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


def _is_single_choice_question(question: dict | None) -> bool:
    if not isinstance(question, dict):
        return False
    input_type = str(question.get("input_type", "")).lower()
    if input_type in _SINGLE_CHOICE_INPUT_TYPES:
        return True
    metadata = question.get("metadata", {})
    structured_kind = str(metadata.get("structured_kind", "")).lower()
    return structured_kind in {"radio", "single", "select", "single_choice"}


def _extract_ordinal_selector_index(raw_text: str) -> int | None:
    match = _ORDINAL_SELECTOR_PATTERN.search(raw_text)
    if not match:
        return None
    ordinal_token = match.group("ordinal")
    ordinal_value = _parse_ordinal_token(ordinal_token)
    if ordinal_value is None or ordinal_value <= 0:
        return None
    return ordinal_value - 1


def _parse_ordinal_token(token: str) -> int | None:
    stripped = token.strip()
    if not stripped:
        return None
    if stripped.isdigit():
        return int(stripped)
    if stripped == "十":
        return 10
    if stripped.startswith("十") and len(stripped) == 2:
        return 10 + _CHINESE_ORDINAL_MAP.get(stripped[1], 0)
    return _CHINESE_ORDINAL_MAP.get(stripped)


def _matches_option_id_selector(raw_text: str, normalized_raw_text: str, option_id: str) -> bool:
    normalized_option_id = _normalize_selector_text(option_id).upper()
    if not normalized_option_id:
        return False
    if normalized_raw_text.upper() == normalized_option_id:
        return True

    raw_text_upper = raw_text.upper()
    selector_pattern = re.compile(
        _OPTION_ID_SELECTOR_TEMPLATE.format(option_id=re.escape(normalized_option_id))
    )
    return bool(selector_pattern.search(raw_text_upper))


def _normalize_selector_text(value: str) -> str:
    return _SELECTOR_TEXT_STRIP_PATTERN.sub("", value).strip()


def _normalize_text(value: str) -> str:
    return re.sub(r"[\s,，。；;：:、.!?？“”\"'`~\-_/]+", "", value).lower()


def _map_empty_option_custom_fallback(question: dict, raw_text: str) -> dict | None:
    fallback_option_id = _empty_option_fallback_id(question)
    stripped_text = raw_text.strip()
    if fallback_option_id is None or not stripped_text:
        return None
    if _looks_like_non_answer_text(stripped_text):
        return None
    if not _looks_related_to_question(question, stripped_text):
        return None
    return {
        "selected_options": [fallback_option_id],
        "input_value": stripped_text,
        "field_updates": {},
        "missing_fields": [],
    }


def _empty_option_fallback_id(question: dict | None) -> str | None:
    if not isinstance(question, dict):
        return None
    if str(question.get("input_type", "")).lower() != "radio":
        return None
    fallback_option_ids = []
    for option in question.get("options", []):
        option_id = str(option.get("option_id", "")).strip()
        if not option_id:
            continue
        option_text = str(option.get("option_text", option.get("label", ""))).strip()
        label = str(option.get("label", option.get("option_text", ""))).strip()
        if not option_text and not label:
            fallback_option_ids.append(option_id)
    if len(fallback_option_ids) != 1:
        return None
    return fallback_option_ids[0]


def _looks_like_non_answer_text(raw_text: str) -> bool:
    normalized_input = _normalize_text(raw_text)
    if not normalized_input:
        return True
    return any(token in normalized_input for token in _NON_ANSWER_TOKENS)


def _looks_related_to_question(question: dict, raw_text: str) -> bool:
    input_tokens = _semantic_tokens(raw_text)
    if not input_tokens:
        return False
    question_tokens = _question_semantic_tokens(question)
    if not question_tokens:
        return False
    return bool(input_tokens & question_tokens)


def _question_semantic_tokens(question: dict) -> set[str]:
    tokens: set[str] = set()
    for value in (
        question.get("title", ""),
        *question.get("metadata", {}).get("matching_hints", []),
    ):
        tokens.update(_semantic_tokens(str(value)))
    for option in question.get("options", []):
        for value in (
            option.get("label", ""),
            option.get("option_text", ""),
            *option.get("aliases", []),
        ):
            tokens.update(_semantic_tokens(str(value)))
    return tokens


def _looks_like_clear_non_empty_option_match(question: dict, raw_text: str) -> bool:
    normalized_input = _normalize_text(raw_text)
    if not normalized_input:
        return False
    input_tokens = _semantic_tokens(raw_text)
    question_context_tokens = _semantic_tokens(str(question.get("title", "")))
    for hint in question.get("metadata", {}).get("matching_hints", []):
        question_context_tokens.update(_semantic_tokens(str(hint)))

    for option in question.get("options", []):
        option_text = str(option.get("option_text", option.get("label", ""))).strip()
        label = str(option.get("label", option.get("option_text", ""))).strip()
        if not option_text and not label:
            continue

        variants = []
        for value in (label, option_text, *option.get("aliases", [])):
            variant = str(value).strip()
            if variant and variant not in variants:
                variants.append(variant)
        for variant in variants:
            normalized_variant = _normalize_text(variant)
            if not normalized_variant:
                continue
            if normalized_input == normalized_variant:
                return True
            if normalized_variant in normalized_input:
                return True
            if normalized_input in normalized_variant and len(normalized_input) >= 4:
                return True

        specific_tokens = _option_semantic_tokens(option) - question_context_tokens
        if input_tokens & specific_tokens:
            return True
    return False


def _option_semantic_tokens(option: dict) -> set[str]:
    tokens: set[str] = set()
    for value in (
        option.get("label", ""),
        option.get("option_text", ""),
        *option.get("aliases", []),
    ):
        tokens.update(_semantic_tokens(str(value)))
    return tokens


def _semantic_tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    for match in _SEMANTIC_TEXT_PATTERN.finditer(value):
        chunk = match.group(0).strip().lower()
        if not chunk:
            continue
        if chunk.isascii():
            if len(chunk) >= 2 and chunk not in _SEMANTIC_STOP_TOKENS:
                tokens.add(chunk)
            continue
        if len(chunk) == 1:
            continue
        for size in range(2, min(4, len(chunk)) + 1):
            for start in range(0, len(chunk) - size + 1):
                token = chunk[start:start + size]
                if token not in _SEMANTIC_STOP_TOKENS:
                    tokens.add(token)
    return tokens
