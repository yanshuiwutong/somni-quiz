"""Runtime engine."""

from __future__ import annotations

from somni_graph_quiz.contracts.question_catalog import get_question
from somni_graph_quiz.contracts.turn_result import calculate_progress_percent, create_turn_result
from somni_graph_quiz.nodes.layer1.turn_classify import TurnClassifyNode
from somni_graph_quiz.nodes.layer2.content.branch import ContentBranch
from somni_graph_quiz.nodes.layer2.non_content.branch import NonContentBranch
from somni_graph_quiz.nodes.layer3.finalize import TurnFinalizeNode
from somni_graph_quiz.nodes.layer3.respond import ResponseComposerNode
from somni_graph_quiz.runtime.companion_transition import CompanionTransition
from somni_graph_quiz.runtime.transitions import apply_branch_state_patch


class GraphRuntimeEngine:
    """Execute the graph turn."""

    def __init__(self) -> None:
        self._classify = TurnClassifyNode()
        self._content = ContentBranch()
        self._non_content = NonContentBranch()
        self._companion = CompanionTransition()
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
        branch_result = self._companion.apply(classified_state, turn_input, branch_result)
        finalized = self._finalize.run(classified_state, branch_result)
        updated_graph_state = apply_branch_state_patch(classified_state, branch_result)
        updated_graph_state["runtime"]["current_turn_index"] += 1
        updated_graph_state["runtime"]["finalized"] = finalized.finalized
        assistant_message = self._respond.run(finalized)
        self._append_recent_turn(updated_graph_state, turn_input, branch_result, finalized, assistant_message)
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
        assistant_message: str,
    ) -> None:
        recent_turns = list(updated_graph_state["session_memory"]["recent_turns"])
        assistant_summary = self._companion_assistant_summary(
            assistant_message=assistant_message,
            finalized=finalized,
        )
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
                "answer_status_override": getattr(finalized, "response_facts", {}).get("answer_status_override"),
                **assistant_summary,
            }
        )
        updated_graph_state["session_memory"]["recent_turns"] = recent_turns[-10:]

    def _companion_assistant_summary(self, *, assistant_message: str, finalized: object) -> dict:
        response_facts = getattr(finalized, "response_facts", {})
        if not (
            response_facts.get("stay_in_companion")
            or response_facts.get("companion_soft_return_to_quiz")
            or response_facts.get("return_to_quiz")
        ):
            return {
                "assistant_mode": None,
                "assistant_topic": None,
                "assistant_followup_kind": None,
                "assistant_pullback_anchor": None,
            }

        lowered_input = str(getattr(finalized, "raw_input", "") or "").lower()
        lowered_message = str(assistant_message or "").lower()
        assistant_topic = self._infer_companion_topic(lowered_input) or self._infer_companion_topic(lowered_message)
        followup_kind = "open_followup" if any(token in assistant_message for token in ("？", "?", "还是", "要是你愿意")) else None
        pullback_anchor = self._infer_companion_pullback_anchor(
            assistant_message=assistant_message,
            finalized=finalized,
        )
        return {
            "assistant_mode": "companion",
            "assistant_topic": assistant_topic,
            "assistant_followup_kind": followup_kind,
            "assistant_pullback_anchor": pullback_anchor,
        }

    def _infer_companion_topic(self, text: str) -> str | None:
        if any(token in text for token in ("旅游", "旅行", "景点", "海边", "去哪")):
            return "travel"
        if any(token in text for token in ("睡不着", "失眠", "入睡困难", "入睡比较困难", "睡眠")):
            return "sleep_stress"
        if any(token in text for token in ("褪黑素",)):
            return "melatonin"
        if any(token in text for token in ("奶茶",)):
            return "milk_tea"
        if any(token in text for token in ("吃什么", "午饭", "午餐", "西红柿炒鸡蛋")):
            return "meal"
        return None

    def _infer_companion_pullback_anchor(self, *, assistant_message: str, finalized: object) -> str | None:
        response_facts = getattr(finalized, "response_facts", {})
        if str(response_facts.get("continue_chat_intent", "none")) == "strong":
            return None
        candidate_question = getattr(finalized, "next_question", None) or getattr(finalized, "current_question", None)
        if not isinstance(candidate_question, dict):
            return None
        candidate_title = str(candidate_question.get("title", "")).strip()
        if not candidate_title:
            return None
        if response_facts.get("companion_soft_return_to_quiz") or response_facts.get("return_to_quiz"):
            return candidate_title
        if candidate_title in assistant_message:
            return candidate_title
        if any(token in assistant_message for token in ("基础信息", "继续往下看", "这部分", "这一题", "顺手看一下")):
            return candidate_title
        return None
