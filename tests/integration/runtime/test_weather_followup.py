"""Runtime integration tests for weather follow-up behavior."""

from somni_graph_quiz.contracts.graph_state import create_graph_state
from somni_graph_quiz.contracts.turn_input import TurnInput
from somni_graph_quiz.runtime.engine import GraphRuntimeEngine


def test_engine_weather_query_without_default_city_asks_city_then_accepts_city_followup(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-weather-followup",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )

    class _WeatherTool:
        def get_current_weather(self, city: str) -> dict:
            return {"ok": True, "city": city, "summary": "晴，22C"}

    graph_state["runtime"]["weather_tool"] = _WeatherTool()
    graph_state["runtime"]["llm_provider"] = None
    graph_state["runtime"]["llm_available"] = False
    engine = GraphRuntimeEngine()

    first = engine.run_turn(
        graph_state,
        TurnInput(
            session_id="session-weather-followup",
            channel="grpc",
            input_mode="message",
            raw_input="今天天气怎么样",
            language_preference="zh-CN",
        ),
    )

    assert first["answer_record"]["answers"] == []
    assert first["pending_question"]["question_id"] == "question-01"
    assert "城市" in first["assistant_message"]
    assert first["updated_graph_state"]["session_memory"]["pending_weather_query"] == {
        "waiting_for_city": True,
        "source": "weather_query",
    }

    second = engine.run_turn(
        first["updated_graph_state"],
        TurnInput(
            session_id="session-weather-followup",
            channel="grpc",
            input_mode="message",
            raw_input="北京",
            language_preference="zh-CN",
        ),
    )

    assert second["answer_record"]["answers"] == []
    assert second["pending_question"]["question_id"] == "question-01"
    assert "北京" in second["assistant_message"]
    assert second["progress_percent"] == 0.0
    assert second["updated_graph_state"]["session_memory"]["pending_weather_query"] is None
