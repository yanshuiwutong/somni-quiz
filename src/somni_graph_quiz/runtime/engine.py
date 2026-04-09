"""Runtime engine."""

from __future__ import annotations

from somni_graph_quiz.contracts.question_catalog import get_question
from somni_graph_quiz.contracts.turn_result import calculate_progress_percent, create_turn_result
from somni_graph_quiz.nodes.layer1.turn_classify import TurnClassifyNode
from somni_graph_quiz.nodes.layer2.content.branch import ContentBranch
from somni_graph_quiz.nodes.layer2.non_content.branch import NonContentBranch
from somni_graph_quiz.nodes.layer3.finalize import TurnFinalizeNode
from somni_graph_quiz.nodes.layer3.respond import ResponseComposerNode
from somni_graph_quiz.runtime.transitions import apply_branch_state_patch


class GraphRuntimeEngine:
    """Execute the graph turn."""

    def __init__(self) -> None:
        self._classify = TurnClassifyNode()
        self._content = ContentBranch()
        self._non_content = NonContentBranch()
        self._finalize = TurnFinalizeNode()
        self._respond = ResponseComposerNode()

    def run_turn(self, graph_state: dict, turn_input: object) -> dict:
        classification = self._classify.run(graph_state, turn_input)
        classified_state = apply_branch_state_patch(graph_state, classification)
        main_branch = classified_state["turn"]["main_branch"]
        if main_branch == "non_content":
            branch_result = self._non_content.run(classified_state, turn_input)
        else:
            branch_result = self._content.run(classified_state, turn_input)
        finalized = self._finalize.run(classified_state, branch_result)
        updated_graph_state = apply_branch_state_patch(classified_state, branch_result)
        updated_graph_state["runtime"]["current_turn_index"] += 1
        updated_graph_state["runtime"]["finalized"] = finalized.finalized
        self._append_recent_turn(updated_graph_state, turn_input, branch_result, finalized)
        assistant_message = self._respond.run(finalized)
        pending_question_id = finalized.response_facts.get("next_question_id") or updated_graph_state[
            "session_memory"
        ]["current_question_id"]
        pending_question = get_question(updated_graph_state["question_catalog"], pending_question_id)
        final_result = None
        if finalized.finalized:
            final_result = {
                "completion_message": assistant_message,
                "finalized": True,
            }
        progress_percent = calculate_progress_percent(
            answered_question_ids=updated_graph_state["session_memory"].get("answered_question_ids", []),
            partial_question_ids=updated_graph_state["session_memory"].get("partial_question_ids", []),
            question_count=len(updated_graph_state["question_catalog"].get("question_order", [])),
            finalized=finalized.finalized,
        )
        return create_turn_result(
            updated_graph_state=updated_graph_state,
            answer_record=finalized.updated_answer_record,
            pending_question=pending_question,
            assistant_message=assistant_message,
            finalized=finalized.finalized,
            final_result=final_result,
            progress_percent=progress_percent,
        )

    def _append_recent_turn(
        self,
        updated_graph_state: dict,
        turn_input: object,
        branch_result: dict,
        finalized: object,
    ) -> None:
        recent_turns = list(updated_graph_state["session_memory"]["recent_turns"])
        recent_turns.append(
            {
                "turn_index": updated_graph_state["runtime"]["current_turn_index"],
                "raw_input": getattr(turn_input, "raw_input", ""),
                "main_branch": updated_graph_state["turn"]["main_branch"],
                "turn_outcome": getattr(finalized, "turn_outcome", "clarification"),
                "recorded_question_ids": list(branch_result.get("applied_question_ids", [])),
                "modified_question_ids": list(branch_result.get("modified_question_ids", [])),
                "partial_question_ids": list(branch_result.get("partial_question_ids", [])),
                "skipped_question_ids": list(branch_result.get("skipped_question_ids", [])),
            }
        )
        updated_graph_state["session_memory"]["recent_turns"] = recent_turns[-10:]
