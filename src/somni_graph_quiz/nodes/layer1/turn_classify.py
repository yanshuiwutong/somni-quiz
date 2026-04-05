"""Turn classification node."""

from __future__ import annotations

from pathlib import Path

from somni_graph_quiz.llm.invocation import invoke_json
from somni_graph_quiz.llm.prompt_loader import PromptLoader
from somni_graph_quiz.runtime.context_builder import build_llm_memory_view


_PROMPTS_ROOT = Path(__file__).resolve().parents[4] / "prompts"


class TurnClassifyNode:
    """Classify a turn into the top-level branch."""

    NON_CONTENT_INTENTS = {
        "identity",
        "pullback_chat",
        "view_all",
        "view_previous",
        "view_current",
        "view_next",
        "navigate_previous",
        "navigate_next",
        "skip",
        "undo",
        "modify_previous",
        "none",
    }

    def __init__(self, prompt_loader: PromptLoader | None = None) -> None:
        self._prompt_loader = prompt_loader or PromptLoader(_PROMPTS_ROOT)

    def run(self, graph_state: dict, turn_input: object) -> dict:
        raw_input = getattr(turn_input, "raw_input", "")
        input_mode = getattr(turn_input, "input_mode", "message")
        response_language = (
            getattr(turn_input, "language_preference", None)
            or graph_state["session"]["language_preference"]
        )
        if input_mode == "direct_answer":
            normalized_input = raw_input.strip()
            return {
                "state_patch": {
                    "turn": {
                        "raw_input": raw_input,
                        "input_mode": input_mode,
                        "normalized_input": normalized_input,
                        "main_branch": "content",
                        "non_content_intent": "none",
                        "response_language": response_language,
                    }
                },
                "branch_decision": {"main_branch": "content", "non_content_intent": "none"},
                "artifacts": {},
                "terminal_signal": None,
                "fallback_used": False,
            }
        llm_output = self._try_llm(graph_state, turn_input, response_language)
        if llm_output is not None:
            normalized_input = str(llm_output.get("normalized_input", raw_input.strip()))
            main_branch = llm_output["main_branch"]
            non_content_intent = self._normalize_non_content_intent(
                main_branch=main_branch,
                candidate=llm_output.get("non_content_intent"),
                normalized_input=normalized_input,
            )
            return {
                "state_patch": {
                    "turn": {
                        "raw_input": raw_input,
                        "input_mode": input_mode,
                        "normalized_input": normalized_input,
                        "main_branch": main_branch,
                        "non_content_intent": non_content_intent,
                        "response_language": response_language,
                    }
                },
                "branch_decision": {
                    "main_branch": main_branch,
                    "non_content_intent": non_content_intent,
                },
                "artifacts": {},
                "terminal_signal": None,
                "fallback_used": False,
            }

        normalized_input = raw_input.strip()
        main_branch, non_content_intent = self._classify(normalized_input)
        return {
            "state_patch": {
                "turn": {
                    "raw_input": raw_input,
                    "input_mode": input_mode,
                    "normalized_input": normalized_input,
                    "main_branch": main_branch,
                    "non_content_intent": non_content_intent,
                    "response_language": response_language,
                }
            },
            "branch_decision": {
                "main_branch": main_branch,
                "non_content_intent": non_content_intent,
            },
            "artifacts": {},
            "terminal_signal": None,
            "fallback_used": True,
        }

    def _try_llm(self, graph_state: dict, turn_input: object, response_language: str) -> dict | None:
        runtime = graph_state["runtime"]
        provider = runtime.get("llm_provider")
        if not runtime.get("llm_available", True) or provider is None:
            return None
        payload = {
            "raw_input": getattr(turn_input, "raw_input", ""),
            "response_language": response_language,
            "memory_view": build_llm_memory_view(graph_state),
        }
        try:
            prompt_text = self._prompt_loader.render("layer1/turn_classify.md", payload)
            output = invoke_json(
                provider,
                prompt_key="layer1/turn_classify.md",
                prompt_text=prompt_text,
            )
        except Exception:
            return None
        if output.get("main_branch") not in {"content", "non_content"}:
            return None
        return output

    def _classify(self, normalized_input: str) -> tuple[str, str]:
        lowered = normalized_input.lower()
        if not normalized_input:
            return "non_content", "pullback_chat"
        if "查看上一题记录" in normalized_input:
            return "non_content", "view_previous"
        if "查看当前题记录" in normalized_input or "查看这题记录" in normalized_input:
            return "non_content", "view_current"
        if "查看下一题" in normalized_input:
            return "non_content", "view_next"
        if "改上一题" in normalized_input or "修改上一题" in normalized_input or "previous answer" in lowered:
            return "non_content", "modify_previous"
        if "上一题" in normalized_input or "previous question" in lowered:
            return "non_content", "navigate_previous"
        if "下一题" in normalized_input or "next" in lowered:
            return "non_content", "navigate_next"
        if "跳过" in normalized_input or "skip" in lowered:
            return "non_content", "skip"
        if "撤回" in normalized_input or "undo" in lowered:
            return "non_content", "undo"
        if "查看" in normalized_input or "view" in lowered:
            return "non_content", "view_all"
        if "你是谁" in normalized_input:
            return "non_content", "identity"
        if any(keyword in lowered for keyword in ("你好", "谢谢", "哈哈", "thank", "hi", "hello")):
            return "non_content", "pullback_chat"
        return "content", "none"

    def _normalize_non_content_intent(
        self,
        *,
        main_branch: str,
        candidate: object,
        normalized_input: str,
    ) -> str:
        if main_branch != "non_content":
            return "none"
        if isinstance(candidate, str) and candidate in self.NON_CONTENT_INTENTS and candidate != "none":
            return candidate
        _, fallback_intent = self._classify(normalized_input)
        return fallback_intent if fallback_intent != "none" else "pullback_chat"
