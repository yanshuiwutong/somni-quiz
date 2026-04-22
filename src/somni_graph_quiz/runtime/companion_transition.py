"""Runtime transition step for companion-mode lifecycle."""

from __future__ import annotations

from copy import deepcopy
import json
import logging

from somni_graph_quiz.runtime.companion_decision import CompanionDecisionEngine
from somni_graph_quiz.runtime.companion_rules import (
    detect_continue_chat_intent,
    detect_distress_level,
    detect_entry_mode,
    has_strong_continue_chat_signal,
    is_explicit_return_to_quiz,
    looks_like_companion_chat,
)

_DIAGNOSTIC_LOGGER = logging.getLogger("somni_graph_quiz.diagnostics.companion_transition")


class CompanionTransition:
    """Apply companion lifecycle decisions onto a branch result."""

    _CONTROL_OR_TOOL_NON_CONTENT_INTENTS = {
        "weather_query",
        "navigate_next",
        "navigate_previous",
        "skip",
        "undo",
        "view_all",
        "view_current",
        "view_previous",
        "view_next",
        "modify_previous",
    }

    def __init__(self, decision_engine: CompanionDecisionEngine | None = None) -> None:
        self._decision_engine = decision_engine or CompanionDecisionEngine()

    def apply(self, graph_state: dict, turn_input: object, branch_result: dict) -> dict:
        raw_input = getattr(turn_input, "raw_input", "")
        session_memory = graph_state["session_memory"]
        companion_context = deepcopy(session_memory.get("companion_context") or self._empty_context())
        response_facts = dict(branch_result.get("response_facts", {}))
        state_patch = deepcopy(branch_result.get("state_patch", {}))
        state_patch.setdefault("session_memory", {})
        applied_question_ids = list(branch_result.get("applied_question_ids", []))
        current_question_id = session_memory.get("current_question_id")
        active_companion_at_turn_start = bool(companion_context.get("active"))
        answered_current_question = bool(current_question_id and current_question_id in applied_question_ids)
        companion_owned = False
        companion_recent_turns = self._recent_turn_summaries(session_memory.get("recent_turns", []))
        decision = None
        if self._should_consider_companion_decision(
            graph_state=graph_state,
            raw_input=raw_input,
            branch_result=branch_result,
            companion_context=companion_context,
        ):
            decision = self._decision_engine.decide(
                graph_state=graph_state,
                raw_input=raw_input,
                branch_result=branch_result,
                companion_context=companion_context,
                companion_recent_turns=companion_recent_turns,
            )
            decision = self._apply_distress_guardrail_if_needed(
                graph_state=graph_state,
                raw_input=raw_input,
                branch_result=branch_result,
                companion_context=companion_context,
                decision=decision,
            )

        if decision is not None:
            decision = self._apply_runtime_constraints(
                graph_state=graph_state,
                raw_input=raw_input,
                branch_result=branch_result,
                companion_context=companion_context,
                decision=decision,
            )
            companion_context, response_facts, companion_owned = self._apply_llm_decision(
                companion_context=companion_context,
                raw_input=raw_input,
                response_facts=response_facts,
                branch_result=branch_result,
                applied_question_ids=applied_question_ids,
                current_question_id=current_question_id,
                entered_from_question_id=session_memory.get("current_question_id"),
                companion_recent_turns=companion_recent_turns,
                decision=decision,
            )
        else:
            companion_context, response_facts, companion_owned = self._apply_rule_decision(
                graph_state=graph_state,
                raw_input=raw_input,
                companion_context=companion_context,
                response_facts=response_facts,
                branch_result=branch_result,
                applied_question_ids=applied_question_ids,
                current_question_id=current_question_id,
                companion_recent_turns=companion_recent_turns,
            )

        if companion_owned:
            response_facts.setdefault("companion_mode", companion_context.get("mode"))
            distress_level = detect_distress_level(raw_input)
            if companion_context.get("mode") == "supportive" and distress_level != "none":
                response_facts["companion_distress_level"] = distress_level
            if response_facts.get("companion_recorded_exit") or response_facts.get("companion_completion_wrapup") or (
                active_companion_at_turn_start
                and companion_owned
                and answered_current_question
                and not response_facts.get("stay_in_companion")
                and not response_facts.get("return_to_quiz")
                and not response_facts.get("companion_soft_return_to_quiz")
            ):
                response_facts.pop("answer_status_override", None)
            else:
                response_facts["answer_status_override"] = "NOT_RECORDED"
            response_facts["silent_recorded_question_ids"] = applied_question_ids
            response_facts["silent_modified_question_ids"] = list(branch_result.get("modified_question_ids", []))
            if decision is not None and decision.get("answer_status_override") is None:
                response_facts.pop("answer_status_override", None)
            response_facts["companion_recent_turns"] = companion_recent_turns

        state_patch["session_memory"]["companion_context"] = companion_context
        return {
            **branch_result,
            "state_patch": state_patch,
            "response_facts": response_facts,
        }

    def _apply_runtime_constraints(
        self,
        *,
        graph_state: dict,
        raw_input: str,
        branch_result: dict,
        companion_context: dict,
        decision: dict,
    ) -> dict:
        single_success_eval = self._evaluate_single_success_unit(
            raw_input=raw_input,
            branch_result=branch_result,
            decision=decision,
        )
        if not companion_context.get("active"):
            if single_success_eval["should_exit"]:
                self._log_transition_diagnostic(
                    "inactive_single_success_suppressed",
                    raw_input=raw_input,
                    **single_success_eval,
                    llm_companion_action=decision.get("companion_action"),
                    llm_continue_chat_intent=decision.get("continue_chat_intent"),
                )
                return self._inactive_noop_decision(reason="single_success_unit_without_active_companion")
            if decision.get("companion_action") == "exit":
                self._log_transition_diagnostic(
                    "inactive_exit_suppressed",
                    raw_input=raw_input,
                    **single_success_eval,
                    llm_companion_action=decision.get("companion_action"),
                    llm_continue_chat_intent=decision.get("continue_chat_intent"),
                )
                return self._inactive_noop_decision(reason="inactive_companion_cannot_exit")
            return decision

        current_mode = companion_context.get("mode")
        applied_question_ids = list(branch_result.get("applied_question_ids", []))
        current_question_id = graph_state["session_memory"].get("current_question_id")
        if self._should_force_main_flow_exit(graph_state, branch_result):
            return {
                "companion_action": "exit",
                "companion_mode": None,
                "answer_status_override": None,
                "reason": "force_main_flow_exit",
                "overlay_action": "main_flow",
                "preserved_companion_mode": current_mode,
            }
        if is_explicit_return_to_quiz(raw_input):
            return {
                "companion_action": "exit",
                "companion_mode": None,
                "answer_status_override": "NOT_RECORDED",
                "reason": "explicit_return_to_quiz",
                "overlay_action": "return_to_quiz",
                "preserved_companion_mode": current_mode,
            }
        if self._has_successful_recording(branch_result) and self._should_keep_companion_after_answer(
            raw_input=raw_input,
            graph_state=graph_state,
            branch_result=branch_result,
            decision=decision,
        ):
            constrained = dict(decision)
            constrained["companion_action"] = "stay"
            constrained["companion_mode"] = decision.get("companion_mode") or current_mode
            constrained["answer_status_override"] = "NOT_RECORDED"
            constrained["continue_chat_intent"] = self._continue_chat_intent(
                decision=decision,
                raw_input=raw_input,
            )
            if constrained["continue_chat_intent"] == "strong":
                constrained["reset_round_counter"] = True
            constrained["reason"] = (
                "answered_current_question_with_companion_chat"
                if current_question_id and current_question_id in applied_question_ids
                else "silent_recorded_answer_keeps_companion"
            )
            return constrained
        if single_success_eval["should_exit"]:
            self._log_transition_diagnostic(
                "active_single_success_exit",
                raw_input=raw_input,
                **single_success_eval,
                llm_companion_action=decision.get("companion_action"),
                llm_continue_chat_intent=decision.get("continue_chat_intent"),
            )
            overlay_action = (
                "completion_wrapup"
                if self._turn_completes_questionnaire(graph_state, branch_result)
                else "none"
            )
            return {
                "companion_action": "exit",
                "companion_mode": None,
                "answer_status_override": None,
                "reason": "single_success_unit_answered",
                "overlay_action": overlay_action,
                "preserved_companion_mode": current_mode,
                "recorded_exit": True,
            }
        if current_question_id and current_question_id in applied_question_ids:
            overlay_action = (
                "completion_wrapup"
                if self._turn_completes_questionnaire(graph_state, branch_result)
                else "none"
            )
            return {
                "companion_action": "exit",
                "companion_mode": None,
                "answer_status_override": None,
                "reason": "answered_current_question",
                "overlay_action": overlay_action,
                "preserved_companion_mode": current_mode,
            }

        intent = self._continue_chat_intent(decision=decision, raw_input=raw_input)
        effective_mode = decision.get("companion_mode") or current_mode
        if intent == "strong":
            constrained = dict(decision)
            constrained["companion_action"] = "stay"
            constrained["companion_mode"] = effective_mode
            constrained["answer_status_override"] = "NOT_RECORDED"
            constrained["reset_round_counter"] = True
            constrained["continue_chat_intent"] = "strong"
            return constrained

        if decision.get("companion_action") != "stay":
            return decision

        next_round = int(companion_context.get("rounds_since_enter", 0)) + 1
        if effective_mode in {"supportive", "smalltalk"} and intent == "strong":
            constrained = dict(decision)
            constrained["reset_round_counter"] = True
            return constrained
        if effective_mode == "smalltalk" and next_round >= 2:
            return {
                "companion_action": "exit",
                "companion_mode": None,
                "answer_status_override": "NOT_RECORDED",
                "reason": "smalltalk_threshold_exit",
                "overlay_action": "soft_return_to_quiz",
                "preserved_companion_mode": current_mode,
            }
        if effective_mode == "supportive" and next_round >= 4:
            return {
                "companion_action": "exit",
                "companion_mode": None,
                "answer_status_override": "NOT_RECORDED",
                "reason": "supportive_threshold_exit",
                "overlay_action": "soft_return_to_quiz",
                "preserved_companion_mode": current_mode,
            }
        return decision

    def _should_force_main_flow_exit(self, graph_state: dict, branch_result: dict) -> bool:
        if graph_state["turn"].get("main_branch", "content") != "non_content":
            return False
        non_content_intent = self._resolved_non_content_intent(graph_state, branch_result)
        return non_content_intent in self._CONTROL_OR_TOOL_NON_CONTENT_INTENTS

    def _turn_completes_questionnaire(self, graph_state: dict, branch_result: dict) -> bool:
        answered_question_ids = list(
            branch_result.get("state_patch", {})
            .get("session_memory", {})
            .get("answered_question_ids", graph_state["session_memory"].get("answered_question_ids", []))
        )
        question_count = len(graph_state["question_catalog"].get("question_order", []))
        return question_count > 0 and len(answered_question_ids) == question_count

    def _apply_distress_guardrail_if_needed(
        self,
        *,
        graph_state: dict,
        raw_input: str,
        branch_result: dict,
        companion_context: dict,
        decision: dict | None,
    ) -> dict | None:
        distress_level = detect_distress_level(raw_input)
        if distress_level == "none":
            return decision
        if decision is None:
            return decision
        if decision.get("companion_action") != "none":
            return decision
        if not self._is_distress_companion_eligible(graph_state, branch_result, companion_context):
            return decision
        return {
            "companion_action": "stay" if companion_context.get("active") else "enter",
            "companion_mode": "supportive",
            "answer_status_override": "NOT_RECORDED",
            "reason": f"distress_guardrail_{distress_level}",
        }

    def _is_distress_companion_eligible(
        self,
        graph_state: dict,
        branch_result: dict,
        companion_context: dict,
    ) -> bool:
        if companion_context.get("active"):
            return True
        non_content_intent = self._resolved_non_content_intent(graph_state, branch_result)
        if non_content_intent == "pullback_chat":
            return True
        if graph_state["turn"].get("main_branch", "content") != "content":
            return False
        return bool(
            branch_result.get("applied_question_ids")
            or branch_result.get("modified_question_ids")
            or branch_result.get("partial_question_ids")
        )

    def _should_consider_companion_decision(
        self,
        *,
        graph_state: dict,
        raw_input: str,
        branch_result: dict,
        companion_context: dict,
    ) -> bool:
        non_content_intent = self._resolved_non_content_intent(graph_state, branch_result)
        if companion_context.get("active"):
            if non_content_intent in self._CONTROL_OR_TOOL_NON_CONTENT_INTENTS:
                return False
            return True
        if non_content_intent in {"pullback_chat", "identity"}:
            return True
        if graph_state["turn"].get("main_branch", "content") != "content":
            return False
        has_question_activity = bool(
            branch_result.get("applied_question_ids")
            or branch_result.get("modified_question_ids")
            or branch_result.get("partial_question_ids")
        )
        if has_question_activity:
            return True
        return looks_like_companion_chat(raw_input)

    def _apply_llm_decision(
        self,
        *,
        companion_context: dict,
        raw_input: str,
        response_facts: dict,
        branch_result: dict,
        applied_question_ids: list[str],
        current_question_id: str | None,
        entered_from_question_id: str | None,
        companion_recent_turns: list[dict],
        decision: dict,
    ) -> tuple[dict, dict, bool]:
        action = decision["companion_action"]
        mode = decision["companion_mode"]
        answer_status_override = decision["answer_status_override"]
        overlay_action = decision.get("overlay_action", "return_to_quiz")

        if action == "none":
            return companion_context, response_facts, False

        if action == "enter":
            companion_context = {
                "active": True,
                "mode": mode,
                "entered_from_question_id": entered_from_question_id,
                "rounds_since_enter": 0,
                "last_turn_continue_chat_intent": self._continue_chat_intent(decision=decision, raw_input=raw_input),
                "last_trigger_reason": decision["reason"],
            }
            response_facts["stay_in_companion"] = True
        elif action == "stay":
            continue_chat_intent = self._continue_chat_intent(decision=decision, raw_input=raw_input)
            rounds_since_enter = (
                0
                if decision.get("reset_round_counter")
                else int(companion_context.get("rounds_since_enter", 0)) + 1
            )
            companion_context = {
                **(companion_context or self._empty_context()),
                "active": True,
                "mode": mode,
                "entered_from_question_id": companion_context.get("entered_from_question_id") or entered_from_question_id,
                "rounds_since_enter": rounds_since_enter,
                "last_turn_continue_chat_intent": continue_chat_intent,
                "last_trigger_reason": decision["reason"],
            }
            response_facts["stay_in_companion"] = True
        else:
            preserved_mode = decision.get("preserved_companion_mode")
            companion_context = self._empty_context()
            if overlay_action == "return_to_quiz":
                response_facts["return_to_quiz"] = True
            elif overlay_action == "soft_return_to_quiz":
                response_facts["companion_soft_return_to_quiz"] = True
            elif overlay_action == "main_flow":
                response_facts["companion_force_main_flow"] = True
            elif overlay_action == "completion_wrapup":
                response_facts["companion_completion_wrapup"] = True
            if preserved_mode and overlay_action != "none":
                response_facts["companion_mode"] = preserved_mode
            if decision.get("recorded_exit"):
                response_facts["companion_recorded_exit"] = True

        if answer_status_override is not None:
            response_facts["answer_status_override"] = answer_status_override
        if action in {"enter", "stay", "exit"}:
            response_facts["silent_recorded_question_ids"] = applied_question_ids
            response_facts["silent_modified_question_ids"] = list(branch_result.get("modified_question_ids", []))
            response_facts["companion_recent_turns"] = companion_recent_turns
            response_facts["continue_chat_intent"] = self._continue_chat_intent(decision=decision, raw_input=raw_input)
        if (
            action == "exit"
            and overlay_action in {"return_to_quiz", "soft_return_to_quiz"}
            and current_question_id
            and current_question_id in applied_question_ids
        ):
            response_facts["companion_soft_return_to_quiz"] = True
        return companion_context, response_facts, True

    def _apply_rule_decision(
        self,
        *,
        graph_state: dict,
        raw_input: str,
        companion_context: dict,
        response_facts: dict,
        branch_result: dict,
        applied_question_ids: list[str],
        current_question_id: str | None,
        companion_recent_turns: list[dict],
    ) -> tuple[dict, dict, bool]:
        companion_owned = False

        if companion_context.get("active"):
            intent = detect_continue_chat_intent(raw_input)
            next_round = int(companion_context.get("rounds_since_enter", 0)) + 1
            preserved_mode = companion_context.get("mode")

            if self._should_force_main_flow_exit(graph_state, branch_result):
                companion_context = self._empty_context()
                response_facts["companion_force_main_flow"] = True
                companion_owned = True
            elif is_explicit_return_to_quiz(raw_input):
                companion_context = self._empty_context()
                response_facts["return_to_quiz"] = True
                response_facts["companion_mode"] = preserved_mode
                companion_owned = True
            elif self._has_successful_recording(branch_result) and self._should_keep_companion_after_answer(
                raw_input=raw_input,
                graph_state=graph_state,
                branch_result=branch_result,
                decision=None,
            ):
                intent = detect_continue_chat_intent(raw_input)
                companion_context["last_turn_continue_chat_intent"] = intent
                companion_context["rounds_since_enter"] = 0 if intent == "strong" else next_round
                response_facts["stay_in_companion"] = True
                response_facts["continue_chat_intent"] = intent
                companion_owned = True
            elif self._should_exit_for_single_success_unit(
                raw_input=raw_input,
                branch_result=branch_result,
                decision=None,
            ):
                companion_context = self._empty_context()
                response_facts["companion_recorded_exit"] = True
                if self._turn_completes_questionnaire(graph_state, branch_result):
                    response_facts["companion_mode"] = preserved_mode
                    response_facts["companion_completion_wrapup"] = True
                companion_owned = True
            elif current_question_id and current_question_id in applied_question_ids:
                companion_context = self._empty_context()
                if self._turn_completes_questionnaire(graph_state, branch_result):
                    response_facts["companion_mode"] = preserved_mode
                    response_facts["companion_completion_wrapup"] = True
                    response_facts.pop("answer_status_override", None)
                companion_owned = True
            elif companion_context.get("mode") in {"supportive", "smalltalk"} and intent == "strong":
                companion_context["last_turn_continue_chat_intent"] = intent
                companion_context["rounds_since_enter"] = 0
                response_facts["stay_in_companion"] = True
                companion_owned = True
            elif companion_context.get("mode") == "supportive" and next_round >= 4:
                companion_context = self._empty_context()
                response_facts["companion_soft_return_to_quiz"] = True
                response_facts["companion_mode"] = preserved_mode
                response_facts["continue_chat_intent"] = intent
                companion_owned = True
            elif companion_context.get("mode") == "smalltalk" and next_round >= 2:
                companion_context = self._empty_context()
                response_facts["companion_soft_return_to_quiz"] = True
                response_facts["companion_mode"] = preserved_mode
                response_facts["continue_chat_intent"] = intent
                companion_owned = True
            else:
                companion_context["last_turn_continue_chat_intent"] = intent
                companion_context["rounds_since_enter"] = next_round
                response_facts["stay_in_companion"] = True
                response_facts["continue_chat_intent"] = intent
                companion_owned = True
        else:
            mode = detect_entry_mode(
                raw_input=raw_input,
                main_branch=graph_state["turn"].get("main_branch", "content"),
                non_content_intent=self._resolved_non_content_intent(graph_state, branch_result),
                applied_question_ids=applied_question_ids,
                modified_question_ids=list(branch_result.get("modified_question_ids", [])),
                partial_question_ids=list(branch_result.get("partial_question_ids", [])),
            )
            if (
                mode is None
                and graph_state["turn"].get("main_branch", "content") == "content"
                and not (
                    applied_question_ids
                    or branch_result.get("modified_question_ids")
                    or branch_result.get("partial_question_ids")
                )
                and looks_like_companion_chat(raw_input)
            ):
                mode = "supportive" if detect_distress_level(raw_input) != "none" else "smalltalk"
            if mode is not None:
                companion_context = {
                    "active": True,
                    "mode": mode,
                    "entered_from_question_id": graph_state["session_memory"].get("current_question_id"),
                    "rounds_since_enter": 0,
                    "last_turn_continue_chat_intent": None,
                    "last_trigger_reason": "distress" if mode == "supportive" else mode,
                }
                response_facts["stay_in_companion"] = True
                response_facts["continue_chat_intent"] = detect_continue_chat_intent(raw_input)
                companion_owned = True
        response_facts["companion_recent_turns"] = companion_recent_turns
        return companion_context, response_facts, companion_owned

    def _resolved_non_content_intent(self, graph_state: dict, branch_result: dict) -> str:
        response_facts = branch_result.get("response_facts", {})
        if response_facts.get("non_content_mode") == "weather":
            return "weather_query"
        action = str(response_facts.get("control_action") or response_facts.get("non_content_action") or "")
        if action in self._CONTROL_OR_TOOL_NON_CONTENT_INTENTS:
            return action
        if response_facts.get("pullback_reason") == "identity_question":
            return "identity"
        if response_facts.get("non_content_mode") == "pullback":
            return "pullback_chat"
        turn_intent = graph_state["turn"].get("non_content_intent", "none")
        if turn_intent in self._CONTROL_OR_TOOL_NON_CONTENT_INTENTS | {"identity", "pullback_chat"}:
            return turn_intent
        return "none"

    def _should_keep_companion_after_answer(
        self,
        *,
        raw_input: str,
        graph_state: dict,
        branch_result: dict,
        decision: dict | None,
    ) -> bool:
        if not self._has_successful_recording(branch_result):
            return False
        if self._turn_completes_questionnaire(graph_state, branch_result):
            return False
        current_question_id = graph_state["session_memory"].get("current_question_id")
        applied_question_ids = list(branch_result.get("applied_question_ids", []))
        current_question_answered = bool(current_question_id and current_question_id in applied_question_ids)
        if has_strong_continue_chat_signal(raw_input):
            return True
        if current_question_answered:
            return False
        if (
            decision is not None
            and decision.get("companion_action") in {"enter", "stay"}
            and decision.get("continue_chat_intent") == "strong"
        ):
            return True
        return bool(graph_state["session_memory"].get("companion_context", {}).get("active"))

    def _should_exit_for_single_success_unit(
        self,
        *,
        raw_input: str,
        branch_result: dict,
        decision: dict | None,
    ) -> bool:
        return self._evaluate_single_success_unit(
            raw_input=raw_input,
            branch_result=branch_result,
            decision=decision,
        )["should_exit"]

    def _has_successful_recording(self, branch_result: dict) -> bool:
        return bool(
            branch_result.get("applied_question_ids")
            or branch_result.get("modified_question_ids")
            or branch_result.get("partial_question_ids")
        )

    def _evaluate_single_success_unit(
        self,
        *,
        raw_input: str,
        branch_result: dict,
        decision: dict | None,
    ) -> dict:
        content_unit_count = branch_result.get("response_facts", {}).get("content_unit_count")
        success_count = (
            len(branch_result.get("applied_question_ids", []))
            + len(branch_result.get("modified_question_ids", []))
            + len(branch_result.get("partial_question_ids", []))
        )
        distress_level = detect_distress_level(raw_input)
        strong_continue_chat_signal = has_strong_continue_chat_signal(raw_input)
        rejected_unit_ids_present = bool(branch_result.get("rejected_unit_ids"))
        llm_strong_continue_chat = bool(
            decision is not None
            and decision.get("companion_action") in {"enter", "stay"}
            and decision.get("continue_chat_intent") == "strong"
        )
        effective_content_unit_count = (
            content_unit_count
            if isinstance(content_unit_count, int) and content_unit_count > 0
            else success_count if success_count == 1 and not rejected_unit_ids_present else content_unit_count
        )
        should_exit = (
            effective_content_unit_count == 1
            and not rejected_unit_ids_present
            and success_count == 1
            and distress_level == "none"
            and not strong_continue_chat_signal
        )
        return {
            "content_unit_count": content_unit_count,
            "effective_content_unit_count": effective_content_unit_count,
            "success_count": success_count,
            "rejected_unit_ids_present": rejected_unit_ids_present,
            "distress_level": distress_level,
            "looks_like_companion_chat": looks_like_companion_chat(raw_input),
            "strong_continue_chat_signal": strong_continue_chat_signal,
            "llm_strong_continue_chat": llm_strong_continue_chat,
            "should_exit": should_exit,
        }

    def _continue_chat_intent(self, *, decision: dict | None, raw_input: str) -> str:
        rule_intent = detect_continue_chat_intent(raw_input)
        if rule_intent == "strong":
            return "strong"
        if decision is not None:
            candidate = decision.get("continue_chat_intent")
            if candidate in {"strong", "weak", "none"}:
                return candidate
        return rule_intent

    def _empty_context(self) -> dict:
        return {
            "active": False,
            "mode": None,
            "entered_from_question_id": None,
            "rounds_since_enter": 0,
            "last_turn_continue_chat_intent": None,
            "last_trigger_reason": None,
        }

    def _inactive_noop_decision(self, *, reason: str) -> dict:
        return {
            "companion_action": "none",
            "companion_mode": None,
            "continue_chat_intent": "none",
            "answer_status_override": None,
            "reason": reason,
        }

    def _recent_turn_summaries(self, recent_turns: object) -> list[dict]:
        if not isinstance(recent_turns, list):
            return []
        summaries: list[dict] = []
        for turn in recent_turns[-3:]:
            if not isinstance(turn, dict):
                continue
            raw_input = str(turn.get("raw_input", "")).strip()
            if not raw_input:
                continue
            summaries.append(
                {
                    "raw_input": raw_input,
                    "turn_outcome": str(turn.get("turn_outcome", "")),
                    "main_branch": str(turn.get("main_branch", "")),
                    "assistant_mode": turn.get("assistant_mode"),
                    "assistant_topic": turn.get("assistant_topic"),
                    "assistant_followup_kind": turn.get("assistant_followup_kind"),
                    "assistant_pullback_anchor": turn.get("assistant_pullback_anchor"),
                }
            )
        return summaries

    def _log_transition_diagnostic(self, event: str, **fields: object) -> None:
        payload = {
            "diagnostic": "companion_transition",
            "event": event,
            **fields,
        }
        _DIAGNOSTIC_LOGGER.warning(json.dumps(payload, ensure_ascii=False, sort_keys=True))
