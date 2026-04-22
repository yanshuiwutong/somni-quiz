"""Tests for the real LLM client wrapper."""

from __future__ import annotations

import json

import httpx

from somni_graph_quiz.llm.client import RealLLMProvider


def test_real_llm_provider_builds_http_client_without_env_proxy() -> None:
    provider = RealLLMProvider(
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        api_key="test-key",
        model="doubao-seed-2-0-mini-260215",
        temperature=0.2,
        timeout=30,
        reasoning_effort="minimal",
    )

    http_client = provider._get_http_client()

    assert isinstance(http_client, httpx.Client)
    assert getattr(http_client, "_trust_env") is False


def test_real_llm_provider_posts_to_normalized_chat_completions_url() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["content_type"] = request.headers["Content-Type"]
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "pong",
                        }
                    }
                ]
            },
        )

    provider = RealLLMProvider(
        base_url="https://api.fullive.xyz/v1",
        api_key="test-key",
        model="gemini-3.1-flash-lite-preview",
        temperature=0.2,
        timeout=30,
        reasoning_effort="minimal",
    )
    provider._http_client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)

    response = provider.generate("real_provider_check", "health check")

    assert response == "pong"
    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.fullive.xyz/v1/chat/completions"
    assert captured["authorization"] == "Bearer test-key"
    assert captured["content_type"] == "application/json"
    assert captured["body"] == {
        "model": "gemini-3.1-flash-lite-preview",
        "messages": [{"role": "user", "content": "health check"}],
        "temperature": 0.2,
        "reasoning_effort": "minimal",
    }


def test_real_llm_provider_accepts_full_chat_completions_base_url() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"text": "hello"},
                                " world",
                            ]
                        }
                    }
                ]
            },
        )

    provider = RealLLMProvider(
        base_url="https://api.fullive.xyz/v1/chat/completions",
        api_key="test-key",
        model="gemini-3.1-flash-lite-preview",
        temperature=0.2,
        timeout=30,
        reasoning_effort="",
    )
    provider._http_client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)

    response = provider.generate("real_provider_check", "health check")

    assert response == "hello world"
    assert captured["url"] == "https://api.fullive.xyz/v1/chat/completions"
