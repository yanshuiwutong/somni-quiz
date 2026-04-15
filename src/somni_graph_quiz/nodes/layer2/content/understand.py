"""Content understanding node."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from somni_graph_quiz.llm.invocation import invoke_json
from somni_graph_quiz.llm.prompt_loader import PromptLoader
from somni_graph_quiz.nodes.layer2.content.mapping import (
    extract_explicit_option_selector,
    map_content_answer,
    map_empty_option_custom_fallback,
    should_prefer_empty_option_custom_fallback,
)
from somni_graph_quiz.utils.time_parse import parse_schedule_fragment


_PROMPTS_ROOT = Path(__file__).resolve().parents[5] / "prompts"
_DIAGNOSTIC_LOGGER = logging.getLogger("somni_graph_quiz.diagnostics.content_understand")

_AGE_PATTERN = re.compile(r"(?P<age>\d{1,3})\s*岁")
_AGE_CORRECTION_PATTERN = re.compile(r"(?:不是|改成|改为|改)\s*(?P<age>\d{1,3})")
_RAW_NUMBER_PATTERN = re.compile(r"\b(?P<number>\d{1,3})\b")
_TIME_EXPRESSION_PATTERN = re.compile(
    r"(?:\d{1,2}|十二|十一|十|两|零|一|二|三|四|五|六|七|八|九)"
    r"(?:\s*[:：]\s*\d{1,2})?\s*(?:点|时)(?=$|[\s,，。；;：:、!?？]|左右|前后|半|整|睡|起|醒|上床|下床)"
)
_RELAXED_CONTEXT_TOKENS = ("自由", "自然", "周末", "休息日", "完全自由安排")
_WAKE_AFTER_TIME_PATTERN = re.compile(r"(?:点|时)\s*起")
_SELECTOR_ONLY_ORDINAL_PATTERN = re.compile(
    r"第\s*(?:\d+|十[一二三四五六七八九]?|[一二两三四五六七八九十])\s*(?:个|项)?",
    re.IGNORECASE,
)
_SELECTOR_ONLY_LETTER_PATTERN = re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z])(?![A-Za-z0-9])")
_SELECTOR_ONLY_FILLER_PATTERN = re.compile(
    r"(?:我要|我想|我就|那我|那就|就是|我|选项|选|选择|答案|是的|是|嗯|哦|好|好的|吧|呀|啊|呢|嘛|这个|那个)",
    re.IGNORECASE,
)
_SELECTOR_ONLY_PUNCTUATION_PATTERN = re.compile(r"[\s,，。！？!?.、~`'\"“”‘’：:；;（）()【】\[\]<>《》\-]+")


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

        session_memory = graph_state["session_memory"]
        if self._is_selector_only_input(raw_input):
            scoped_selector_unit = self._extract_scoped_single_choice_selector_unit(
                graph_state,
                session_memory,
                raw_input,
            )
            if scoped_selector_unit is not None:
                understood = self._standardize_understood(
                    graph_state,
                    {
                        "content_units": [scoped_selector_unit],
                        "clarification_needed": False,
                        "clarification_reason": None,
                    },
                )
                understood["content_units"] = self._resolve_single_choice_units(
                    graph_state,
                    understood.get("content_units", []),
                )
                self._log_diagnostic(
                    "selector_only_scope_applied",
                    raw_input=raw_input,
                    content_units=self._summarize_units(understood.get("content_units", [])),
                )
                return understood
            return {
                "content_units": [],
                "clarification_needed": True,
                "clarification_reason": "current_question_mismatch",
                "clarification_question_id": session_memory.get("current_question_id"),
                "clarification_question_title": (
                    graph_state["question_catalog"]["question_index"][
                        session_memory["current_question_id"]
                    ].get("title")
                    if session_memory.get("current_question_id")
                    else None
                ),
                "clarification_kind": "current_question_mismatch",
            }

        llm_output, llm_attempt = self._try_llm(graph_state, turn_input)
        if llm_output is not None:
            understood = self._standardize_understood(graph_state, llm_output)
            understood["content_units"] = self._resolve_single_choice_units(
                graph_state,
                understood.get("content_units", []),
            )
            understood = self._apply_current_single_choice_custom_fallback(
                graph_state,
                session_memory,
                raw_input,
                understood,
                source="llm",
            )
            understood = self._override_current_single_choice_custom_option_misfires(
                graph_state,
                session_memory,
                understood,
                source="llm",
            )
            self._log_diagnostic(
                "llm_result_consumed",
                raw_input=raw_input,
                llm_provider_available=llm_attempt["llm_provider_available"],
                path="llm",
                content_units=self._summarize_units(understood.get("content_units", [])),
                clarification_needed=bool(understood.get("clarification_needed", False)),
            )
            self._log_diagnostic(
                "content_units_standardized",
                raw_input=raw_input,
                path="llm",
                content_units=self._summarize_units(understood.get("content_units", [])),
                clarification_needed=bool(understood.get("clarification_needed", False)),
            )
            return understood
        understood = self._standardize_understood(
            graph_state,
            self._rule_understand(graph_state, turn_input, raw_input),
        )
        understood["content_units"] = self._resolve_single_choice_units(
            graph_state,
            understood.get("content_units", []),
        )
        self._log_diagnostic(
            "rule_fallback_used",
            raw_input=raw_input,
            llm_provider_available=llm_attempt["llm_provider_available"],
            path="rule",
            fallback_reason=llm_attempt["event"],
            content_units=self._summarize_units(understood.get("content_units", [])),
            clarification_needed=bool(understood.get("clarification_needed", False)),
        )
        self._log_diagnostic(
            "content_units_standardized",
            raw_input=raw_input,
            path="rule",
            content_units=self._summarize_units(understood.get("content_units", [])),
            clarification_needed=bool(understood.get("clarification_needed", False)),
        )
        return understood

    def standardize_content_unit(self, graph_state: dict, content_unit: dict) -> dict:
        """Normalize a resolved content unit into a storage-ready payload."""
        normalized = self._normalize_unit(content_unit, 1)
        normalized = self._prefer_regular_schedule_question(graph_state, normalized)
        normalized = self._ensure_regular_schedule_question(graph_state, normalized)
        normalized = self._prefer_current_free_time_question(graph_state, normalized)
        normalized = self._resolve_single_choice_winner(graph_state, normalized)
        question_id = normalized.get("winner_question_id")
        if not question_id:
            return normalized
        question = graph_state["question_catalog"]["question_index"].get(question_id)
        if not question:
            return normalized
        normalized = self._normalize_action_mode_for_state(graph_state, normalized)
        if normalized["selected_options"] or normalized["field_updates"] or normalized["missing_fields"]:
            return normalized
        mapped = self._map_regular_schedule_unit(normalized)
        if mapped is None:
            mapped = map_content_answer(
                question,
                normalized.get("raw_extracted_value", normalized.get("unit_text", "")),
                raw_text=normalized.get("unit_text", ""),
                allow_custom_empty_option_fallback=(
                    question_id == graph_state["session_memory"].get("current_question_id")
                ),
            )
        if (
            not mapped.get("selected_options")
            and not mapped.get("field_updates")
            and not mapped.get("missing_fields")
            and self._is_single_choice_question(question)
        ):
            llm_mapped = self._try_llm_option_mapping(
                graph_state,
                question,
                normalized.get("unit_text", ""),
            )
            if llm_mapped is not None:
                mapped = llm_mapped
        field_updates = dict(mapped.get("field_updates", {}))
        missing_fields = list(mapped.get("missing_fields", []))
        if normalized.get("action_mode") == "partial_completion" and field_updates:
            existing = (
                graph_state["session_memory"]
                .get("pending_partial_answers", {})
                .get(question_id, {})
                .get("filled_fields", {})
            )
            merged_fields = {**dict(existing), **field_updates}
            missing_fields = [
                field for field in ("bedtime", "wake_time") if field not in merged_fields
            ]
        return {
            **normalized,
            "selected_options": list(mapped.get("selected_options", [])),
            "input_value": str(mapped.get("input_value", "")),
            "field_updates": field_updates,
            "missing_fields": missing_fields,
        }

    def _prefer_current_free_time_question(self, graph_state: dict, unit: dict) -> dict:
        session_memory = graph_state["session_memory"]
        target_question_id = self._time_question_priority_target(
            session_memory,
            str(unit.get("unit_text", "")),
        )
        if target_question_id not in {"question-03", "question-04"}:
            return unit

        current_question_id = str(session_memory.get("current_question_id") or "")
        modify_target = str((session_memory.get("pending_modify_context") or {}).get("question_id") or "")
        if target_question_id not in {current_question_id, modify_target}:
            return unit

        if str(unit.get("winner_question_id") or "") == target_question_id:
            return unit

        mapped = self._map_unit_to_target_question(
            graph_state,
            unit,
            target_question_id,
        )
        if mapped is None or not mapped.get("selected_options"):
            return unit

        return {
            **unit,
            "action_mode": self._action_mode(session_memory, target_question_id),
            "candidate_question_ids": [target_question_id],
            "winner_question_id": target_question_id,
            "needs_attribution": False,
            "selected_options": list(mapped.get("selected_options", [])),
            "input_value": str(mapped.get("input_value", "")),
            "field_updates": dict(mapped.get("field_updates", {})),
            "missing_fields": list(mapped.get("missing_fields", [])),
        }

    def _map_unit_to_target_question(
        self,
        graph_state: dict,
        unit: dict,
        question_id: str,
    ) -> dict | None:
        question = graph_state["question_catalog"]["question_index"].get(question_id)
        if not question:
            return None
        mapped = map_content_answer(
            question,
            unit.get("raw_extracted_value", unit.get("unit_text", "")),
            raw_text=unit.get("unit_text", ""),
            allow_custom_empty_option_fallback=(
                question_id == graph_state["session_memory"].get("current_question_id")
            ),
        )
        if (
            not mapped.get("selected_options")
            and not mapped.get("field_updates")
            and not mapped.get("missing_fields")
            and self._is_single_choice_question(question)
        ):
            llm_mapped = self._try_llm_option_mapping(
                graph_state,
                question,
                unit.get("unit_text", ""),
            )
            if llm_mapped is not None:
                mapped = llm_mapped
        return mapped

    def _apply_current_single_choice_custom_fallback(
        self,
        graph_state: dict,
        session_memory: dict,
        raw_input: str,
        understood: dict,
        *,
        source: str,
    ) -> dict:
        if not self._should_try_current_single_choice_custom_fallback(graph_state, understood):
            return understood
        fallback_unit = self._extract_current_single_choice_custom_fallback_unit(
            graph_state,
            session_memory,
            raw_input,
        )
        if fallback_unit is None:
            return understood
        fallback_understood = self._standardize_understood(
            graph_state,
            {
                "content_units": [fallback_unit],
                "clarification_needed": False,
                "clarification_reason": None,
            },
        )
        fallback_understood["content_units"] = self._resolve_single_choice_units(
            graph_state,
            fallback_understood.get("content_units", []),
        )
        self._log_diagnostic(
            "current_single_choice_custom_fallback_applied",
            raw_input=raw_input,
            source=source,
            prior_content_units=self._summarize_units(understood.get("content_units", [])),
            prior_clarification_needed=bool(understood.get("clarification_needed", False)),
            content_units=self._summarize_units(fallback_understood.get("content_units", [])),
        )
        return fallback_understood

    def _override_current_single_choice_custom_option_misfires(
        self,
        graph_state: dict,
        session_memory: dict,
        understood: dict,
        *,
        source: str,
    ) -> dict:
        current_question_id = str(session_memory.get("current_question_id") or "")
        if not current_question_id:
            return understood
        question = graph_state["question_catalog"]["question_index"].get(current_question_id)
        if not self._is_single_choice_question(question):
            return understood
        content_units = understood.get("content_units", [])
        if not isinstance(content_units, list) or not content_units:
            return understood

        corrected_units: list[dict] = []
        applied = False
        for unit in content_units:
            if not isinstance(unit, dict):
                corrected_units.append(unit)
                continue
            unit_question_id = str(unit.get("winner_question_id") or "")
            unit_text = str(unit.get("unit_text", "")).strip()
            selected_options = list(unit.get("selected_options", []))
            if (
                unit_question_id != current_question_id
                or not selected_options
                or not unit_text
                or not should_prefer_empty_option_custom_fallback(question, unit_text)
            ):
                corrected_units.append(unit)
                continue
            fallback = map_empty_option_custom_fallback(question, unit_text)
            if fallback is None:
                corrected_units.append(unit)
                continue
            corrected_units.append(
                {
                    **unit,
                    "selected_options": list(fallback.get("selected_options", [])),
                    "input_value": str(fallback.get("input_value", "")),
                    "field_updates": {},
                    "missing_fields": [],
                }
            )
            applied = True

        if not applied:
            return understood
        corrected_understood = {
            **understood,
            "content_units": corrected_units,
        }
        self._log_diagnostic(
            "current_single_choice_custom_option_misfire_overridden",
            source=source,
            prior_content_units=self._summarize_units(content_units),
            content_units=self._summarize_units(corrected_units),
        )
        return corrected_understood

    def _should_try_current_single_choice_custom_fallback(
        self,
        graph_state: dict,
        understood: dict,
    ) -> bool:
        current_question_id = str(graph_state["session_memory"].get("current_question_id") or "")
        if not current_question_id:
            return False
        question = graph_state["question_catalog"]["question_index"].get(current_question_id)
        if not self._is_single_choice_question(question):
            return False
        if bool(understood.get("clarification_needed", False)):
            return True
        content_units = understood.get("content_units", [])
        if not isinstance(content_units, list) or not content_units:
            return True
        return any(
            str(unit.get("winner_question_id") or "") == current_question_id
            and not self._content_unit_has_answer_signal(unit)
            for unit in content_units
            if isinstance(unit, dict)
        )

    def _content_unit_has_answer_signal(self, unit: dict) -> bool:
        return bool(
            list(unit.get("selected_options", []))
            or dict(unit.get("field_updates", {}))
            or list(unit.get("missing_fields", []))
        )

    def _normalize_action_mode_for_state(self, graph_state: dict, unit: dict) -> dict:
        question_id = str(unit.get("winner_question_id") or "")
        if not question_id:
            return unit
        session_memory = graph_state["session_memory"]
        normalized_action_mode = self._action_mode(session_memory, question_id)
        if question_id == "question-02":
            field_updates = dict(unit.get("field_updates", {}))
            if not field_updates:
                field_updates = self._extract_regular_schedule_fields(unit)
            if self._should_resume_partial_schedule(session_memory, question_id, field_updates):
                normalized_action_mode = "partial_completion"
        if str(unit.get("action_mode") or "") == normalized_action_mode:
            return unit
        return {
            **unit,
            "action_mode": normalized_action_mode,
        }

    def _map_regular_schedule_unit(self, unit: dict) -> dict | None:
        if str(unit.get("winner_question_id") or "") != "question-02":
            return None
        field_updates = self._extract_regular_schedule_fields(unit)
        if not field_updates:
            return None
        input_value = str(unit.get("input_value", ""))
        if not input_value and {"bedtime", "wake_time"}.issubset(field_updates):
            input_value = f"{field_updates['bedtime']}-{field_updates['wake_time']}"
        return {
            "selected_options": [],
            "input_value": input_value,
            "field_updates": field_updates,
            "missing_fields": [field for field in ("bedtime", "wake_time") if field not in field_updates],
        }

    def _extract_regular_schedule_fields(self, unit: dict) -> dict[str, str]:
        raw_extracted_value = unit.get("raw_extracted_value")
        if isinstance(raw_extracted_value, dict):
            direct_fields = {
                field: str(value)
                for field in ("bedtime", "wake_time")
                if (value := raw_extracted_value.get(field))
            }
            if direct_fields:
                return direct_fields

        for candidate_text in self._regular_schedule_parse_candidates(unit):
            filled_fields = parse_schedule_fragment(candidate_text).get("filled_fields", {})
            if filled_fields:
                return {
                    field: str(value)
                    for field, value in filled_fields.items()
                    if field in {"bedtime", "wake_time"} and value
                }
        return {}

    def _regular_schedule_parse_candidates(self, unit: dict) -> list[str]:
        candidates: list[str] = []
        for value in (
            unit.get("unit_text", ""),
            unit.get("raw_extracted_value", ""),
            unit.get("input_value", ""),
        ):
            if isinstance(value, str):
                normalized_value = value.strip()
                if normalized_value and normalized_value not in candidates:
                    candidates.append(normalized_value)
        return candidates

    def _prefer_regular_schedule_question(self, graph_state: dict, unit: dict) -> dict:
        regular_schedule_question_id = "question-02"
        time_question_ids = {regular_schedule_question_id, "question-03", "question-04"}
        question_index = graph_state["question_catalog"]["question_index"]
        if regular_schedule_question_id not in question_index:
            return unit
        time_question_priority_target = self._time_question_priority_target(
            graph_state["session_memory"],
            str(unit.get("unit_text", "")),
        )
        candidate_question_ids = {str(question_id) for question_id in unit.get("candidate_question_ids", [])}
        winner_question_id = str(unit.get("winner_question_id") or "")
        if time_question_priority_target and (
            winner_question_id == time_question_priority_target
            or time_question_priority_target in candidate_question_ids
        ):
            return unit
        if winner_question_id and winner_question_id not in time_question_ids:
            return unit
        if candidate_question_ids and not (candidate_question_ids & time_question_ids):
            return unit
        if self._has_relaxed_context(str(unit.get("unit_text", ""))):
            return unit
        if not self._looks_like_regular_schedule_unit(unit):
            return unit
        return {
            **unit,
            "candidate_question_ids": [regular_schedule_question_id],
            "winner_question_id": regular_schedule_question_id,
            "needs_attribution": False,
        }

    def _ensure_regular_schedule_question(self, graph_state: dict, unit: dict) -> dict:
        regular_schedule_question_id = "question-02"
        question_index = graph_state["question_catalog"]["question_index"]
        if regular_schedule_question_id not in question_index:
            return unit
        unit_text = str(unit.get("unit_text", ""))
        if self._has_relaxed_context(unit_text):
            return unit
        candidate_question_ids = {
            str(question_id)
            for question_id in unit.get("candidate_question_ids", [])
            if question_id
        }
        winner_question_id = str(unit.get("winner_question_id") or "")
        time_question_ids = {"question-03", "question-04"}
        if not (candidate_question_ids & time_question_ids or winner_question_id in time_question_ids):
            return unit
        session_memory = graph_state["session_memory"]
        if self._time_question_priority_target(session_memory, unit_text):
            return unit
        schedule = parse_schedule_fragment(unit_text)
        filled_fields = schedule.get("filled_fields", {})
        if not filled_fields:
            return unit
        if not ({"bedtime", "wake_time"} & set(filled_fields)):
            return unit
        winner_question_id = str(unit.get("winner_question_id") or "")
        if winner_question_id == regular_schedule_question_id:
            return unit
        return {
            **unit,
            "candidate_question_ids": [regular_schedule_question_id],
            "winner_question_id": regular_schedule_question_id,
            "needs_attribution": False,
        }

    def _try_llm(self, graph_state: dict, turn_input: object) -> tuple[dict | None, dict]:
        runtime = graph_state["runtime"]
        provider = runtime.get("llm_provider")
        raw_input = getattr(turn_input, "raw_input", "")
        llm_provider_available = bool(runtime.get("llm_available", True) and provider is not None)
        self._log_diagnostic(
            "llm_attempt_started",
            raw_input=raw_input,
            llm_provider_available=llm_provider_available,
        )
        if not runtime.get("llm_available", True) or provider is None:
            self._log_diagnostic(
                "llm_unavailable",
                raw_input=raw_input,
                llm_provider_available=False,
            )
            return None, {
                "event": "llm_unavailable",
                "llm_provider_available": False,
            }
        payload = {
            "raw_input": raw_input,
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
        except Exception as exc:
            self._log_diagnostic(
                "llm_exception",
                raw_input=raw_input,
                llm_provider_available=True,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            return None, {
                "event": "llm_exception",
                "llm_provider_available": True,
            }
        content_units = output.get("content_units")
        if not isinstance(content_units, list):
            self._log_diagnostic(
                "llm_invalid_schema",
                raw_input=raw_input,
                llm_provider_available=True,
                output_keys=sorted(str(key) for key in output.keys()),
                content_units_type=type(content_units).__name__,
            )
            return None, {
                "event": "llm_invalid_schema",
                "llm_provider_available": True,
            }
        understood = {
            "content_units": [self._normalize_unit(unit, index) for index, unit in enumerate(content_units, 1)],
            "clarification_needed": bool(output.get("clarification_needed", False)),
            "clarification_reason": output.get("clarification_reason"),
        }
        self._log_diagnostic(
            "llm_result_received",
            raw_input=raw_input,
            llm_provider_available=True,
            content_units=self._summarize_units(understood["content_units"]),
            clarification_needed=understood["clarification_needed"],
        )
        return understood, {
            "event": "llm_result_received",
            "llm_provider_available": True,
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
                "clarification_question_id": current_question_id,
                "clarification_question_title": graph_state["question_catalog"]["question_index"][
                    current_question_id
                ].get("title"),
                "clarification_kind": "partial_missing_fields",
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
            if (
                "question-02" in session_memory["question_states"]
                and not self._has_relaxed_context(raw_input)
                and not self._time_question_priority_target(session_memory, raw_input)
            ):
                question_id = "question-02"
                action_mode = self._action_mode(session_memory, question_id)
                if self._should_resume_partial_schedule(
                    session_memory,
                    question_id,
                    schedule["filled_fields"],
                ):
                    action_mode = "partial_completion"
                return {
                    "content_units": [
                        {
                            "unit_id": "unit-1",
                            "unit_text": raw_input,
                            "action_mode": action_mode,
                            "candidate_question_ids": [question_id],
                            "winner_question_id": question_id,
                            "needs_attribution": False,
                            "raw_extracted_value": schedule["filled_fields"] or raw_input,
                        }
                    ],
                    "clarification_needed": False,
                    "clarification_reason": None,
                }
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

        current_selector_unit = self._extract_current_single_choice_selector_unit(
            graph_state,
            session_memory,
            raw_input,
        )
        if current_selector_unit is not None:
            return {
                "content_units": [current_selector_unit],
                "clarification_needed": False,
                "clarification_reason": None,
            }

        current_custom_fallback_unit = self._extract_current_single_choice_custom_fallback_unit(
            graph_state,
            session_memory,
            raw_input,
        )
        if current_custom_fallback_unit is not None:
            return {
                "content_units": [current_custom_fallback_unit],
                "clarification_needed": False,
                "clarification_reason": None,
            }

        generic_candidates = self._extract_generic_question_candidates(graph_state, raw_input)
        if generic_candidates:
            if len(generic_candidates) == 1:
                question_id = generic_candidates[0]
                return {
                    "content_units": [
                        {
                            "unit_id": "unit-1",
                            "unit_text": raw_input,
                            "action_mode": self._action_mode(session_memory, question_id),
                            "candidate_question_ids": [question_id],
                            "winner_question_id": question_id,
                            "needs_attribution": False,
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
                        "candidate_question_ids": generic_candidates,
                        "winner_question_id": None,
                        "needs_attribution": True,
                        "raw_extracted_value": raw_input,
                    }
                ],
                "clarification_needed": False,
                "clarification_reason": None,
            }

        return {
            "content_units": [],
            "clarification_needed": True,
            "clarification_reason": "current_question_mismatch" if current_question_id else "no_target_question",
            "clarification_question_id": current_question_id,
            "clarification_question_title": (
                graph_state["question_catalog"]["question_index"][current_question_id].get("title")
                if current_question_id
                else None
            ),
            "clarification_kind": "current_question_mismatch" if current_question_id else "no_target_question",
        }

    def _contains_time_expression(self, raw_input: str) -> bool:
        return bool(_TIME_EXPRESSION_PATTERN.search(raw_input))

    def _has_relaxed_context(self, raw_input: str) -> bool:
        return any(token in raw_input for token in _RELAXED_CONTEXT_TOKENS)

    def _looks_like_regular_schedule_unit(self, unit: dict) -> bool:
        unit_text = str(unit.get("unit_text", ""))
        if not any(token in unit_text for token in ("睡", "起", "醒", "上床", "下床")):
            return False
        raw_extracted_value = unit.get("raw_extracted_value")
        if isinstance(raw_extracted_value, dict):
            field_names = set(raw_extracted_value)
            if "bedtime" in field_names or "wake_time" in field_names:
                return True
        field_updates = unit.get("field_updates", {})
        if isinstance(field_updates, dict):
            field_names = set(field_updates)
            if "bedtime" in field_names or "wake_time" in field_names:
                return True
        return False

    def _extract_age_unit(self, session_memory: dict, raw_input: str) -> dict | None:
        question_id = "question-01"
        if question_id not in session_memory["question_states"]:
            return None
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
        if "question-02" not in session_memory["question_states"]:
            return None
        schedule = parse_schedule_fragment(raw_input)
        if not schedule["filled_fields"]:
            return None
        if self._has_relaxed_context(raw_input):
            return None
        if self._time_question_priority_target(session_memory, raw_input):
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

    def _time_question_priority_target(self, session_memory: dict, raw_input: str) -> str | None:
        current_question_id = str(session_memory.get("current_question_id") or "")
        if self._can_answer_time_question(current_question_id, raw_input):
            return current_question_id

        pending_modify_context = session_memory.get("pending_modify_context") or {}
        modify_target = str(pending_modify_context.get("question_id") or "")
        if self._can_answer_time_question(modify_target, raw_input):
            return modify_target
        return None

    def _can_answer_time_question(self, question_id: str, raw_input: str) -> bool:
        if question_id not in {"question-03", "question-04"}:
            return False
        if not self._contains_time_expression(raw_input):
            return False

        looks_like_wake = self._looks_like_wake_text(raw_input)
        looks_like_sleep = self._looks_like_sleep_text(raw_input)
        if question_id == "question-03":
            return not (looks_like_wake and not looks_like_sleep)
        return not (looks_like_sleep and not looks_like_wake)

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

    def _extract_generic_question_candidates(self, graph_state: dict, raw_input: str) -> list[str]:
        candidates: list[str] = []
        question_catalog = graph_state["question_catalog"]
        has_time_expression = self._contains_time_expression(raw_input)
        for question_id in question_catalog["question_order"]:
            question = question_catalog["question_index"][question_id]
            if has_time_expression and self._looks_like_age_question(question):
                continue
            mapped = map_content_answer(
                question,
                raw_input,
                raw_text=raw_input,
                allow_explicit_selectors=False,
            )
            if self._has_answer_signal(question, mapped):
                candidates.append(question_id)
        return candidates

    def _extract_current_single_choice_selector_unit(
        self,
        graph_state: dict,
        session_memory: dict,
        raw_input: str,
    ) -> dict | None:
        current_question_id = str(session_memory.get("current_question_id") or "")
        if not current_question_id:
            return None
        question = graph_state["question_catalog"]["question_index"].get(current_question_id)
        selected_option_id = extract_explicit_option_selector(question, raw_input)
        if selected_option_id is None:
            return None
        return {
            "unit_id": "unit-1",
            "unit_text": raw_input,
            "action_mode": self._action_mode(session_memory, current_question_id),
            "candidate_question_ids": [current_question_id],
            "winner_question_id": current_question_id,
            "needs_attribution": False,
            "raw_extracted_value": {
                "selected_options": [selected_option_id],
                "input_value": "",
            },
            "selected_options": [selected_option_id],
            "input_value": "",
            "field_updates": {},
            "missing_fields": [],
        }

    def _extract_scoped_single_choice_selector_unit(
        self,
        graph_state: dict,
        session_memory: dict,
        raw_input: str,
    ) -> dict | None:
        current_selector_unit = self._extract_current_single_choice_selector_unit(
            graph_state,
            session_memory,
            raw_input,
        )
        if current_selector_unit is not None:
            return current_selector_unit
        return self._extract_modify_target_single_choice_selector_unit(
            graph_state,
            session_memory,
            raw_input,
        )

    def _extract_modify_target_single_choice_selector_unit(
        self,
        graph_state: dict,
        session_memory: dict,
        raw_input: str,
    ) -> dict | None:
        modify_target = str((session_memory.get("pending_modify_context") or {}).get("question_id") or "")
        current_question_id = str(session_memory.get("current_question_id") or "")
        if not modify_target or modify_target == current_question_id:
            return None
        question = graph_state["question_catalog"]["question_index"].get(modify_target)
        selected_option_id = extract_explicit_option_selector(question, raw_input)
        if selected_option_id is None:
            return None
        return {
            "unit_id": "unit-1",
            "unit_text": raw_input,
            "action_mode": self._action_mode(session_memory, modify_target),
            "candidate_question_ids": [modify_target],
            "winner_question_id": modify_target,
            "needs_attribution": False,
            "raw_extracted_value": {
                "selected_options": [selected_option_id],
                "input_value": "",
            },
            "selected_options": [selected_option_id],
            "input_value": "",
            "field_updates": {},
            "missing_fields": [],
        }

    def _is_selector_only_input(self, raw_input: str) -> bool:
        if not raw_input:
            return False
        if not (
            _SELECTOR_ONLY_ORDINAL_PATTERN.search(raw_input)
            or _SELECTOR_ONLY_LETTER_PATTERN.search(raw_input)
        ):
            return False
        remainder = _SELECTOR_ONLY_ORDINAL_PATTERN.sub(" ", raw_input)
        remainder = _SELECTOR_ONLY_LETTER_PATTERN.sub(" ", remainder)
        remainder = _SELECTOR_ONLY_FILLER_PATTERN.sub(" ", remainder)
        remainder = _SELECTOR_ONLY_PUNCTUATION_PATTERN.sub("", remainder)
        return not remainder

    def _extract_current_single_choice_custom_fallback_unit(
        self,
        graph_state: dict,
        session_memory: dict,
        raw_input: str,
    ) -> dict | None:
        current_question_id = str(session_memory.get("current_question_id") or "")
        if not current_question_id:
            return None
        question = graph_state["question_catalog"]["question_index"].get(current_question_id)
        if not should_prefer_empty_option_custom_fallback(question, raw_input):
            return None
        mapped = map_empty_option_custom_fallback(question, raw_input)
        if mapped is None or mapped.get("input_value", "").strip() != raw_input.strip():
            return None
        return {
            "unit_id": "unit-1",
            "unit_text": raw_input,
            "action_mode": self._action_mode(session_memory, current_question_id),
            "candidate_question_ids": [current_question_id],
            "winner_question_id": current_question_id,
            "needs_attribution": False,
            "raw_extracted_value": {
                "selected_options": list(mapped.get("selected_options", [])),
                "input_value": str(mapped.get("input_value", "")),
            },
            "selected_options": list(mapped.get("selected_options", [])),
            "input_value": str(mapped.get("input_value", "")),
            "field_updates": {},
            "missing_fields": [],
        }

    def _has_answer_signal(self, question: dict, mapped: dict) -> bool:
        if mapped.get("selected_options"):
            return True
        if mapped.get("field_updates"):
            return True
        input_type = str(question.get("input_type", "")).lower()
        if input_type == "text" and not question.get("options"):
            return False
        return False

    def _looks_like_age_question(self, question: dict) -> bool:
        if str(question.get("question_id")) == "question-01":
            return True
        title = str(question.get("title", "")).lower()
        if "年龄" in title or "age" in title:
            return True
        hints = [str(item).lower() for item in question.get("metadata", {}).get("matching_hints", [])]
        return any(token in {"年龄", "age"} for token in hints)

    def _resolve_single_choice_winner(self, graph_state: dict, unit: dict) -> dict:
        return self._resolve_single_choice_unit(graph_state, unit)

    def _is_viable_single_choice_candidate(
        self,
        graph_state: dict,
        question_id: str,
        selected_options: list[str],
    ) -> bool:
        question = graph_state["question_catalog"]["question_index"].get(question_id)
        if not question or not self._is_single_choice_question(question):
            return False
        option_ids = {
            str(option.get("option_id", ""))
            for option in question.get("options", [])
            if str(option.get("option_id", ""))
        }
        if not option_ids:
            return False
        return all(option_id in option_ids for option_id in selected_options)

    def _normalize_unit(self, unit: dict, index: int) -> dict:
        return {
            "unit_id": unit.get("unit_id") or f"unit-{index}",
            "unit_text": unit.get("unit_text", ""),
            "action_mode": unit.get("action_mode", "answer"),
            "candidate_question_ids": list(unit.get("candidate_question_ids", [])),
            "winner_question_id": unit.get("winner_question_id"),
            "needs_attribution": bool(unit.get("needs_attribution", False)),
            "raw_extracted_value": unit.get("raw_extracted_value", unit.get("unit_text", "")),
            "selected_options": list(unit.get("selected_options", [])),
            "input_value": str(unit.get("input_value", "")),
            "field_updates": dict(unit.get("field_updates", {})),
            "missing_fields": list(unit.get("missing_fields", [])),
        }

    def _standardize_understood(self, graph_state: dict, understood: dict) -> dict:
        return {
            "content_units": [
                self.standardize_content_unit(graph_state, unit)
                for unit in understood.get("content_units", [])
            ],
            "clarification_needed": bool(understood.get("clarification_needed", False)),
            "clarification_reason": understood.get("clarification_reason"),
            "clarification_question_id": understood.get("clarification_question_id"),
            "clarification_question_title": understood.get("clarification_question_title"),
            "clarification_kind": understood.get("clarification_kind"),
        }

    def _resolve_single_choice_units(self, graph_state: dict, content_units: list[dict]) -> list[dict]:
        return [self._resolve_single_choice_unit(graph_state, unit) for unit in content_units]

    def _resolve_single_choice_unit(self, graph_state: dict, unit: dict) -> dict:
        winner_question_id = unit.get("winner_question_id")
        candidate_question_ids = [str(question_id) for question_id in unit.get("candidate_question_ids", [])]
        if winner_question_id and winner_question_id not in candidate_question_ids:
            candidate_question_ids = [winner_question_id, *candidate_question_ids]
        if not candidate_question_ids:
            return unit

        single_choice_candidates = [
            question_id
            for question_id in candidate_question_ids
            if self._is_single_choice_question(
                graph_state["question_catalog"]["question_index"].get(question_id),
            )
        ]
        if not single_choice_candidates:
            return unit

        closures = self._resolve_single_choice_candidate_closures(
            graph_state,
            unit,
            single_choice_candidates,
        )
        self._log_diagnostic(
            "single_choice_candidate_closures_evaluated",
            unit_id=unit.get("unit_id"),
            candidate_question_ids=single_choice_candidates,
            viable_closures=[
                {
                    "question_id": closure["question_id"],
                    "selected_options": list(closure["selected_options"]),
                }
                for closure in closures
            ],
        )

        if len(closures) == 1:
            closure = closures[0]
            return {
                **unit,
                "candidate_question_ids": [closure["question_id"]],
                "winner_question_id": closure["question_id"],
                "needs_attribution": False,
                "selected_options": list(closure["selected_options"]),
                "input_value": str(closure.get("input_value", "")),
                "field_updates": dict(closure.get("field_updates", {})),
                "missing_fields": list(closure.get("missing_fields", [])),
            }
        if len(closures) > 1:
            preferred_closure = self._prefer_relaxed_time_closure(graph_state, unit, closures)
            if preferred_closure is not None:
                return {
                    **unit,
                    "candidate_question_ids": [preferred_closure["question_id"]],
                    "winner_question_id": preferred_closure["question_id"],
                    "needs_attribution": False,
                    "selected_options": list(preferred_closure["selected_options"]),
                    "input_value": str(preferred_closure.get("input_value", "")),
                    "field_updates": dict(preferred_closure.get("field_updates", {})),
                    "missing_fields": list(preferred_closure.get("missing_fields", [])),
                }
            return {
                **unit,
                "candidate_question_ids": [closure["question_id"] for closure in closures],
                "winner_question_id": None,
                "needs_attribution": True,
                "selected_options": [],
                "input_value": "",
                "field_updates": {},
                "missing_fields": [],
            }

        if winner_question_id:
            question = graph_state["question_catalog"]["question_index"].get(winner_question_id)
            if self._is_single_choice_question(question):
                if self._content_unit_has_answer_signal(unit):
                    return unit
                return {
                    **unit,
                    "needs_attribution": False,
                    "selected_options": [],
                    "input_value": "",
                    "field_updates": {},
                    "missing_fields": [],
                }

        if len(candidate_question_ids) == 1:
            question_id = candidate_question_ids[0]
            question = graph_state["question_catalog"]["question_index"].get(question_id)
            if self._is_single_choice_question(question):
                return {
                    **unit,
                    "candidate_question_ids": [question_id],
                    "winner_question_id": question_id,
                    "needs_attribution": False,
                    "selected_options": [],
                    "input_value": "",
                    "field_updates": {},
                    "missing_fields": [],
                }

        return {
            **unit,
            "selected_options": [],
            "input_value": "",
            "field_updates": dict(unit.get("field_updates", {})),
            "missing_fields": list(unit.get("missing_fields", [])),
        }

    def _prefer_relaxed_time_closure(
        self,
        graph_state: dict,
        unit: dict,
        closures: list[dict],
    ) -> dict | None:
        closure_by_question_id = {
            str(closure.get("question_id")): closure
            for closure in closures
            if str(closure.get("question_id"))
        }
        closure_question_ids = set(closure_by_question_id)
        if not closure_question_ids or not closure_question_ids.issubset({"question-03", "question-04"}):
            return None

        unit_text = str(unit.get("unit_text", ""))
        if self._looks_like_wake_text(unit_text):
            return closure_by_question_id.get("question-04")
        if self._looks_like_sleep_text(unit_text):
            return closure_by_question_id.get("question-03")

        session_memory = graph_state["session_memory"]
        modify_target = str((session_memory.get("pending_modify_context") or {}).get("question_id") or "")
        if modify_target in closure_by_question_id:
            return closure_by_question_id[modify_target]

        current_question_id = str(session_memory.get("current_question_id") or "")
        if current_question_id in closure_by_question_id:
            return closure_by_question_id[current_question_id]

        return None

    def _resolve_single_choice_candidate_closures(
        self,
        graph_state: dict,
        unit: dict,
        candidate_question_ids: list[str],
    ) -> list[dict]:
        closures: list[dict] = []
        seen_question_ids: set[str] = set()
        for question_id in candidate_question_ids:
            if question_id in seen_question_ids:
                continue
            seen_question_ids.add(question_id)
            closure = self._resolve_single_choice_candidate_closure(graph_state, unit, question_id)
            if closure is not None:
                closures.append(closure)
        return closures

    def _resolve_single_choice_candidate_closure(
        self,
        graph_state: dict,
        unit: dict,
        question_id: str,
    ) -> dict | None:
        question = graph_state["question_catalog"]["question_index"].get(question_id)
        if not self._is_single_choice_question(question):
            return None

        existing_selection = self._normalize_single_choice_mapping(
            question,
            {
                "selected_options": list(unit.get("selected_options", [])),
                "input_value": str(unit.get("input_value", "")),
                "field_updates": dict(unit.get("field_updates", {})),
                "missing_fields": list(unit.get("missing_fields", [])),
            },
        )
        if existing_selection is not None:
            return {
                "question_id": question_id,
                **existing_selection,
            }

        current_question_id = str(graph_state["session_memory"].get("current_question_id") or "")
        winner_question_id = str(unit.get("winner_question_id") or "")
        candidate_question_ids = [
            str(candidate_question_id)
            for candidate_question_id in unit.get("candidate_question_ids", [])
            if str(candidate_question_id)
        ]
        mapped = map_content_answer(
            question,
            unit.get("raw_extracted_value", unit.get("unit_text", "")),
            raw_text=unit.get("unit_text", ""),
            allow_custom_empty_option_fallback=(
                question_id == current_question_id
                and (
                    winner_question_id == question_id
                    or candidate_question_ids == [question_id]
                )
            ),
        )
        normalized_mapped = self._normalize_single_choice_mapping(question, mapped)
        if normalized_mapped is not None:
            return {
                "question_id": question_id,
                **normalized_mapped,
            }

        llm_mapped = self._try_llm_option_mapping(
            graph_state,
            question,
            unit.get("unit_text", ""),
        )
        normalized_llm = self._normalize_single_choice_mapping(question, llm_mapped)
        if normalized_llm is None:
            return None
        return {
            "question_id": question_id,
            **normalized_llm,
        }

    def _normalize_single_choice_mapping(
        self,
        question: dict | None,
        mapped: dict | None,
    ) -> dict | None:
        if not self._is_single_choice_question(question) or not isinstance(mapped, dict):
            return None
        valid_option_ids = {
            str(option.get("option_id", ""))
            for option in question.get("options", [])
            if str(option.get("option_id", ""))
        }
        normalized_options = []
        for option_id in mapped.get("selected_options", []):
            normalized_option_id = str(option_id)
            if normalized_option_id and normalized_option_id in valid_option_ids:
                normalized_options.append(normalized_option_id)
        deduped_options: list[str] = []
        for option_id in normalized_options:
            if option_id not in deduped_options:
                deduped_options.append(option_id)
        if len(deduped_options) != 1:
            return None
        return {
            "selected_options": deduped_options,
            "input_value": str(mapped.get("input_value", "")),
            "field_updates": dict(mapped.get("field_updates", {})),
            "missing_fields": list(mapped.get("missing_fields", [])),
        }

    def _is_single_choice_question(self, question: dict | None) -> bool:
        if not isinstance(question, dict):
            return False
        input_type = str(question.get("input_type", "")).lower()
        if input_type in {"radio", "single", "select", "time_point"}:
            return True
        metadata = question.get("metadata", {})
        structured_kind = str(metadata.get("structured_kind", "")).lower()
        return structured_kind in {"radio", "single", "select", "single_choice"}

    def _looks_like_wake_text(self, unit_text: str) -> bool:
        if any(token in unit_text for token in ("起床", "醒", "早上", "早晨")):
            return True
        return bool(_WAKE_AFTER_TIME_PATTERN.search(unit_text))

    def _looks_like_sleep_text(self, unit_text: str) -> bool:
        return any(token in unit_text for token in ("睡", "入睡", "晚上", "夜里"))

    def _try_llm_option_mapping(
        self,
        graph_state: dict,
        question: dict,
        raw_text: str,
    ) -> dict | None:
        runtime = graph_state["runtime"]
        provider = runtime.get("llm_provider")
        if not runtime.get("llm_available", True) or provider is None:
            return None
        payload = {
            "question": question,
            "raw_text": raw_text,
            "matching_hints": list(question.get("metadata", {}).get("matching_hints", [])),
        }
        try:
            prompt_text = self._prompt_loader.render("layer2/text_option_mapping.md", payload)
            output = invoke_json(
                provider,
                prompt_key="layer2/text_option_mapping.md",
                prompt_text=prompt_text,
            )
        except Exception:
            return None
        selected_options = output.get("selected_options")
        if not isinstance(selected_options, list) or not selected_options:
            return None
        valid_option_ids = {
            str(option.get("option_id", ""))
            for option in question.get("options", [])
            if str(option.get("option_id", ""))
        }
        normalized_options = [
            str(option_id)
            for option_id in selected_options
            if str(option_id) in valid_option_ids
        ]
        deduped_options: list[str] = []
        for option_id in normalized_options:
            if option_id not in deduped_options:
                deduped_options.append(option_id)
        if self._is_single_choice_question(question):
            if len(deduped_options) != 1:
                return None
        elif not deduped_options:
            return None
        return {
            "selected_options": deduped_options,
            "input_value": self._custom_fallback_input_value(question, raw_text, deduped_options),
            "field_updates": {},
            "missing_fields": [],
        }

    def _custom_fallback_input_value(
        self,
        question: dict,
        raw_text: str,
        selected_options: list[str],
    ) -> str:
        if len(selected_options) != 1:
            return ""
        selected_option_id = selected_options[0]
        for option in question.get("options", []):
            option_id = str(option.get("option_id", "")).strip()
            if option_id != selected_option_id:
                continue
            option_text = str(option.get("option_text", option.get("label", ""))).strip()
            label = str(option.get("label", option.get("option_text", ""))).strip()
            if not option_text and not label:
                return raw_text.strip()
            return ""
        return ""

    def _log_diagnostic(self, event: str, **fields: object) -> None:
        payload = {
            "diagnostic": "content_understand",
            "event": event,
            **fields,
        }
        _DIAGNOSTIC_LOGGER.warning(json.dumps(payload, ensure_ascii=False, sort_keys=True))

    def _summarize_units(self, content_units: list[dict]) -> list[dict]:
        summary: list[dict] = []
        for unit in content_units:
            summary.append(
                {
                    "unit_id": unit.get("unit_id"),
                    "winner_question_id": unit.get("winner_question_id"),
                    "action_mode": unit.get("action_mode"),
                    "needs_attribution": bool(unit.get("needs_attribution", False)),
                    "selected_options": list(unit.get("selected_options", [])),
                    "field_updates": dict(unit.get("field_updates", {})),
                    "missing_fields": list(unit.get("missing_fields", [])),
                    "input_value": str(unit.get("input_value", "")),
                }
            )
        return summary
