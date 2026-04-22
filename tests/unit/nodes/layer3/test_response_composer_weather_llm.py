"""Weather-specific response composer tests."""

from types import SimpleNamespace

from somni_graph_quiz.llm.client import FakeLLMProvider
from somni_graph_quiz.nodes.layer3.respond import ResponseComposerNode


def test_response_composer_weather_success_uses_llm_when_available() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/response_composer.md": """
            {
              "assistant_message": "Beijing weather today is sunny and 22C. Let's continue with Your age range."
            }
            """
        }
    )
    finalized = SimpleNamespace(
        raw_input="What's the weather today?",
        input_mode="message",
        main_branch="non_content",
        non_content_intent="weather_query",
        turn_outcome="pullback",
        current_question={"question_id": "question-01", "title": "Your age range", "input_type": "radio"},
        next_question={"question_id": "question-01", "title": "Your age range", "input_type": "radio"},
        finalized=False,
        response_language="en",
        response_facts={
            "non_content_mode": "weather",
            "non_content_action": "weather_query",
            "weather_status": "success",
            "weather_city": "Beijing",
            "weather_summary": "sunny, 22C",
            "llm_provider": provider,
            "llm_available": True,
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert message == "Beijing weather today is sunny and 22C. Let's continue with Your age range."
    assert len(provider.calls) == 1


def test_response_composer_weather_missing_city_uses_llm_when_available() -> None:
    provider = FakeLLMProvider(
        responses={
            "layer3/response_composer.md": """
            {
              "assistant_message": "Which city would you like me to check the weather for?"
            }
            """
        }
    )
    finalized = SimpleNamespace(
        raw_input="What's the weather today?",
        input_mode="message",
        main_branch="non_content",
        non_content_intent="weather_query",
        turn_outcome="pullback",
        current_question={"question_id": "question-01", "title": "Your age range", "input_type": "radio"},
        next_question={"question_id": "question-01", "title": "Your age range", "input_type": "radio"},
        finalized=False,
        response_language="en",
        response_facts={
            "non_content_mode": "weather",
            "non_content_action": "weather_query",
            "weather_status": "missing_city",
            "llm_provider": provider,
            "llm_available": True,
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert message == "Which city would you like me to check the weather for?"
    assert len(provider.calls) == 1
