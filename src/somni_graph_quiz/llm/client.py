"""LLM client abstractions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeLLMProvider:
    """Simple provider used by tests and local development."""

    responses: dict[str, str]
    calls: list[tuple[str, str]] = field(default_factory=list)

    def generate(self, prompt_key: str, prompt_text: str) -> str:
        """Return a predefined response and store the call."""
        self.calls.append((prompt_key, prompt_text))
        try:
            return self.responses[prompt_key]
        except KeyError as exc:
            raise ValueError(f"No fake response configured for {prompt_key!r}") from exc


@dataclass
class RealLLMProvider:
    """Thin wrapper around the configured remote chat model."""

    base_url: str
    api_key: str
    model: str
    temperature: float
    timeout: int
    reasoning_effort: str
    _client: Any | None = field(default=None, init=False, repr=False)

    def generate(self, prompt_key: str, prompt_text: str) -> str:
        """Generate text from the configured remote model."""
        _ = prompt_key
        client = self._get_client()
        response = client.invoke(prompt_text)
        content = getattr(response, "content", response)
        if isinstance(content, list):
            return "".join(
                chunk.get("text", "") if isinstance(chunk, dict) else str(chunk)
                for chunk in content
            )
        return str(content)

    def _get_client(self) -> Any:
        if self._client is None:
            from langchain_openai import ChatOpenAI

            kwargs: dict[str, Any] = {
                "model": self.model,
                "api_key": self.api_key,
                "base_url": self.base_url,
                "temperature": self.temperature,
                "timeout": self.timeout,
            }
            if self.reasoning_effort:
                kwargs["reasoning_effort"] = self.reasoning_effort
            self._client = ChatOpenAI(**kwargs)
        return self._client
