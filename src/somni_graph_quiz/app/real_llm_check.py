"""Explicit diagnostics for the configured real remote LLM."""

from __future__ import annotations

import time

from somni_graph_quiz.adapters.streamlit.mapper import map_streamlit_questionnaire_to_catalog
from somni_graph_quiz.app.bootstrap import build_llm_provider
from somni_graph_quiz.app.settings import GraphQuizSettings, get_settings
from somni_graph_quiz.app.streamlit_app import build_default_questionnaire


def _business9_catalog() -> dict:
    return map_streamlit_questionnaire_to_catalog(build_default_questionnaire())


def run_real_llm_check(settings: GraphQuizSettings | None = None) -> dict[str, object]:
    """Run a minimal real-provider call and return structured diagnostics."""
    runtime_settings = settings or get_settings()
    questionnaire_catalog = _business9_catalog()
    missing_keys = runtime_settings.missing_llm_config_keys
    if missing_keys:
        return {
            "ready": False,
            "success": False,
            "questionnaire": "business9",
            "question_count": len(questionnaire_catalog["question_order"]),
            "provider_model": runtime_settings.llm_model,
            "missing_keys": missing_keys,
            "latency_ms": None,
            "response_preview": "",
            "error": "missing_configuration",
            "error_type": None,
        }

    provider = build_llm_provider(runtime_settings)
    if provider is None:
        return {
            "ready": True,
            "success": False,
            "questionnaire": "business9",
            "question_count": len(questionnaire_catalog["question_order"]),
            "provider_model": runtime_settings.llm_model,
            "missing_keys": [],
            "latency_ms": None,
            "response_preview": "",
            "error": "provider_unavailable",
            "error_type": None,
        }

    start = time.monotonic()
    try:
        response = provider.generate(
            "real_provider_check",
            "Reply with a very short health check acknowledgement.",
        )
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        return {
            "ready": True,
            "success": True,
            "questionnaire": "business9",
            "question_count": len(questionnaire_catalog["question_order"]),
            "provider_model": runtime_settings.llm_model,
            "missing_keys": [],
            "latency_ms": latency_ms,
            "response_preview": str(response).strip()[:200],
            "error": None,
            "error_type": None,
        }
    except Exception as exc:
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        return {
            "ready": True,
            "success": False,
            "questionnaire": "business9",
            "question_count": len(questionnaire_catalog["question_order"]),
            "provider_model": runtime_settings.llm_model,
            "missing_keys": [],
            "latency_ms": latency_ms,
            "response_preview": "",
            "error": str(exc),
            "error_type": type(exc).__name__,
        }
