"""Tests for companion rule helpers."""

from somni_graph_quiz.runtime.companion_rules import detect_continue_chat_intent


def test_detect_continue_chat_intent_marks_open_question_as_strong() -> None:
    assert detect_continue_chat_intent("那我该怎么办？") == "strong"


def test_detect_continue_chat_intent_does_not_treat_control_question_as_strong() -> None:
    assert detect_continue_chat_intent("下一题是什么？") == "none"


def test_detect_continue_chat_intent_does_not_treat_weather_question_as_strong() -> None:
    assert detect_continue_chat_intent("今天天气怎么样？") == "weak"


def test_detect_continue_chat_intent_does_not_treat_closed_confirmation_as_strong() -> None:
    assert detect_continue_chat_intent("这样对吗？") == "weak"


def test_detect_continue_chat_intent_marks_topic_recommendation_as_strong() -> None:
    assert detect_continue_chat_intent("我想找个海边城市放空两天，你推荐去哪") == "strong"


def test_detect_continue_chat_intent_marks_open_life_topic_without_question_mark_as_strong() -> None:
    assert detect_continue_chat_intent("最近就想找个安静点的地方散散心，顺便吃点好的") == "strong"


def test_detect_continue_chat_intent_marks_open_food_question_as_strong() -> None:
    assert detect_continue_chat_intent("奶茶有什么坏处吗") == "strong"


def test_detect_continue_chat_intent_marks_open_meal_question_as_strong() -> None:
    assert detect_continue_chat_intent("今天中午吃什么，西红柿炒鸡蛋怎么样") == "strong"


def test_detect_continue_chat_intent_treats_short_confirmation_as_weak() -> None:
    assert detect_continue_chat_intent("好的") == "weak"
    assert detect_continue_chat_intent("嗯嗯") == "weak"
    assert detect_continue_chat_intent("可以") == "weak"


def test_detect_continue_chat_intent_treats_short_travel_fragment_as_weak() -> None:
    assert detect_continue_chat_intent("北京") == "weak"
    assert detect_continue_chat_intent("海边") == "weak"
    assert detect_continue_chat_intent("三天") == "weak"
    assert detect_continue_chat_intent("安静点") == "weak"


def test_detect_continue_chat_intent_treats_short_sleep_fragment_as_weak() -> None:
    assert detect_continue_chat_intent("工作忙的时候") == "weak"
    assert detect_continue_chat_intent("一般在晚上") == "weak"


def test_detect_continue_chat_intent_only_marks_explicit_expansion_as_strong() -> None:
    assert detect_continue_chat_intent("为什么会这样") == "strong"
    assert detect_continue_chat_intent("你更推荐哪个") == "strong"
    assert detect_continue_chat_intent("那我该怎么安排") == "strong"


def test_detect_continue_chat_intent_treats_followup_choice_reply_as_weak() -> None:
    assert detect_continue_chat_intent("我选第二个") == "weak"
    assert detect_continue_chat_intent("第二个") == "weak"
