"""Rule helpers for companion transition decisions."""

from __future__ import annotations

_SUPPORTIVE_TOKENS = (
    "头疼",
    "难受",
    "难过",
    "心情不好",
    "不开心",
    "睡不着",
    "失眠",
    "烦",
    "焦虑",
    "崩溃",
    "委屈",
    "压力",
    "怎么办",
)
_HIGH_RISK_TOKENS = (
    "想死",
    "不想活",
    "活不下去",
    "自杀",
    "自残",
    "结束生命",
    "结束自己",
    "去死",
    "死了算了",
)
_RETURN_TOKENS = ("继续问卷", "下一题", "先不聊了")
_STRONG_TOKENS = (
    "其实还有",
    "而且",
    "怎么办",
    "为什么",
    "很烦",
    "头疼",
    "难过",
    "不开心",
    "睡不着",
    "压力",
    "想死",
    "不想活",
    "活不下去",
    "自杀",
    "自残",
)
_OPEN_QUESTION_TOKENS = (
    "怎么办",
    "为什么",
    "怎么做",
    "怎么才能",
    "你觉得",
    "能具体说说",
    "能不能具体说说",
    "怎么安排",
    "哪个更适合",
    "哪种更适合",
    "要不要",
    "推荐去哪",
    "推荐去哪里",
    "推荐哪儿",
)
_OPEN_INTERROGATIVE_TOKENS = (
    "什么",
    "怎么",
    "怎样",
    "怎么样",
    "为何",
    "为什么",
    "哪",
    "哪里",
    "哪儿",
    "哪个",
    "哪些",
    "谁",
    "推荐",
    "建议",
    "有啥",
    "有什么",
    "坏处",
    "好处",
    "区别",
    "适合",
)
_OPEN_TOPIC_TOKENS = (
    "旅游",
    "旅行",
    "景点",
    "去哪玩",
    "去哪里玩",
    "哪里好玩",
    "海边",
    "小城",
    "散散心",
    "放松",
    "住两天",
    "待两天",
    "美食",
    "吃点好的",
    "攻略",
    "路线",
    "安排",
    "周末",
)
_DEFER_CHAT_TOKENS = (
    "先聊别的",
    "先聊点别的",
    "先不答",
    "先不说这个",
    "先不聊问卷",
    "先聊聊",
    "想继续聊",
    "继续聊聊",
    "接着聊",
    "再聊聊",
)
_CONTROL_TOKENS = (
    "下一题",
    "跳过",
    "继续问卷",
    "上一题",
    "改上一题",
    "修改上一题",
    "查看",
    "撤回",
)
_TOOL_TOKENS = ("天气", "weather")
_IDENTITY_TOKENS = ("你是谁", "who are you")
_GREETING_TOKENS = ("你好", "您好", "hello", "hi", "hey", "哈哈", "在吗")
_POLITE_CLOSE_TOKENS = (
    "谢谢",
    "感谢",
    "好的",
    "好哦",
    "嗯嗯",
    "知道了",
)
_CLOSED_CONFIRMATION_TOKENS = (
    "对吗",
    "是吗",
    "可以吗",
    "行吗",
    "好不好",
    "是不是",
)
_SHORT_CONFIRMATION_TOKENS = (
    "好的",
    "嗯",
    "嗯嗯",
    "可以",
    "行",
    "好的呀",
    "是的",
    "对",
    "明白了",
)
_SHORT_CONTEXTUAL_FRAGMENT_TOKENS = (
    "北京",
    "海边",
    "三天",
    "安静点",
    "工作忙的时候",
    "一般在晚上",
)


def detect_entry_mode(
    *,
    raw_input: str,
    main_branch: str,
    non_content_intent: str,
    applied_question_ids: list[str],
    modified_question_ids: list[str],
    partial_question_ids: list[str],
) -> str | None:
    """Return companion mode to enter, if this turn should enter companion mode."""
    if non_content_intent == "identity":
        return "smalltalk"
    if non_content_intent == "pullback_chat":
        if detect_distress_level(raw_input) != "none":
            return "supportive"
        return "smalltalk"
    has_question_activity = bool(applied_question_ids or modified_question_ids or partial_question_ids)
    if main_branch == "content" and has_question_activity and detect_distress_level(raw_input) != "none":
        return "supportive"
    return None


def detect_distress_level(raw_input: str) -> str:
    """Classify the distress intensity carried by the current raw input."""
    text = str(raw_input).strip().lower()
    if any(token in text for token in _HIGH_RISK_TOKENS):
        return "high_risk"
    if any(token in text for token in _SUPPORTIVE_TOKENS):
        return "normal"
    return "none"


def detect_continue_chat_intent(raw_input: str) -> str:
    """Classify whether an ongoing companion turn strongly continues chat."""
    text = str(raw_input).strip().lower()
    if any(token in text for token in _RETURN_TOKENS):
        return "none"
    if any(token in text for token in _CONTROL_TOKENS):
        return "none"
    if detect_distress_level(raw_input) != "none":
        return "strong"
    if any(token in text for token in _TOOL_TOKENS):
        return "weak"
    if any(token in text for token in _IDENTITY_TOKENS):
        return "weak"
    if text in _SHORT_CONFIRMATION_TOKENS:
        return "weak"
    if text in _SHORT_CONTEXTUAL_FRAGMENT_TOKENS:
        return "weak"
    if any(token in text for token in _CLOSED_CONFIRMATION_TOKENS):
        return "weak"
    if any(token in text for token in _STRONG_TOKENS):
        return "strong"
    if any(token in text for token in _DEFER_CHAT_TOKENS):
        return "strong"
    if any(token in text for token in _OPEN_QUESTION_TOKENS):
        return "strong"
    if _looks_like_open_question(text):
        return "strong"
    if any(token in text for token in _OPEN_TOPIC_TOKENS):
        return "strong"
    if any(token in text for token in _POLITE_CLOSE_TOKENS):
        return "weak"
    if text:
        return "weak"
    return "weak"


def looks_like_companion_chat(raw_input: str) -> bool:
    """Return whether the input resembles chat that companion should take over."""
    text = str(raw_input).strip().lower()
    if not text:
        return False
    if any(token in text for token in _RETURN_TOKENS):
        return False
    if any(token in text for token in _CONTROL_TOKENS):
        return False
    if any(token in text for token in _TOOL_TOKENS):
        return False
    if detect_distress_level(raw_input) != "none":
        return True
    if detect_continue_chat_intent(raw_input) == "strong":
        return True
    if any(token in text for token in _GREETING_TOKENS):
        return True
    if any(token in text for token in _POLITE_CLOSE_TOKENS):
        return True
    if any(token in text for token in _IDENTITY_TOKENS):
        return True
    if any(token in text for token in _STRONG_TOKENS):
        return True
    if any(token in text for token in _DEFER_CHAT_TOKENS):
        return True
    if any(token in text for token in _OPEN_QUESTION_TOKENS):
        return True
    if any(token in text for token in _OPEN_TOPIC_TOKENS):
        return True
    return False


def has_strong_continue_chat_signal(raw_input: str) -> bool:
    """Return whether the raw input itself clearly asks to keep chatting."""
    if detect_distress_level(raw_input) != "none":
        return True
    return detect_continue_chat_intent(raw_input) == "strong"


def is_explicit_return_to_quiz(raw_input: str) -> bool:
    """Return whether the user explicitly asked to return to the quiz."""
    text = str(raw_input).strip().lower()
    return any(token in text for token in _RETURN_TOKENS)


def _looks_like_open_question(text: str) -> bool:
    if not text:
        return False
    if any(token in text for token in _CLOSED_CONFIRMATION_TOKENS):
        return False
    if any(token in text for token in _OPEN_INTERROGATIVE_TOKENS):
        return True
    return "?" in text or "？" in text
