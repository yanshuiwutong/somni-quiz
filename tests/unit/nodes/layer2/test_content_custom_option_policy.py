from somni_graph_quiz.contracts.graph_state import create_graph_state
from somni_graph_quiz.contracts.turn_input import TurnInput
from somni_graph_quiz.llm.client import FakeLLMProvider
from somni_graph_quiz.nodes.layer2.content.branch import ContentBranch


def _custom_fallback_question() -> dict:
    return {
        "question_id": "question-09",
        "title": "早上醒来后，多久能彻底清醒？",
        "description": "",
        "input_type": "radio",
        "options": [
            {"option_id": "A", "label": "几乎立刻清醒，满血复活", "option_text": "几乎立刻清醒，满血复活", "aliases": []},
            {"option_id": "B", "label": "需要洗漱或咖啡缓冲", "option_text": "需要洗漱或咖啡缓冲", "aliases": []},
            {"option_id": "C", "label": "1-2 小时都不太清醒，身体沉重", "option_text": "1-2 小时都不太清醒，身体沉重", "aliases": []},
            {"option_id": "D", "label": "", "option_text": "", "aliases": []},
        ],
        "tags": ["anchor"],
        "metadata": {
            "allow_partial": False,
            "structured_kind": "radio",
            "response_style": "default",
            "matching_hints": ["清醒", "醒来", "早起", "缓过来"],
        },
    }


def test_content_branch_prefers_empty_option_for_current_question_non_standard_free_text_over_llm_option_mapping() -> None:
    question_catalog = {
        "question_order": ["question-09"],
        "question_index": {"question-09": _custom_fallback_question()},
    }
    graph_state = create_graph_state(
        session_id="session-custom-fallback-llm-non-standard-free-text",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
        responses={
            "layer2/content_understand.md": """
            {
              "content_units": [
                {
                  "unit_id": "unit-1",
                  "unit_text": "我一般要缓很久才能完全清醒",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-09"],
                  "winner_question_id": "question-09",
                  "needs_attribution": false,
                  "raw_extracted_value": "我一般要缓很久才能完全清醒",
                  "selected_options": [],
                  "input_value": "",
                  "field_updates": {},
                  "missing_fields": []
                }
              ],
              "clarification_needed": false,
              "clarification_reason": null
            }
            """,
            "layer2/text_option_mapping.md": """
            {
              "selected_options": ["C"],
              "confidence": 0.87,
              "reason": "long time to fully wake up is semantically closest to option C"
            }
            """,
        }
    )
    graph_state["session_memory"]["current_question_id"] = "question-09"
    graph_state["session_memory"]["pending_question_ids"] = ["question-09"]

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-custom-fallback-llm-non-standard-free-text",
            channel="grpc",
            input_mode="message",
            raw_input="我一般要缓很久才能完全清醒",
            language_preference="zh-CN",
        ),
    )

    assert result["applied_question_ids"] == ["question-09"]
    answer = result["state_patch"]["session_memory"]["answered_records"]["question-09"]
    assert answer["selected_options"] == ["D"]
    assert answer["input_value"] == "我一般要缓很久才能完全清醒"
