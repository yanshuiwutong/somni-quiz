"""Final attribution node."""

from __future__ import annotations

import re
from pathlib import Path

from somni_graph_quiz.llm.invocation import invoke_json
from somni_graph_quiz.llm.prompt_loader import PromptLoader


_PROMPTS_ROOT = Path(__file__).resolve().parents[5] / "prompts"
_TIME_HOUR_PATTERN = re.compile(r"(?P<hour>\d{1,2})\s*(?:[:：]\d{1,2})?\s*(?:点|时)?")
_RELAXED_CONTEXT_TOKENS = ("自由", "自然", "周末", "休息日", "完全自由安排")
_CHANGE_REQUEST_TOKENS = ("改", "改成", "改为", "更改", "改到")


class FinalAttributionNode:
    """Resolve winner within a fixed candidate set."""

    def __init__(self, prompt_loader: PromptLoader | None = None) -> None:
        self._prompt_loader = prompt_loader or PromptLoader(_PROMPTS_ROOT)

    def run(self, graph_state: dict, content_unit: dict) -> dict:
        candidate_question_ids = list(content_unit["candidate_question_ids"])
        if content_unit["winner_question_id"] in candidate_question_ids:
            return {**content_unit, "needs_attribution": False}
        llm_output = self._try_llm(graph_state, content_unit)
        if llm_output is not None:
            winner_question_id = llm_output.get("winner_question_id")
            needs_clarification = bool(llm_output.get("needs_clarification", False))
            if winner_question_id in candidate_question_ids:
                return {
                    **content_unit,
                    "winner_question_id": winner_question_id,
                    "needs_attribution": False,
                    "needs_clarification": needs_clarification,
                }
            if needs_clarification:
                return {
                    **content_unit,
                    "winner_question_id": None,
                    "needs_attribution": False,
                    "needs_clarification": True,
                }
        return self._fallback(graph_state, content_unit)

    def _try_llm(self, graph_state: dict, content_unit: dict) -> dict | None:
        runtime = graph_state["runtime"]
        provider = runtime.get("llm_provider")
        if not runtime.get("llm_available", True) or provider is None:
            return None
        payload = {
            "content_unit": content_unit,
            "memory_view": {
                "current_question_id": graph_state["session_memory"]["current_question_id"],
                "pending_modify_context": graph_state["session_memory"]["pending_modify_context"],
                "partial_question_ids": graph_state["session_memory"]["partial_question_ids"],
                "recent_turns": graph_state["session_memory"]["recent_turns"][-5:],
            },
            "question_catalog": graph_state["question_catalog"],
        }
        try:
            prompt_text = self._prompt_loader.render("layer2/final_attribution.md", payload)
            return invoke_json(
                provider,
                prompt_key="layer2/final_attribution.md",
                prompt_text=prompt_text,
            )
        except Exception:
            return None

    def _fallback(self, graph_state: dict, content_unit: dict) -> dict:
        candidate_question_ids = list(content_unit["candidate_question_ids"])
        unit_text = str(content_unit.get("unit_text", ""))
        current_question_id = graph_state["session_memory"]["current_question_id"]
        if content_unit["winner_question_id"] in candidate_question_ids:
            return content_unit
        latest_candidate = self._latest_answered_candidate(graph_state, candidate_question_ids)
        if self._looks_like_change_request(unit_text) and latest_candidate is not None:
            return {
                **content_unit,
                "winner_question_id": latest_candidate,
                "needs_attribution": False,
                "needs_clarification": False,
            }
        if {"question-02", "question-03", "question-04"}.issubset(set(candidate_question_ids)):
            relaxed_target = self._resolve_relaxed_target(graph_state, unit_text)
            if relaxed_target in candidate_question_ids:
                return {
                    **content_unit,
                    "winner_question_id": relaxed_target,
                    "needs_attribution": False,
                    "needs_clarification": False,
                }
            return {
                **content_unit,
                "winner_question_id": "question-02",
                "needs_attribution": False,
                "needs_clarification": False,
            }
        if "question-02" in candidate_question_ids and ("睡" in unit_text or "起" in unit_text):
            return {
                **content_unit,
                "winner_question_id": "question-02",
                "needs_attribution": False,
                "needs_clarification": False,
            }
        if current_question_id in candidate_question_ids:
            winner = current_question_id
        else:
            winner = "question-02" if "question-02" in candidate_question_ids else (
                candidate_question_ids[0] if candidate_question_ids else None
            )
        return {
            **content_unit,
            "winner_question_id": winner,
            "needs_attribution": False,
            "needs_clarification": winner is None,
        }

    def _latest_answered_candidate(self, graph_state: dict, candidate_question_ids: list[str]) -> str | None:
        session_memory = graph_state["session_memory"]
        for turn in reversed(session_memory.get("recent_turns", [])):
            for key in ("modified_question_ids", "recorded_question_ids"):
                for question_id in reversed(turn.get(key, [])):
                    if question_id in candidate_question_ids:
                        return question_id
        for question_id in reversed(session_memory.get("answered_question_ids", [])):
            if question_id in candidate_question_ids:
                return question_id
        return None

    def _looks_like_change_request(self, unit_text: str) -> bool:
        return any(token in unit_text for token in _CHANGE_REQUEST_TOKENS)

    def _resolve_relaxed_target(self, graph_state: dict, unit_text: str) -> str | None:
        current_question_id = graph_state["session_memory"]["current_question_id"]
        pending_modify_context = graph_state["session_memory"]["pending_modify_context"] or {}
        modify_target = pending_modify_context.get("question_id")
        has_relaxed_context = (
            current_question_id in {"question-03", "question-04"}
            or modify_target in {"question-03", "question-04"}
            or any(token in unit_text for token in _RELAXED_CONTEXT_TOKENS)
        )
        if not has_relaxed_context:
            return None
        if current_question_id in {"question-03", "question-04"}:
            return current_question_id
        if modify_target in {"question-03", "question-04"}:
            return modify_target
        if self._looks_like_wake_text(unit_text):
            return "question-04"
        if self._looks_like_sleep_text(unit_text):
            return "question-03"
        hour = self._extract_hour(unit_text)
        if hour is None:
            return None
        if 4 <= hour <= 11:
            return "question-04"
        return "question-03"

    def _looks_like_wake_text(self, unit_text: str) -> bool:
        return any(token in unit_text for token in ("起床", "醒", "早上", "早晨"))

    def _looks_like_sleep_text(self, unit_text: str) -> bool:
        return any(token in unit_text for token in ("睡", "入睡", "晚上", "夜里"))

    def _extract_hour(self, unit_text: str) -> int | None:
        match = _TIME_HOUR_PATTERN.search(unit_text)
        if not match:
            return None
        return int(match.group("hour")) % 24
