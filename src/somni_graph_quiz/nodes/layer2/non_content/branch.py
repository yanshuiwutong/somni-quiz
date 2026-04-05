"""Non-content branch coordinator."""

from __future__ import annotations

from copy import deepcopy

from somni_graph_quiz.contracts.node_contracts import create_branch_result


class NonContentBranch:
    """Execute non-content actions selected by layer1."""

    def run(self, graph_state: dict, turn_input: object) -> dict:
        non_content_intent = graph_state["turn"].get("non_content_intent", "pullback_chat")
        if non_content_intent in {
            "navigate_next",
            "navigate_previous",
            "skip",
            "undo",
            "view_all",
            "view_current",
            "view_previous",
            "view_next",
            "modify_previous",
        }:
            return self._apply_control(graph_state, non_content_intent)
        if non_content_intent == "identity":
            return create_branch_result(
                branch_type="non_content",
                response_facts={
                    "non_content_mode": "pullback",
                    "non_content_action": "pullback",
                    "pullback_reason": "identity_question",
                },
            )
        return create_branch_result(
            branch_type="non_content",
            response_facts={
                "non_content_mode": "pullback",
                "non_content_action": "pullback",
                "pullback_reason": "chat",
            },
        )

    def _apply_control(self, graph_state: dict, control_action: str) -> dict:
        session_memory = graph_state["session_memory"]
        if control_action == "modify_previous":
            target_question_id = self._latest_answered_question_id(session_memory)
            if not target_question_id:
                return create_branch_result(
                    branch_type="non_content",
                    clarification_needed=True,
                    response_facts={
                        "non_content_mode": "control",
                        "control_action": "modify_previous",
                        "non_content_action": "modify_previous",
                        "clarification_reason": "missing_modify_target",
                    },
                )
            return create_branch_result(
                branch_type="non_content",
                state_patch={
                    "session_memory": {
                        "current_question_id": target_question_id,
                        "pending_modify_context": {"question_id": target_question_id},
                    }
                },
                response_facts={
                    "non_content_mode": "control",
                    "control_action": "modify_previous",
                    "non_content_action": "modify_previous",
                    "next_question_id": target_question_id,
                },
            )
        if control_action == "navigate_previous":
            target_question_id = self._latest_answered_question_id(session_memory)
            if not target_question_id:
                return create_branch_result(
                    branch_type="non_content",
                    clarification_needed=True,
                    response_facts={
                        "non_content_mode": "control",
                        "control_action": "navigate_previous",
                        "non_content_action": "navigate_previous",
                        "clarification_reason": "missing_previous_question",
                    },
                )
            return create_branch_result(
                branch_type="non_content",
                state_patch={"session_memory": {"current_question_id": target_question_id}},
                response_facts={
                    "non_content_mode": "control",
                    "control_action": "navigate_previous",
                    "non_content_action": "navigate_previous",
                    "next_question_id": target_question_id,
                },
            )
        if control_action == "navigate_next":
            pending = list(session_memory["pending_question_ids"])
            if pending:
                current_question_id = pending[1] if len(pending) > 1 else pending[0]
                return create_branch_result(
                    branch_type="non_content",
                    state_patch={
                        "session_memory": {
                            "current_question_id": current_question_id,
                            "pending_question_ids": pending[1:] or pending,
                        }
                    },
                    response_facts={
                        "non_content_mode": "control",
                        "control_action": "navigate_next",
                        "non_content_action": "navigate_next",
                        "next_question_id": current_question_id,
                    },
                )
        if control_action == "skip":
            current_question_id = session_memory["current_question_id"]
            skipped = list(dict.fromkeys([*session_memory["skipped_question_ids"], current_question_id]))
            pending = [qid for qid in session_memory["pending_question_ids"] if qid != current_question_id]
            next_question_id = pending[0] if pending else None
            question_states = deepcopy(session_memory["question_states"])
            if current_question_id:
                question_states[current_question_id] = {
                    "status": "skipped",
                    "attempt_count": question_states[current_question_id]["attempt_count"],
                    "last_action_mode": question_states[current_question_id]["last_action_mode"],
                }
            return create_branch_result(
                branch_type="non_content",
                state_patch={
                    "session_memory": {
                        "skipped_question_ids": skipped,
                        "pending_question_ids": pending,
                        "current_question_id": next_question_id,
                        "pending_partial_answers": deepcopy(session_memory["pending_partial_answers"]),
                        "partial_question_ids": list(session_memory["partial_question_ids"]),
                        "question_states": question_states,
                    }
                },
                skipped_question_ids=[current_question_id] if current_question_id else [],
                response_facts={
                    "non_content_mode": "control",
                    "control_action": "skip",
                    "non_content_action": "skip",
                    "next_question_id": next_question_id,
                },
            )
        if control_action == "undo":
            previous = deepcopy(session_memory["previous_answer_record"])
            if not previous:
                return create_branch_result(
                    branch_type="non_content",
                    response_facts={
                        "non_content_mode": "undo",
                        "non_content_action": "undo",
                        "undo_applied": False,
                    },
                )
            answered = deepcopy(session_memory["answered_records"])
            answered.update(previous)
            return create_branch_result(
                branch_type="non_content",
                state_patch={
                    "session_memory": {
                        "answered_records": answered,
                        "previous_answer_record": None,
                    }
                },
                response_facts={
                    "non_content_mode": "undo",
                    "non_content_action": "undo",
                    "undo_applied": True,
                },
            )
        if control_action == "view_current":
            current_question_id = session_memory["current_question_id"]
            record = session_memory["answered_records"].get(current_question_id)
            view_records = [record] if record else []
            return create_branch_result(
                branch_type="non_content",
                response_facts={
                    "non_content_mode": "view",
                    "non_content_action": "view_current",
                    "view_target_question_id": current_question_id,
                    "view_records": view_records,
                },
            )
        if control_action == "view_previous":
            target_question_id = self._latest_answered_question_id(session_memory)
            record = session_memory["answered_records"].get(target_question_id) if target_question_id else None
            view_records = [record] if record else []
            return create_branch_result(
                branch_type="non_content",
                response_facts={
                    "non_content_mode": "view",
                    "non_content_action": "view_previous",
                    "view_target_question_id": target_question_id,
                    "view_records": view_records,
                },
            )
        if control_action == "view_next":
            pending = list(session_memory["pending_question_ids"])
            current_question_id = pending[1] if len(pending) > 1 else (pending[0] if pending else None)
            return create_branch_result(
                branch_type="non_content",
                response_facts={
                    "non_content_mode": "view",
                    "non_content_action": "view_next",
                    "view_target_question_id": current_question_id,
                    "view_records": [],
                    "next_question_id": current_question_id,
                },
            )
        if control_action == "view_all":
            return create_branch_result(
                branch_type="non_content",
                response_facts={
                    "non_content_mode": "view",
                    "non_content_action": "view_all",
                    "view_records": list(session_memory["answered_records"].values()),
                },
            )
        return create_branch_result(
            branch_type="non_content",
            response_facts={"non_content_mode": "pullback", "non_content_action": "pullback"},
        )

    def _latest_answered_question_id(self, session_memory: dict) -> str | None:
        for turn in reversed(session_memory["recent_turns"]):
            modified_question_ids = turn.get("modified_question_ids", [])
            if modified_question_ids:
                return modified_question_ids[-1]
            recorded_question_ids = turn.get("recorded_question_ids", [])
            if recorded_question_ids:
                return recorded_question_ids[-1]
        answered_question_ids = session_memory["answered_question_ids"]
        if answered_question_ids:
            return answered_question_ids[-1]
        return None
