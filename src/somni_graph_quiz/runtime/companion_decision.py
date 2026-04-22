"""LLM-first companion decision helper."""

from __future__ import annotations

from pathlib import Path

from somni_graph_quiz.contracts.question_catalog import get_question
from somni_graph_quiz.llm.invocation import invoke_json
from somni_graph_quiz.llm.prompt_loader import PromptLoader


_PROMPTS_ROOT = Path(__file__).resolve().parents[3] / "prompts"
_VALID_ACTIONS = {"enter", "stay", "exit", "none"}
_VALID_MODES = {"smalltalk", "supportive", "none"}
_VALID_OVERRIDES = {"NOT_RECORDED", "none"}
_VALID_CONTINUE_CHAT_INTENTS = {"strong", "weak", "none"}


class CompanionDecisionEngine:
    """Resolve companion state decisions via LLM when available."""

    def __init__(self, prompt_loader: PromptLoader | None = None) -> None:
        self._prompt_loader = prompt_loader or PromptLoader(_PROMPTS_ROOT)

    def decide(
        self,
        *,
        graph_state: dict,
        raw_input: str,
        branch_result: dict,
        companion_context: dict,
        companion_recent_turns: list[dict],
    ) -> dict | None:
        runtime = graph_state.get("runtime", {})
        provider = runtime.get("llm_provider")
        if not runtime.get("llm_available", False) or provider is None:
            return None

        payload = {
            "raw_input": raw_input,
            "response_language": graph_state.get("turn", {}).get("response_language", "zh-CN"),
            "main_branch": graph_state.get("turn", {}).get("main_branch", "content"),
            "non_content_intent": graph_state.get("turn", {}).get("non_content_intent", "none"),
            "applied_question_ids": list(branch_result.get("applied_question_ids", [])),
            "modified_question_ids": list(branch_result.get("modified_question_ids", [])),
            "partial_question_ids": list(branch_result.get("partial_question_ids", [])),
            "current_question": self._current_question_summary(graph_state),
            "companion_context": dict(companion_context),
            "companion_recent_turns": list(companion_recent_turns),
        }
        try:
            prompt_text = self._prompt_loader.render("layer1/companion_decision.md", payload)
            output = invoke_json(
                provider,
                prompt_key="layer1/companion_decision.md",
                prompt_text=prompt_text,
            )
        except Exception:
            return None
        return self._validate(output)

    def _current_question_summary(self, graph_state: dict) -> dict | None:
        question_id = graph_state.get("session_memory", {}).get("current_question_id")
        question = get_question(graph_state.get("question_catalog", {}), question_id)
        if not question:
            return None
        return {
            "question_id": question.get("question_id"),
            "title": question.get("title"),
            "input_type": question.get("input_type"),
        }

    def _validate(self, output: dict) -> dict | None:
        action = str(output.get("companion_action", "")).strip()
        mode = str(output.get("companion_mode", "")).strip()
        answer_status_override = str(output.get("answer_status_override", "")).strip()
        continue_chat_intent = str(output.get("continue_chat_intent", "")).strip() or "none"
        reason = output.get("reason")

        if action not in _VALID_ACTIONS:
            return None
        if mode not in _VALID_MODES:
            return None
        if answer_status_override not in _VALID_OVERRIDES:
            return None
        if continue_chat_intent not in _VALID_CONTINUE_CHAT_INTENTS:
            return None
        if not isinstance(reason, str) or not reason.strip():
            return None

        if action in {"enter", "stay"} and mode == "none":
            return None
        if action in {"exit", "none"} and mode != "none":
            return None
        if action == "none" and answer_status_override != "none":
            return None

        return {
            "companion_action": action,
            "companion_mode": None if mode == "none" else mode,
            "continue_chat_intent": continue_chat_intent,
            "answer_status_override": None if answer_status_override == "none" else answer_status_override,
            "reason": reason.strip(),
        }
