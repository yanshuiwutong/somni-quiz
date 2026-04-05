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
            if unit.get("needs_attribution"):
                resolved_units.append(self._attribution.run(graph_state, unit))
            else:
                resolved_units.append(unit)
        return self._apply.run(
            graph_state,
            resolved_units,
            clarification_needed=understood["clarification_needed"],
        )
