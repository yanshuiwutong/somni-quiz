"""Content understanding node."""

from __future__ import annotations

import re
from pathlib import Path

from somni_graph_quiz.llm.invocation import invoke_json
from somni_graph_quiz.llm.prompt_loader import PromptLoader
from somni_graph_quiz.utils.time_parse import parse_schedule_fragment


_PROMPTS_ROOT = Path(__file__).resolve().parents[5] / "prompts"

_AGE_PATTERN = re.compile(r"(?P<age>\d{1,3})\s*岁")
_AGE_CORRECTION_PATTERN = re.compile(r"(?:不是|改成|改为|改)\s*(?P<age>\d{1,3})")
_RAW_NUMBER_PATTERN = re.compile(r"\b(?P<number>\d{1,3})\b")
_TIME_EXPRESSION_PATTERN = re.compile(
    r"(?:\d{1,2}|十二|十一|十|两|零|一|二|三|四|五|六|七|八|九)"
    r"(?:\s*[:：]\s*\d{1,2})?\s*(?:点|时)"
)
_RELAXED_CONTEXT_TOKENS = ("自由", "自然", "周末", "休息日", "完全自由安排")


class ContentUnderstandNode:
    """Understand content into one or more resolved units."""

    def __init__(self, prompt_loader: PromptLoader | None = None) -> None:
        self._prompt_loader = prompt_loader or PromptLoader(_PROMPTS_ROOT)

    def run(self, graph_state: dict, turn_input: object) -> dict:
        raw_input = getattr(turn_input, "raw_input", "").strip()
        if not raw_input:
            return {
                "content_units": [],
                "clarification_needed": True,
                "clarification_reason": "missing_content",
            }

        direct_answer_payload = getattr(turn_input, "direct_answer_payload", None)
        if direct_answer_payload and direct_answer_payload.get("question_id"):
            return self._rule_understand(graph_state, turn_input, raw_input)

        llm_output = self._try_llm(graph_state, turn_input)
        if llm_output is not None:
            return llm_output
        return self._rule_understand(graph_state, turn_input, raw_input)

    def _try_llm(self, graph_state: dict, turn_input: object) -> dict | None:
        runtime = graph_state["runtime"]
        provider = runtime.get("llm_provider")
        if not runtime.get("llm_available", True) or provider is None:
            return None
        payload = {
            "raw_input": getattr(turn_input, "raw_input", ""),
            "input_mode": getattr(turn_input, "input_mode", "message"),
            "direct_answer_payload": getattr(turn_input, "direct_answer_payload", None),
            "memory_view": self._build_memory_view(graph_state),
            "question_catalog": graph_state["question_catalog"],
        }
        try:
            prompt_text = self._prompt_loader.render("layer2/content_understand.md", payload)
            output = invoke_json(
                provider,
                prompt_key="layer2/content_understand.md",
                prompt_text=prompt_text,
            )
        except Exception:
            return None
        content_units = output.get("content_units")
        if not isinstance(content_units, list):
            return None
        return {
            "content_units": [self._normalize_unit(unit, index) for index, unit in enumerate(content_units, 1)],
            "clarification_needed": bool(output.get("clarification_needed", False)),
            "clarification_reason": output.get("clarification_reason"),
        }

    def _rule_understand(self, graph_state: dict, turn_input: object, raw_input: str) -> dict:
        session_memory = graph_state["session_memory"]
        current_question_id = session_memory["current_question_id"]
        question_states = session_memory["question_states"]
        direct_answer_payload = getattr(turn_input, "direct_answer_payload", None)
        if direct_answer_payload and direct_answer_payload.get("question_id"):
            question_id = direct_answer_payload["question_id"]
            selected_options = list(direct_answer_payload.get("selected_options", []))
            input_value = direct_answer_payload.get("input_value", "")
            raw_value = input_value or " ".join(selected_options)
            extracted_value: object = raw_value
            action_mode = self._action_mode(session_memory, question_id)
            if question_id == "question-02":
                schedule = parse_schedule_fragment(raw_value)
                extracted_value = schedule["filled_fields"] or raw_value
                if self._should_resume_partial_schedule(session_memory, question_id, schedule["filled_fields"]):
                    action_mode = "partial_completion"
            elif selected_options:
                extracted_value = {
                    "selected_options": selected_options,
                    "input_value": input_value,
                }
            return {
                "content_units": [
                    {
                        "unit_id": "unit-1",
                        "unit_text": raw_input,
                        "action_mode": action_mode,
                        "candidate_question_ids": [question_id],
                        "winner_question_id": question_id,
                        "needs_attribution": False,
                        "raw_extracted_value": extracted_value,
                    }
                ],
                "clarification_needed": False,
                "clarification_reason": None,
            }

        content_units: list[dict] = []
        age_unit = self._extract_age_unit(session_memory, raw_input)
        if age_unit is not None:
            content_units.append(age_unit)

        schedule_unit = self._extract_schedule_unit(session_memory, raw_input)
        if schedule_unit is not None:
            content_units.append(schedule_unit)

        if content_units:
            return {
                "content_units": content_units,
                "clarification_needed": False,
                "clarification_reason": None,
            }

        if current_question_id and question_states[current_question_id]["status"] == "partial":
            return {
                "content_units": [],
                "clarification_needed": True,
                "clarification_reason": "partial_missing_fields",
            }

        if raw_input.isdigit():
            winner = current_question_id if current_question_id == "question-01" else "question-01"
            return {
                "content_units": [
                    {
                        "unit_id": "unit-1",
                        "unit_text": raw_input,
                        "action_mode": self._action_mode(session_memory, winner),
                        "candidate_question_ids": [winner],
                        "winner_question_id": winner,
                        "needs_attribution": False,
                        "raw_extracted_value": raw_input,
                    }
                ],
                "clarification_needed": False,
                "clarification_reason": None,
            }

        schedule = parse_schedule_fragment(raw_input)
        if schedule["is_time_point_only"]:
            candidate_question_ids = self._time_candidates(graph_state)
            return {
                "content_units": [
                    {
                        "unit_id": "unit-1",
                        "unit_text": raw_input,
                        "action_mode": self._action_mode(session_memory, current_question_id),
                        "candidate_question_ids": candidate_question_ids,
                        "winner_question_id": None,
                        "needs_attribution": True,
                        "raw_extracted_value": raw_input,
                    }
                ],
                "clarification_needed": False,
                "clarification_reason": None,
            }

        if self._contains_time_expression(raw_input):
            candidate_question_ids = self._time_candidates(graph_state)
            return {
                "content_units": [
                    {
                        "unit_id": "unit-1",
                        "unit_text": raw_input,
                        "action_mode": self._action_mode(session_memory, current_question_id),
                        "candidate_question_ids": candidate_question_ids,
                        "winner_question_id": None,
                        "needs_attribution": True,
                        "raw_extracted_value": raw_input,
                    }
                ],
                "clarification_needed": False,
                "clarification_reason": None,
            }

        return {
            "content_units": [
                {
                    "unit_id": "unit-1",
                    "unit_text": raw_input,
                    "action_mode": self._action_mode(session_memory, current_question_id),
                    "candidate_question_ids": [current_question_id] if current_question_id else [],
                    "winner_question_id": current_question_id,
                    "needs_attribution": False,
                    "raw_extracted_value": raw_input,
                }
            ],
            "clarification_needed": current_question_id is None,
            "clarification_reason": None if current_question_id else "no_target_question",
        }

    def _contains_time_expression(self, raw_input: str) -> bool:
        return bool(_TIME_EXPRESSION_PATTERN.search(raw_input))

    def _has_relaxed_context(self, raw_input: str) -> bool:
        return any(token in raw_input for token in _RELAXED_CONTEXT_TOKENS)

    def _extract_age_unit(self, session_memory: dict, raw_input: str) -> dict | None:
        question_id = "question-01"
        answered = session_memory["question_states"][question_id]["status"] == "answered"
        correction_match = _AGE_CORRECTION_PATTERN.search(raw_input)
        if "年龄" in raw_input and correction_match:
            age_clause = re.split(r"[;；]", raw_input, maxsplit=1)[0]
            numbers = re.findall(r"\d{1,3}", age_clause)
            corrected_age = numbers[-1] if numbers else correction_match.group("age")
            return {
                "unit_id": "unit-1",
                "unit_text": raw_input,
                "action_mode": "modify" if answered else "answer",
                "candidate_question_ids": [question_id],
                "winner_question_id": question_id,
                "needs_attribution": False,
                "raw_extracted_value": corrected_age,
            }
        age_match = _AGE_PATTERN.search(raw_input)
        if age_match:
            return {
                "unit_id": "unit-1",
                "unit_text": age_match.group(0),
                "action_mode": self._action_mode(session_memory, question_id),
                "candidate_question_ids": [question_id],
                "winner_question_id": question_id,
                "needs_attribution": False,
                "raw_extracted_value": age_match.group("age"),
            }
        if raw_input.isdigit():
            return {
                "unit_id": "unit-1",
                "unit_text": raw_input,
                "action_mode": self._action_mode(session_memory, question_id),
                "candidate_question_ids": [question_id],
                "winner_question_id": question_id,
                "needs_attribution": False,
                "raw_extracted_value": raw_input,
            }
        if "年龄" in raw_input:
            numbers = _RAW_NUMBER_PATTERN.findall(raw_input)
            if numbers:
                return {
                    "unit_id": "unit-1",
                    "unit_text": raw_input,
                    "action_mode": self._action_mode(session_memory, question_id),
                    "candidate_question_ids": [question_id],
                    "winner_question_id": question_id,
                    "needs_attribution": False,
                    "raw_extracted_value": numbers[-1],
                }
        return None

    def _extract_schedule_unit(self, session_memory: dict, raw_input: str) -> dict | None:
        schedule = parse_schedule_fragment(raw_input)
        if not schedule["filled_fields"]:
            return None
        if self._has_relaxed_context(raw_input):
            return None
        question_id = "question-02"
        if self._should_resume_partial_schedule(session_memory, question_id, schedule["filled_fields"]):
            action_mode = "partial_completion"
        else:
            action_mode = self._action_mode(session_memory, question_id)
        unit_id = "unit-2" if "年龄" in raw_input or _AGE_PATTERN.search(raw_input) else "unit-1"
        return {
            "unit_id": unit_id,
            "unit_text": raw_input,
            "action_mode": action_mode,
            "candidate_question_ids": [question_id],
            "winner_question_id": question_id,
            "needs_attribution": False,
            "raw_extracted_value": schedule["filled_fields"],
        }

    def _action_mode(self, session_memory: dict, question_id: str | None) -> str:
        if not question_id:
            return "answer"
        status = session_memory["question_states"][question_id]["status"]
        if status == "answered":
            return "modify"
        if status == "partial":
            return "partial_completion"
        return "answer"

    def _should_resume_partial_schedule(
        self,
        session_memory: dict,
        question_id: str,
        filled_fields: dict[str, str],
    ) -> bool:
        if question_id != "question-02" or not filled_fields:
            return False
        existing = session_memory["pending_partial_answers"].get(question_id)
        if not existing:
            return False
        missing_fields = set(existing.get("missing_fields", []))
        if not missing_fields:
            return False
        field_names = set(filled_fields)
        return field_names.issubset(missing_fields)

    def _time_candidates(self, graph_state: dict) -> list[str]:
        question_order = graph_state["question_catalog"]["question_order"]
        question_index = graph_state["question_catalog"]["question_index"]
        return [
            question_id
            for question_id in question_order
            if self._is_time_candidate(question_id, question_index.get(question_id, {}))
        ]

    def _is_time_candidate(self, question_id: str, question_entry: dict) -> bool:
        if question_entry.get("input_type") in {"time_range", "time_point"}:
            return True
        if question_id in {"question-03", "question-04"}:
            return True
        metadata = question_entry.get("metadata", {})
        hints = [str(item) for item in metadata.get("matching_hints", [])]
        hint_text = " ".join(hints).lower()
        return "free day" in hint_text or "weekend" in hint_text

    def _build_memory_view(self, graph_state: dict) -> dict:
        session_memory = graph_state["session_memory"]
        return {
            "current_question_id": session_memory["current_question_id"],
            "pending_question_ids": list(session_memory["pending_question_ids"]),
            "answered_question_ids": list(session_memory["answered_question_ids"]),
            "partial_question_ids": list(session_memory["partial_question_ids"]),
            "pending_modify_context": session_memory["pending_modify_context"],
            "pending_partial_answers": session_memory["pending_partial_answers"],
            "recent_turns": session_memory["recent_turns"][-5:],
            "clarification_context": session_memory["clarification_context"],
        }

    def _normalize_unit(self, unit: dict, index: int) -> dict:
        return {
            "unit_id": unit.get("unit_id") or f"unit-{index}",
            "unit_text": unit.get("unit_text", ""),
            "action_mode": unit.get("action_mode", "answer"),
            "candidate_question_ids": list(unit.get("candidate_question_ids", [])),
            "winner_question_id": unit.get("winner_question_id"),
            "needs_attribution": bool(unit.get("needs_attribution", False)),
            "raw_extracted_value": unit.get("raw_extracted_value", unit.get("unit_text", "")),
        }
