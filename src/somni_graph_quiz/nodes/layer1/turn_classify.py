"""Turn classification node."""

from __future__ import annotations

from pathlib import Path
import re

from somni_graph_quiz.llm.invocation import invoke_json
from somni_graph_quiz.nodes.layer2.content.mapping import map_content_answer
from somni_graph_quiz.nodes.layer2.non_content.control_rules import detect_control_action
from somni_graph_quiz.llm.prompt_loader import PromptLoader
from somni_graph_quiz.runtime.context_builder import build_llm_memory_view
from somni_graph_quiz.tools import looks_like_weather_city_followup, looks_like_weather_query
from somni_graph_quiz.utils.time_parse import parse_schedule_fragment


_PROMPTS_ROOT = Path(__file__).resolve().parents[4] / "prompts"
_NORMALIZE_PATTERN = re.compile(r"[\s,，。；;：:、.!?？“”\"'`~\\-_/]+")
_OPEN_LIFE_TOPIC_TOKENS = (
    "旅游",
    "旅行",
    "景点",
    "去哪玩",
    "去哪里玩",
    "哪里好玩",
    "海边",
    "散散心",
    "放松",
    "住两天",
    "待两天",
    "美食",
    "吃点好的",
    "攻略",
    "路线",
    "推荐",
)
_GREETING_TOKENS = ("你好", "您好", "谢谢", "哈哈", "thank", "hi", "hello")
_REFUSAL_TOKENS = (
    "不做",
    "不想答",
    "不回答",
    "不填",
    "先不说",
    "这个不答",
    "不想做",
)
_SHORT_CONFIRMATION_TOKENS = {
    "是的",
    "好的",
    "好",
    "嗯",
    "嗯嗯",
    "可以",
    "行",
    "对",
    "明白了",
}
_PENDING_NON_CONTENT_INTENT = "pending_non_content"


class TurnClassifyNode:
    """Classify a turn into the top-level branch."""

    NON_CONTENT_INTENTS = {
        _PENDING_NON_CONTENT_INTENT,
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
        if detect_control_action(raw_input) is not None:
            normalized_input = raw_input.strip()
            return {
                "state_patch": {
                    "turn": {
                        "raw_input": raw_input,
                        "input_mode": input_mode,
                        "normalized_input": normalized_input,
                        "main_branch": "non_content",
                        "non_content_intent": _PENDING_NON_CONTENT_INTENT,
                        "response_language": response_language,
                    }
                },
                "branch_decision": {
                    "main_branch": "non_content",
                    "non_content_intent": _PENDING_NON_CONTENT_INTENT,
                },
                "artifacts": {},
                "terminal_signal": None,
                "fallback_used": False,
            }
        if self._should_route_to_pending_weather_followup(graph_state, raw_input):
            normalized_input = raw_input.strip()
            return {
                "state_patch": {
                    "turn": {
                        "raw_input": raw_input,
                        "input_mode": input_mode,
                        "normalized_input": normalized_input,
                        "main_branch": "non_content",
                        "non_content_intent": _PENDING_NON_CONTENT_INTENT,
                        "response_language": response_language,
                    }
                },
                "branch_decision": {
                    "main_branch": "non_content",
                    "non_content_intent": _PENDING_NON_CONTENT_INTENT,
                },
                "artifacts": {},
                "terminal_signal": None,
                "fallback_used": False,
            }
        llm_output = self._try_llm(graph_state, turn_input, response_language)
        if llm_output is not None:
            normalized_input = str(llm_output.get("normalized_input", raw_input.strip()))
            main_branch = llm_output["main_branch"]
            if main_branch == "non_content" and self._has_stable_answer_signal(graph_state, raw_input):
                main_branch = "content"
            elif (
                main_branch == "content"
                and self._looks_like_non_content_signal(normalized_input)
                and not self._has_stable_answer_signal(graph_state, raw_input)
            ):
                main_branch = "non_content"
            non_content_intent = self._normalize_non_content_intent(main_branch=main_branch)
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
        if self._has_stable_answer_signal(graph_state, normalized_input):
            main_branch, non_content_intent = "content", "none"
        else:
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
            "question_catalog_summary": self._build_question_catalog_summary(graph_state["question_catalog"]),
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

    def _build_question_catalog_summary(self, question_catalog: dict) -> list[dict]:
        summary: list[dict] = []
        for question_id in question_catalog["question_order"]:
            question = question_catalog["question_index"][question_id]
            summary.append(
                {
                    "question_id": question_id,
                    "title": question.get("title"),
                    "input_type": question.get("input_type"),
                    "tags": list(question.get("tags", [])),
                    "options": [
                        {
                            "option_id": option.get("option_id"),
                            "label": option.get("label", option.get("option_text", "")),
                        }
                        for option in question.get("options", [])
                    ],
                }
            )
        return summary

    def _classify(self, normalized_input: str) -> tuple[str, str]:
        if not normalized_input:
            return "non_content", _PENDING_NON_CONTENT_INTENT
        if self._looks_like_non_content_signal(normalized_input):
            return "non_content", _PENDING_NON_CONTENT_INTENT
        return "content", "none"

    def _normalize_non_content_intent(self, *, main_branch: str) -> str:
        if main_branch != "non_content":
            return "none"
        return _PENDING_NON_CONTENT_INTENT

    def _should_route_to_pending_weather_followup(self, graph_state: dict, raw_input: str) -> bool:
        pending_weather_query = graph_state.get("session_memory", {}).get("pending_weather_query") or {}
        if not pending_weather_query.get("waiting_for_city"):
            return False
        candidate_text = str(raw_input).strip()
        if not looks_like_weather_city_followup(candidate_text):
            return False
        normalized_input = candidate_text.strip()
        fallback_branch, fallback_intent = self._classify(normalized_input)
        if fallback_branch == "non_content" and fallback_intent != "none":
            return False
        current_question_id = graph_state.get("session_memory", {}).get("current_question_id")
        current_question = graph_state.get("question_catalog", {}).get("question_index", {}).get(current_question_id)
        if (
            current_question
            and str(current_question.get("input_type", "")).lower() != "text"
            and self._looks_like_answer_to_question(current_question, candidate_text)
        ):
            return False
        return True

    def _has_stable_answer_signal(self, graph_state: dict, raw_input: str) -> bool:
        candidate_text = str(raw_input).strip()
        if not candidate_text:
            return False
        if self._looks_like_answer_to_pullback_target(graph_state, candidate_text):
            return True
        current_question_id = graph_state.get("session_memory", {}).get("current_question_id")
        current_question = graph_state.get("question_catalog", {}).get("question_index", {}).get(current_question_id)
        if current_question and self._looks_like_answer_to_question(current_question, candidate_text):
            return True
        for question in graph_state.get("question_catalog", {}).get("question_index", {}).values():
            if self._looks_like_answer_to_question(question, candidate_text):
                return True
        return self._looks_like_catalog_answer(graph_state["question_catalog"], candidate_text)

    def _looks_like_non_content_signal(self, normalized_input: str) -> bool:
        lowered = normalized_input.lower()
        if lowered in _SHORT_CONFIRMATION_TOKENS:
            return True
        if detect_control_action(normalized_input) is not None:
            return True
        if any(token in normalized_input for token in ("下一题", "上一题", "跳过", "撤回", "查看", "改上一题", "修改上一题")):
            return True
        if "你是谁" in normalized_input:
            return True
        if looks_like_weather_query(normalized_input):
            return True
        if any(token in normalized_input for token in _OPEN_LIFE_TOPIC_TOKENS):
            return True
        if any(token in lowered for token in _GREETING_TOKENS):
            return True
        return any(token in normalized_input for token in _REFUSAL_TOKENS)

    def _looks_like_answer_to_pullback_target(self, graph_state: dict, raw_input: str) -> bool:
        question_catalog = graph_state["question_catalog"]
        question_index = question_catalog.get("question_index", {})
        candidate_text = str(raw_input).strip()
        if not candidate_text:
            return False
        for question_id in self._pullback_target_question_ids(graph_state.get("session_memory", {})):
            question = question_index.get(question_id)
            if question and self._looks_like_answer_to_question(question, candidate_text):
                return True
        return False

    def _pullback_target_question_ids(self, session_memory: dict) -> list[str]:
        target_ids: list[str] = []
        clarification_context = session_memory.get("clarification_context") or {}
        clarification_question_id = str(clarification_context.get("question_id") or "")
        current_question_id = str(session_memory.get("current_question_id") or "")
        for question_id in (clarification_question_id, current_question_id):
            if question_id and question_id not in target_ids:
                target_ids.append(question_id)
        return target_ids

    def _looks_like_answer_to_question(self, question: dict, normalized_input: str) -> bool:
        input_type = str(question.get("input_type", "")).lower()
        if input_type == "time_range":
            return bool(parse_schedule_fragment(normalized_input).get("filled_fields"))
        mapped = map_content_answer(question, normalized_input, raw_text=normalized_input)
        if mapped.get("selected_options"):
            return True
        if mapped.get("field_updates"):
            return True
        return False

    def _looks_like_catalog_answer(self, question_catalog: dict, normalized_input: str) -> bool:
        normalized_text = self._normalize_for_overlap(normalized_input)
        if len(normalized_text) < 4:
            return False
        input_ngrams = self._ngrams(normalized_text)
        if len(input_ngrams) < 2:
            return False

        for question in question_catalog.get("question_index", {}).values():
            catalog_text = self._question_catalog_text(question)
            if not catalog_text:
                continue
            if normalized_text in catalog_text or catalog_text in normalized_text:
                return True
            overlap = sum(1 for token in input_ngrams if token in catalog_text)
            if overlap >= 2:
                return True
        return False

    def _question_catalog_text(self, question: dict) -> str:
        parts = [
            str(question.get("title", "")),
            *[str(tag) for tag in question.get("tags", [])],
            *[str(item) for item in question.get("metadata", {}).get("matching_hints", [])],
            *[
                str(option.get("label", option.get("option_text", "")))
                for option in question.get("options", [])
            ],
        ]
        return self._normalize_for_overlap("".join(parts))

    def _normalize_for_overlap(self, value: str) -> str:
        return _NORMALIZE_PATTERN.sub("", value).lower()

    def _ngrams(self, value: str) -> set[str]:
        lengths = (2, 3, 4)
        return {
            value[index : index + size]
            for size in lengths
            for index in range(max(0, len(value) - size + 1))
            if len(value[index : index + size]) == size
        }
