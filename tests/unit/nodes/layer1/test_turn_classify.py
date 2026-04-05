"""Tests for turn classification."""

from somni_graph_quiz.contracts.graph_state import create_graph_state
from somni_graph_quiz.contracts.turn_input import TurnInput
from somni_graph_quiz.llm.client import FakeLLMProvider
from somni_graph_quiz.nodes.layer1.turn_classify import TurnClassifyNode


def test_turn_classify_marks_control_as_non_content(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-1",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-1",
            channel="grpc",
            input_mode="message",
            raw_input="下一题",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "non_content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "navigate_next"
    assert result["state_patch"]["turn"]["normalized_input"] == "下一题"


def test_turn_classify_marks_numeric_input_as_content(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-1",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="en",
    )

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-1",
            channel="grpc",
            input_mode="message",
            raw_input="22",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "none"


def test_turn_classify_uses_llm_when_available(question_catalog: dict) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "content",
              "normalized_input": "7点起",
              "reason": "partial completion of sleep schedule"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="session-llm",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-llm",
            channel="grpc",
            input_mode="message",
            raw_input="7点起",
            language_preference="zh-CN",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "none"
    assert result["state_patch"]["turn"]["normalized_input"] == "7点起"
    assert len(provider.calls) == 1


def test_turn_classify_falls_back_to_rules_when_llm_output_is_invalid(question_catalog: dict) -> None:
    provider = FakeLLMProvider(
        responses={"layer1/turn_classify.md": "not json"}
    )
    graph_state = create_graph_state(
        session_id="session-fallback",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-fallback",
            channel="grpc",
            input_mode="message",
            raw_input="下一题",
            language_preference="zh-CN",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "non_content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "navigate_next"
    assert len(provider.calls) == 1


def test_turn_classify_marks_identity_question_as_non_content(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-identity",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-identity",
            channel="grpc",
            input_mode="message",
            raw_input="你是谁",
            language_preference="zh-CN",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "non_content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "identity"


def test_turn_classify_bypasses_llm_for_direct_answer(question_catalog: dict) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "non_content",
              "normalized_input": "should-not-be-used"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="session-direct-answer",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-direct-answer",
            channel="grpc",
            input_mode="direct_answer",
            raw_input="23:00-07:00",
            direct_answer_payload={
                "question_id": "question-02",
                "selected_options": [],
                "input_value": "23:00-07:00",
            },
            language_preference="zh-CN",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "none"
    assert result["state_patch"]["turn"]["normalized_input"] == "23:00-07:00"
    assert provider.calls == []


def test_turn_classify_marks_view_all_as_non_content_intent(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-view",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-view",
            channel="grpc",
            input_mode="message",
            raw_input="查看记录",
            language_preference="zh-CN",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "non_content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "view_all"


def test_turn_classify_marks_greeting_as_pullback_chat(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-greeting",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-greeting",
            channel="grpc",
            input_mode="message",
            raw_input="你好",
            language_preference="zh-CN",
        ),
    )

    assert result["state_patch"]["turn"]["main_branch"] == "non_content"
    assert result["state_patch"]["turn"]["non_content_intent"] == "pullback_chat"
