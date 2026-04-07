"""Tests for the real LLM client wrapper."""

from __future__ import annotations

import httpx
import langchain_openai

from somni_graph_quiz.llm.client import RealLLMProvider


def test_real_llm_provider_builds_chat_client_without_env_proxy(monkeypatch) -> None:
    captured_kwargs: dict[str, object] = {}

    class _FakeChatOpenAI:
        def __init__(self, **kwargs) -> None:
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", _FakeChatOpenAI)

    provider = RealLLMProvider(
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        api_key="test-key",
        model="doubao-seed-2-0-mini-260215",
        temperature=0.2,
        timeout=30,
        reasoning_effort="minimal",
    )

    provider._get_client()

    http_client = captured_kwargs["http_client"]
    http_async_client = captured_kwargs["http_async_client"]
    assert isinstance(http_client, httpx.Client)
    assert isinstance(http_async_client, httpx.AsyncClient)
    assert getattr(http_client, "_trust_env") is False
    assert getattr(http_async_client, "_trust_env") is False
