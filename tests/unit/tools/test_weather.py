"""Tests for the weather tool abstraction."""

from somni_graph_quiz.tools.weather import WeatherTool


def test_weather_tool_returns_provider_result() -> None:
    class _Provider:
        def fetch_current_weather(self, city: str) -> dict:
            return {
                "ok": True,
                "city": city,
                "summary": "晴，22C",
                "provider": "fake",
            }

    result = WeatherTool(_Provider()).get_current_weather("北京")

    assert result["ok"] is True
    assert result["city"] == "北京"
    assert result["summary"] == "晴，22C"


def test_weather_tool_normalizes_provider_errors() -> None:
    class _Provider:
        def fetch_current_weather(self, city: str) -> dict:
            raise TimeoutError(f"timeout for {city}")

    result = WeatherTool(_Provider()).get_current_weather("上海")

    assert result["ok"] is False
    assert result["city"] == "上海"
    assert result["error_code"] == "provider_error"
