"""Content branch coordinator."""

from __future__ import annotations

from somni_graph_quiz.nodes.layer2.content.apply import ContentApplyNode
from somni_graph_quiz.nodes.layer2.content.attribution import FinalAttributionNode
from somni_graph_quiz.nodes.layer2.content.understand import ContentUnderstandNode


class ContentBranch:
    """Coordinate understanding, attribution, and apply."""

    def __init__(self) -> None:
        self._understand = ContentUnderstandNode()
        self._attribution = FinalAttributionNode()
        self._apply = ContentApplyNode()

    def run(self, graph_state: dict, turn_input: object) -> dict:
        understood = self._understand.run(graph_state, turn_input)
        resolved_units = []
        for unit in understood["content_units"]:
            if unit.get("needs_attribution") and self._should_skip_attribution(unit):
                candidate_question_ids = list(unit.get("candidate_question_ids", []))
                locally_resolved = {**unit, "needs_attribution": False}
                if unit.get("winner_question_id") is None and len(candidate_question_ids) == 1:
                    locally_resolved["winner_question_id"] = candidate_question_ids[0]
                resolved_units.append(
                    self._understand.standardize_content_unit(
                        graph_state,
                        locally_resolved,
                    )
                )
            elif unit.get("needs_attribution"):
                resolved_units.append(
                    self._understand.standardize_content_unit(
                        graph_state,
                        self._attribution.run(graph_state, unit),
                    )
                )
            else:
                resolved_units.append(self._understand.standardize_content_unit(graph_state, unit))
        return self._apply.run(
            graph_state,
            resolved_units,
            clarification_needed=understood["clarification_needed"],
            clarification_details={
                "clarification_reason": understood.get("clarification_reason"),
                "clarification_question_id": understood.get("clarification_question_id"),
                "clarification_question_title": understood.get("clarification_question_title"),
                "clarification_kind": understood.get("clarification_kind"),
            },
        )

    def _should_skip_attribution(self, unit: dict) -> bool:
        candidate_question_ids = list(unit.get("candidate_question_ids", []))
        if unit.get("winner_question_id") is not None:
            return True
        return len(candidate_question_ids) <= 1
