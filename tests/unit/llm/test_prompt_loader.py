"""Tests for prompt assembly."""

from pathlib import Path

from somni_graph_quiz.llm.prompt_loader import PromptLoader


def test_prompt_loader_includes_shared_analysis_contracts() -> None:
    loader = PromptLoader(Path(__file__).resolve().parents[3] / "prompts")

    prompt = loader.render("layer1/turn_classify.md", {"raw_input": "下一题"})

    assert "Prompt Layout" not in prompt
    assert "TurnClassifyOutput" in prompt
    assert "main_branch" in prompt
    assert "raw_input" in prompt
    assert "Persona Contract" not in prompt


def test_prompt_loader_includes_response_shared_contracts_for_layer3() -> None:
    loader = PromptLoader(Path(__file__).resolve().parents[3] / "prompts")

    prompt = loader.render("layer3/response_composer.md", {"turn_outcome": "answered"})

    assert "Persona Contract" in prompt
    assert "Language Rules" in prompt
    assert "Hard Guardrails" in prompt
    assert '"turn_outcome": "answered"' in prompt
