"""Prompt loading helpers."""

from __future__ import annotations

import json
from pathlib import Path


class PromptLoader:
    """Load prompt files and assemble shared contracts around them."""

    def __init__(self, prompts_root: Path) -> None:
        self._prompts_root = Path(prompts_root)

    def render(self, prompt_path: str, payload: dict) -> str:
        """Render a prompt with shared contracts and a JSON payload."""
        prompt_file = self._prompts_root / Path(prompt_path)
        sections = [
            self._read_shared("glossary.md"),
            self._read_shared("output_contracts.md"),
            self._read(prompt_file),
        ]
        if str(prompt_path).startswith("layer3/"):
            sections.extend(
                [
                    self._titled("Language Rules", self._read_shared("language_policy.md")),
                    self._read_shared("persona_contract.md"),
                    self._titled(
                        "Hard Guardrails",
                        self._read_shared("response_guardrails.md"),
                    ),
                ]
            )
        sections.append("## Input Payload\n\n```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```")
        return "\n\n".join(section for section in sections if section)

    def _read_shared(self, filename: str) -> str:
        return self._read(self._prompts_root / "shared" / filename)

    def _read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8").strip()

    def _titled(self, title: str, content: str) -> str:
        return f"## {title}\n\n{content}"
