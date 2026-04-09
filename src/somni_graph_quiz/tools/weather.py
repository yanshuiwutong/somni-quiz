"""Weather tool abstraction and default provider."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from urllib.parse import quote
from urllib.request import urlopen


_WEATHER_QUERY_HINTS = (
    "天气",
    "气温",
    "温度",
    "下雨",
    "雨吗",
)
_CITY_TRAILING_TOKENS = ("今天", "今日", "现在", "当前", "这会", "的")
_COMMON_CITY_REPLIES = {
    "北京",
    "上海",
    "天津",
    "重庆",
    "香港",
    "澳门",
}
_NON_CITY_REPLY_TOKENS = (
    "你好",
    "您好",
    "谢谢",
    "哈哈",
    "下一题",
    "上一题",
    "跳过",
    "撤回",
    "查看",
    "天气",
    "气温",
    "温度",
)


def looks_like_weather_query(text: str) -> bool:
    """Return True when the input is explicitly asking for weather."""
    normalized = str(text).strip()
    if not normalized:
        return False
    if "天气" in normalized:
        return True
    return any(token in normalized for token in _WEATHER_QUERY_HINTS[1:])


def extract_weather_city(text: str) -> str:
    """Extract an explicit city from a weather query when present."""
    normalized = str(text).strip()
    if not normalized:
        return ""
    for marker in ("天气", "气温", "温度", "会下雨", "下雨", "雨吗"):
        if marker not in normalized:
            continue
        prefix = normalized.split(marker, 1)[0].strip(" ，,。？?！!：:")
        for token in _CITY_TRAILING_TOKENS:
            if prefix.endswith(token):
                prefix = prefix[: -len(token)].strip(" ，,。？?！!：:")
        prefix = re.sub(r"(请问|帮我|查下|查一?下|看看|想问下)$", "", prefix).strip()
        if 1 < len(prefix) <= 16:
            return prefix
    return ""


def looks_like_weather_city_followup(text: str) -> bool:
    """Return True when a short follow-up likely only contains a city name."""
    normalized = str(text).strip().strip("，,。！？?!：:；;")
    if not normalized or looks_like_weather_query(normalized):
        return False
    lowered = normalized.lower()
    if any(token in normalized for token in _NON_CITY_REPLY_TOKENS):
        return False
    if any(token in lowered for token in ("hello", "hi", "thanks", "thank", "next", "previous", "skip", "undo")):
        return False
    if re.search(r"\d", normalized):
        return False
    if normalized in _COMMON_CITY_REPLIES:
        return True
    if re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,31}", normalized):
        return True
    if normalized.endswith(("市", "区", "县", "州", "镇")):
        return True
    return bool(re.fullmatch(r"[\u4e00-\u9fff]{2,5}", normalized))


@dataclass(slots=True)
class WttrInWeatherProvider:
    """Fetch current weather from wttr.in."""

    timeout: int = 10

    def fetch_current_weather(self, city: str) -> dict:
        query_city = str(city).strip()
        if not query_city:
            raise ValueError("city is required")
        url = f"https://wttr.in/{quote(query_city)}?format=j1"
        with urlopen(url, timeout=self.timeout) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        current = (payload.get("current_condition") or [{}])[0]
        weather_desc = (current.get("weatherDesc") or [{}])[0].get("value", "")
        temp_c = current.get("temp_C", "")
        feels_like = current.get("FeelsLikeC", "")
        summary_tokens = [token for token in (weather_desc, f"{temp_c}C" if temp_c else "") if token]
        if feels_like:
            summary_tokens.append(f"体感 {feels_like}C")
        summary = "，".join(summary_tokens).strip("，")
        if not summary:
            raise LookupError(f"empty weather result for {query_city}")
        return {
            "ok": True,
            "city": query_city,
            "summary": summary,
            "provider": "wttr.in",
        }


@dataclass(slots=True)
class WeatherTool:
    """Stable internal weather tool interface."""

    provider: object

    def get_current_weather(self, city: str) -> dict:
        normalized_city = str(city).strip()
        if not normalized_city:
            return {
                "ok": False,
                "city": "",
                "summary": "",
                "error_code": "missing_city",
            }
        try:
            result = self.provider.fetch_current_weather(normalized_city)
        except Exception:
            return {
                "ok": False,
                "city": normalized_city,
                "summary": "",
                "error_code": "provider_error",
            }
        normalized = {
            "ok": bool(result.get("ok", True)),
            "city": str(result.get("city", normalized_city)).strip() or normalized_city,
            "summary": str(result.get("summary", "")).strip(),
            "provider": str(result.get("provider", "")).strip(),
        }
        if normalized["ok"] and normalized["summary"]:
            return normalized
        return {
            "ok": False,
            "city": normalized["city"],
            "summary": normalized["summary"],
            "error_code": "empty_result",
            "provider": normalized["provider"],
        }
