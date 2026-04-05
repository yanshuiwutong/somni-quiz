"""Turn finalize node."""

from __future__ import annotations

from somni_graph_quiz.contracts.finalized_turn_context import create_finalized_turn_context
from somni_graph_quiz.contracts.question_catalog import get_question
from somni_graph_quiz.runtime.transitions import apply_branch_state_patch


class TurnFinalizeNode:
    """Merge branch output and derive response facts."""

    def run(self, graph_state: dict, branch_result: dict) -> object:
        updated_graph_state = apply_branch_state_patch(graph_state, branch_result)
        session_memory = updated_graph_state["session_memory"]
        turn_state = updated_graph_state["turn"]
        response_language = turn_state["response_language"]
        current_question = self._question_summary(
            get_question(updated_graph_state["question_catalog"], session_memory["current_question_id"])
        )
        next_question_id = self._choose_next_question_id(updated_graph_state, branch_result)
        next_question = self._question_summary(
            get_question(updated_graph_state["question_catalog"], next_question_id)
        )
        turn_outcome = self._pick_turn_outcome(
            branch_result=branch_result,
            answered_question_ids=session_memory["answered_question_ids"],
            question_count=len(updated_graph_state["question_catalog"]["question_order"]),
        )
        finalized = turn_outcome == "completed"
        response_facts = {
            **branch_result.get("response_facts", {}),
            "next_question_id": next_question_id,
            "finalized": finalized,
            "response_language": response_language,
            "llm_available": updated_graph_state["runtime"].get("llm_available", False),
            "llm_provider": updated_graph_state["runtime"].get("llm_provider"),
        }
        updated_graph_state["runtime"]["finalized"] = finalized
        return create_finalized_turn_context(
            turn_outcome=turn_outcome,
            updated_answer_record={"answers": list(session_memory["answered_records"].values())},
            updated_question_states=session_memory["question_states"],
            current_question_id=session_memory["current_question_id"],
            next_question=next_question,
            finalized=finalized,
            response_language=response_language,
            response_facts=response_facts,
            raw_input=turn_state.get("raw_input", ""),
            input_mode=turn_state.get("input_mode", "message"),
            main_branch=turn_state.get("main_branch", "content"),
            non_content_intent=turn_state.get("non_content_intent", "none"),
            current_question=current_question,
        )

    def _question_summary(self, question: dict | None) -> dict | None:
        if not question:
            return None
        return {
            "question_id": question.get("question_id"),
            "title": question.get("title"),
            "input_type": question.get("input_type"),
        }

    def _choose_next_question_id(self, graph_state: dict, branch_result: dict) -> str | None:
        session_memory = graph_state["session_memory"]
        if branch_result["branch_type"] == "non_content":
            explicit_question_id = branch_result.get("response_facts", {}).get("next_question_id")
            if explicit_question_id is not None:
                return explicit_question_id
        if session_memory["current_question_id"] is not None:
            return session_memory["current_question_id"]
        pending = session_memory["pending_question_ids"]
        if pending:
            return pending[0]
        if session_memory["skipped_question_ids"]:
            return session_memory["skipped_question_ids"][0]
        return None

    def _pick_turn_outcome(
        self,
        *,
        branch_result: dict,
        answered_question_ids: list[str],
        question_count: int,
    ) -> str:
        if question_count > 0 and len(answered_question_ids) == question_count:
            return "completed"
        if branch_result["modified_question_ids"]:
            return "modified"
        if branch_result["applied_question_ids"]:
            return "answered"
        if branch_result["partial_question_ids"]:
            return "partial_recorded"
        if branch_result["skipped_question_ids"]:
            return "skipped"
        if branch_result["clarification_needed"]:
            return "clarification"
        if branch_result["branch_type"] == "non_content":
            mode = branch_result.get("response_facts", {}).get("non_content_mode")
            control_action = branch_result.get("response_facts", {}).get("control_action")
            if mode == "view":
                return "view_only"
            if mode == "undo":
                return "undo_applied"
            if mode == "control" and control_action in {
                "navigate_next",
                "navigate_previous",
                "modify_previous",
            }:
                return "navigate"
            return "pullback"
        return "clarification"
