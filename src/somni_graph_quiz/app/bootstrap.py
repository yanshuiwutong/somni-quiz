"""Application bootstrap entrypoints."""

from __future__ import annotations

from somni_graph_quiz.app.settings import GraphQuizSettings, get_settings
from somni_graph_quiz.llm.client import RealLLMProvider


def build_llm_provider(settings: GraphQuizSettings) -> RealLLMProvider | None:
    """Build the configured remote LLM provider, if credentials are ready."""
    if not settings.llm_ready:
        return None
    return RealLLMProvider(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout,
        reasoning_effort=settings.llm_reasoning_effort,
    )


def apply_runtime_dependencies(
    graph_state: dict,
    *,
    settings: GraphQuizSettings | None = None,
) -> None:
    """Attach configured runtime dependencies onto a graph state."""
    runtime_settings = settings or get_settings()
    provider = build_llm_provider(runtime_settings)
    graph_state["runtime"]["llm_provider"] = provider
    graph_state["runtime"]["llm_available"] = provider is not None
