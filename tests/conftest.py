"""Shared pytest fixtures for somni_graph_quiz."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


@pytest.fixture()
def question_catalog() -> dict:
    return {
        "question_order": ["question-01", "question-02", "question-03", "question-04"],
        "question_index": {
            "question-01": {
                "question_id": "question-01",
                "title": "How old are you?",
                "description": "",
                "input_type": "text",
                "options": [],
                "tags": ["profile"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": None,
                    "response_style": "default",
                    "matching_hints": ["age"],
                },
            },
            "question-02": {
                "question_id": "question-02",
                "title": "What time do you usually sleep and wake?",
                "description": "",
                "input_type": "time_range",
                "options": [],
                "tags": ["schedule"],
                "metadata": {
                    "allow_partial": True,
                    "structured_kind": "time_range",
                    "response_style": "followup",
                    "matching_hints": ["sleep", "bedtime"],
                },
            },
            "question-03": {
                "question_id": "question-03",
                "title": "What time do you fall asleep on free days?",
                "description": "",
                "input_type": "time_point",
                "options": [],
                "tags": ["relaxed_schedule"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "time_point",
                    "response_style": "followup",
                    "matching_hints": ["free day", "relaxed", "weekend sleep"],
                },
            },
            "question-04": {
                "question_id": "question-04",
                "title": "What time do you wake on free days?",
                "description": "",
                "input_type": "time_point",
                "options": [],
                "tags": ["relaxed_schedule"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "time_point",
                    "response_style": "followup",
                    "matching_hints": ["free day", "relaxed", "weekend wake"],
                },
            },
        },
    }


@pytest.fixture()
def companion_question_catalog() -> dict:
    return {
        "question_order": ["question-01", "question-02", "question-03"],
        "question_index": {
            "question-01": {
                "question_id": "question-01",
                "title": "您的年龄段？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "18-24 岁"},
                    {"option_id": "B", "label": "25-34 岁"},
                ],
                "tags": ["基础信息"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["年龄", "age"],
                },
            },
            "question-02": {
                "question_id": "question-02",
                "title": "您平时通常几点睡？",
                "description": "",
                "input_type": "text",
                "options": [],
                "tags": ["作息"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": None,
                    "response_style": "default",
                    "matching_hints": ["入睡", "几点睡", "睡觉"],
                },
            },
            "question-03": {
                "question_id": "question-03",
                "title": "您醒来后多久能彻底清醒？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "几乎立刻"},
                    {"option_id": "B", "label": "需要缓冲"},
                ],
                "tags": ["恢复"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["清醒", "恢复"],
                },
            },
        },
    }
