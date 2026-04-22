"""Turn input contract."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TurnInput:
    """External turn input passed into the runtime."""

    session_id: str
    channel: str
    input_mode: str
    raw_input: str
    direct_answer_payload: dict | None = None
    language_preference: str | None = None
