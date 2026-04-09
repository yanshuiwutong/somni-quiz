"""Content apply node."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy

from somni_graph_quiz.contracts.node_contracts import create_branch_result
from somni_graph_quiz.nodes.layer2.content.mapping import map_content_value
from somni_graph_quiz.utils.time_parse import build_time_range_input_value


class ContentApplyNode:
    """Apply resolved content units into session memory patches."""

    def run(
        self,
        graph_state: dict,
        content_units: list[dict],
        clarification_needed: bool = False,
        clarification_details: dict | None = None,
    ) -> dict:
        if clarification_needed:
            return self._handle_clarification(graph_state, clarification_details or {})

        session_memory = graph_state["session_memory"]
        answered_records = deepcopy(session_memory["answered_records"])
        pending_partial_answers = deepcopy(session_memory["pending_partial_answers"])
        answered_question_ids = list(session_memory["answered_question_ids"])
        partial_question_ids = list(session_memory["partial_question_ids"])
        skipped_question_ids = list(session_memory["skipped_question_ids"])
        unanswered_question_ids = list(session_memory["unanswered_question_ids"])
        pending_question_ids = list(session_memory["pending_question_ids"])
        question_states = deepcopy(session_memory["question_states"])
        previous_answer_record: dict[str, dict] = {}
        applied_question_ids: list[str] = []
        modified_question_ids: list[str] = []
        partial_ids: list[str] = []
        rejected_unit_ids: list[str] = []
        current_question_id = session_memory["current_question_id"]
        clarification_context = deepcopy(session_memory["clarification_context"])
        response_facts: dict = {}

        duplicate_question_ids = {
            question_id
            for question_id, count in Counter(
                unit.get("winner_question_id")
                for unit in content_units
                if unit.get("winner_question_id")
            ).items()
            if count > 1
        }

        if duplicate_question_ids:
            response_facts["clarification_reason"] = "same_question_conflict"

        for unit in content_units:
            question_id = unit.get("winner_question_id")
            if not question_id:
                rejected_unit_ids.append(unit["unit_id"])
                response_facts.setdefault("clarification_reason", "missing_winner")
                self._set_clarification_target(response_facts, graph_state, None, "question_not_identified")
                continue
            if question_id in duplicate_question_ids:
                rejected_unit_ids.append(unit["unit_id"])
                continue

            action_mode = unit["action_mode"]
            question = graph_state["question_catalog"]["question_index"][question_id]
            question_status = question_states[question_id]["status"]
            if action_mode == "answer" and question_status == "answered":
                action_mode = "modify"
            has_pending_partial = question_id in pending_partial_answers
            if not self._is_valid_action_mode(action_mode, question_status, has_pending_partial):
                rejected_unit_ids.append(unit["unit_id"])
                response_facts.setdefault("clarification_reason", "invalid_action_mode_for_state")
                self._set_clarification_target(response_facts, graph_state, question_id, "invalid_action_mode_for_state")
                continue

            mapped = self._mapped_payload(unit, question_id)

            if question_id == "question-02":
                outcome = self._apply_schedule(
                    question_id=question_id,
                    action_mode=action_mode,
                    mapped=mapped,
                    answered_records=answered_records,
                    pending_partial_answers=pending_partial_answers,
                    partial_question_ids=partial_question_ids,
                    question_states=question_states,
                )
                if outcome["status"] == "rejected":
                    rejected_unit_ids.append(unit["unit_id"])
                    response_facts.setdefault("clarification_reason", outcome["reason"])
                    self._set_clarification_target(
                        response_facts,
                        graph_state,
                        question_id,
                        "partial_missing_fields" if outcome["reason"] == "invalid_time_value" else outcome["reason"],
                    )
                    continue
                if outcome["status"] == "partial":
                    if question_id in skipped_question_ids:
                        skipped_question_ids.remove(question_id)
                    if question_id not in partial_ids:
                        partial_ids.append(question_id)
                    response_facts["missing_fields_by_question"] = {
                        question_id: pending_partial_answers[question_id]["missing_fields"]
                    }
                    current_question_id = question_id
                    clarification_context = self._build_clarification_context(
                        graph_state,
                        question_id,
                        "partial_missing_fields",
                    )
                    continue
                if action_mode == "modify":
                    previous_answer_record[question_id] = deepcopy(answered_records[question_id])
                    modified_question_ids.append(question_id)
                else:
                    applied_question_ids.append(question_id)
                if question_id in skipped_question_ids:
                    skipped_question_ids.remove(question_id)
            else:
                if not self._is_valid_mapped_answer(question, mapped):
                    rejected_unit_ids.append(unit["unit_id"])
                    response_facts.setdefault("clarification_reason", "invalid_answer_value")
                    self._set_clarification_target(
                        response_facts,
                        graph_state,
                        question_id,
                        "question_identified_option_not_identified",
                    )
                    continue
                if action_mode == "modify":
                    previous_answer_record[question_id] = deepcopy(answered_records[question_id])
                    modified_question_ids.append(question_id)
                else:
                    applied_question_ids.append(question_id)
                if question_id in skipped_question_ids:
                    skipped_question_ids.remove(question_id)
                if question.get("input_type") == "text" and not question.get("options"):
                    answered_records[question_id] = {
                        "question_id": question_id,
                        "selected_options": [],
                        "input_value": str(unit.get("raw_extracted_value", unit["unit_text"])),
                        "field_updates": {},
                    }
                else:
                    answered_records[question_id] = {
                        "question_id": question_id,
                        "selected_options": list(mapped.get("selected_options", [])),
                        "input_value": mapped.get("input_value", ""),
                        "field_updates": {},
                    }
                question_states[question_id] = {
                    "status": "answered",
                    "attempt_count": 0,
                    "last_action_mode": action_mode,
                }

            if question_id not in answered_question_ids:
                answered_question_ids.append(question_id)
            if question_id in unanswered_question_ids:
                unanswered_question_ids.remove(question_id)
            if question_id in partial_question_ids:
                partial_question_ids.remove(question_id)
            if question_id in pending_question_ids:
                pending_question_ids.remove(question_id)
            current_question_id = pending_question_ids[0] if pending_question_ids else None

        progress_made = bool(applied_question_ids or modified_question_ids or partial_ids)
        pending_modify_context = session_memory["pending_modify_context"]
        if progress_made:
            pending_modify_context = None
        if applied_question_ids or modified_question_ids:
            clarification_context = None

        return create_branch_result(
            branch_type="content",
            state_patch={
                "session_memory": {
                    "answered_records": answered_records,
                    "pending_partial_answers": pending_partial_answers,
                    "answered_question_ids": answered_question_ids,
                    "partial_question_ids": partial_question_ids,
                    "skipped_question_ids": skipped_question_ids,
                    "unanswered_question_ids": unanswered_question_ids,
                    "pending_question_ids": pending_question_ids,
                    "current_question_id": current_question_id,
                    "question_states": question_states,
                    "previous_answer_record": previous_answer_record or None,
                    "pending_modify_context": pending_modify_context,
                    "clarification_context": clarification_context,
                }
            },
            applied_question_ids=applied_question_ids,
            modified_question_ids=modified_question_ids,
            partial_question_ids=partial_ids,
            rejected_unit_ids=rejected_unit_ids,
            clarification_needed=bool(rejected_unit_ids) and not progress_made,
            response_facts=response_facts | {
                "recorded_question_ids": applied_question_ids,
                "modified_question_ids": modified_question_ids,
                "partial_question_ids": partial_ids,
            },
        )

    def _handle_clarification(self, graph_state: dict, clarification_details: dict) -> dict:
        session_memory = graph_state["session_memory"]
        current_question_id = session_memory["current_question_id"]
        question_states = deepcopy(session_memory["question_states"])
        skipped_question_ids = list(session_memory["skipped_question_ids"])
        pending_question_ids = list(session_memory["pending_question_ids"])
        current_attempt = 0
        if current_question_id:
            current_attempt = question_states[current_question_id]["attempt_count"] + 1
            current_status = question_states[current_question_id]["status"]
            if current_attempt >= 2 and current_status in {"partial", "unanswered"}:
                question_states[current_question_id] = {
                    "status": "skipped",
                    "attempt_count": current_attempt,
                    "last_action_mode": question_states[current_question_id]["last_action_mode"],
                }
                if current_question_id not in skipped_question_ids:
                    skipped_question_ids.append(current_question_id)
                pending_question_ids = [
                    question_id
                    for question_id in pending_question_ids
                    if question_id != current_question_id
                ]
                next_question_id = pending_question_ids[0] if pending_question_ids else None
                return create_branch_result(
                    branch_type="content",
                    state_patch={
                        "session_memory": {
                            "answered_records": deepcopy(session_memory["answered_records"]),
                            "question_states": question_states,
                            "skipped_question_ids": skipped_question_ids,
                            "pending_question_ids": pending_question_ids,
                            "current_question_id": next_question_id,
                            "pending_partial_answers": deepcopy(session_memory["pending_partial_answers"]),
                            "partial_question_ids": list(session_memory["partial_question_ids"]),
                            "clarification_context": None,
                        }
                    },
                    skipped_question_ids=[current_question_id],
                    response_facts={"clarification_reason": "auto_skip_after_retries"},
                )
            question_states[current_question_id] = {
                "status": current_status,
                "attempt_count": current_attempt,
                "last_action_mode": question_states[current_question_id]["last_action_mode"],
            }
        response_facts = {
            "clarification_reason": clarification_details.get("clarification_reason", "content_understand"),
        }
        target_question_id = clarification_details.get("clarification_question_id") or current_question_id
        clarification_kind = clarification_details.get("clarification_kind") or response_facts["clarification_reason"]
        self._set_clarification_target(
            response_facts,
            graph_state,
            target_question_id,
            clarification_kind,
            title=clarification_details.get("clarification_question_title"),
        )
        return create_branch_result(
            branch_type="content",
            state_patch={
                "session_memory": {
                    "answered_records": deepcopy(session_memory["answered_records"]),
                    "question_states": question_states,
                    "clarification_context": self._build_clarification_context(
                        graph_state,
                        target_question_id,
                        clarification_kind,
                        title=clarification_details.get("clarification_question_title"),
                    ),
                }
            },
            clarification_needed=True,
            response_facts=response_facts,
        )

    def _apply_schedule(
        self,
        *,
        question_id: str,
        action_mode: str,
        mapped: dict,
        answered_records: dict,
        pending_partial_answers: dict,
        partial_question_ids: list[str],
        question_states: dict,
    ) -> dict:
        if not mapped.get("filled_fields"):
            return {"status": "rejected", "reason": "invalid_time_value"}
        if action_mode == "partial_completion":
            existing = pending_partial_answers.get(question_id, {
                "question_id": question_id,
                "filled_fields": {},
                "missing_fields": ["bedtime", "wake_time"],
                "source_question_state": "partial",
            })
            merged = {**existing["filled_fields"], **mapped["filled_fields"]}
            missing_fields = [field for field in ("bedtime", "wake_time") if field not in merged]
            if missing_fields:
                pending_partial_answers[question_id] = {
                    "question_id": question_id,
                    "filled_fields": merged,
                    "missing_fields": missing_fields,
                    "source_question_state": "partial",
                }
                if question_id not in partial_question_ids:
                    partial_question_ids.append(question_id)
                question_states[question_id] = {
                    "status": "partial",
                    "attempt_count": 0,
                    "last_action_mode": "partial_completion",
                }
                return {"status": "partial"}
            answered_records[question_id] = {
                "question_id": question_id,
                "selected_options": [],
                "input_value": build_time_range_input_value(merged),
                "field_updates": merged,
            }
            pending_partial_answers.pop(question_id, None)
            question_states[question_id] = {
                "status": "answered",
                "attempt_count": 0,
                "last_action_mode": action_mode,
            }
            return {"status": "answered"}

        if mapped["missing_fields"]:
            pending_partial_answers[question_id] = {
                "question_id": question_id,
                "filled_fields": mapped["filled_fields"],
                "missing_fields": mapped["missing_fields"],
                "source_question_state": "partial",
            }
            if question_id not in partial_question_ids:
                partial_question_ids.append(question_id)
            question_states[question_id] = {
                "status": "partial",
                "attempt_count": 0,
                "last_action_mode": action_mode,
            }
            return {"status": "partial"}

        answered_records[question_id] = {
            "question_id": question_id,
            "selected_options": [],
            "input_value": build_time_range_input_value(mapped["filled_fields"]),
            "field_updates": mapped["filled_fields"],
        }
        pending_partial_answers.pop(question_id, None)
        question_states[question_id] = {
            "status": "answered",
            "attempt_count": 0,
            "last_action_mode": action_mode,
        }
        return {"status": "answered"}

    def _is_valid_action_mode(
        self,
        action_mode: str,
        question_status: str,
        has_pending_partial: bool = False,
    ) -> bool:
        if action_mode == "answer":
            return question_status in {"unanswered", "skipped"}
        if action_mode == "modify":
            return question_status == "answered"
        if action_mode == "partial_completion":
            return question_status == "partial" or has_pending_partial
        return False

    def _is_valid_mapped_answer(self, question: dict, mapped: dict) -> bool:
        input_type = str(question.get("input_type", "")).lower()
        if input_type == "text" and not question.get("options"):
            return bool(mapped.get("selected_options")) or bool(str(mapped.get("input_value", "")).strip())
        if input_type in {"radio", "single", "select", "multi", "checkbox", "time_point"}:
            return bool(mapped.get("selected_options"))
        return bool(mapped.get("selected_options")) or bool(str(mapped.get("input_value", "")).strip())

    def _mapped_payload(self, unit: dict, question_id: str) -> dict:
        selected_options = list(unit.get("selected_options", []))
        field_updates = dict(unit.get("field_updates", {}))
        missing_fields = list(unit.get("missing_fields", []))
        input_value = str(unit.get("input_value", ""))
        if selected_options or field_updates or missing_fields:
            return {
                "selected_options": selected_options,
                "input_value": input_value,
                "filled_fields": field_updates,
                "field_updates": field_updates,
                "missing_fields": missing_fields,
            }
        return map_content_value(question_id, unit.get("raw_extracted_value", unit["unit_text"]))

    def _set_clarification_target(
        self,
        response_facts: dict,
        graph_state: dict,
        question_id: str | None,
        clarification_kind: str,
        *,
        title: str | None = None,
    ) -> None:
        response_facts.setdefault("clarification_kind", clarification_kind)
        if not question_id:
            return
        question = graph_state["question_catalog"]["question_index"].get(question_id, {})
        response_facts.setdefault("clarification_question_id", question_id)
        response_facts.setdefault(
            "clarification_question_title",
            title or question.get("title"),
        )

    def _build_clarification_context(
        self,
        graph_state: dict,
        question_id: str | None,
        clarification_kind: str,
        *,
        title: str | None = None,
    ) -> dict | None:
        if not question_id:
            return None
        question = graph_state["question_catalog"]["question_index"].get(question_id, {})
        return {
            "question_id": question_id,
            "question_title": title or question.get("title"),
            "kind": clarification_kind,
        }
