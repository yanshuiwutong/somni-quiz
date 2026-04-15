"""LLM client abstractions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx


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
    _http_client: httpx.Client | None = field(default=None, init=False, repr=False)

    def generate(self, prompt_key: str, prompt_text: str) -> str:
        """Generate text from the configured remote model."""
        _ = prompt_key
        response = self._get_http_client().post(
            self._chat_completions_url(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=self._build_payload(prompt_text),
        )
        response.raise_for_status()
        return self._extract_content(response.json())

    def _get_http_client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(timeout=self.timeout, trust_env=False)
        return self._http_client

    def _chat_completions_url(self) -> str:
        base_url = self.base_url.rstrip("/")
        if base_url.endswith("/chat/completions"):
            return base_url
        return f"{base_url}/chat/completions"

    def _build_payload(self, prompt_text: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt_text}],
            "temperature": self.temperature,
        }
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        return payload

    def _extract_content(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("LLM response missing choices")

        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, list):
            return "".join(
                chunk.get("text", "") if isinstance(chunk, dict) else str(chunk)
                for chunk in content
            )
        if content is None:
            return ""
        return str(content)
