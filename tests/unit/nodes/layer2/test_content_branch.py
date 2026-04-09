"""Tests for content branch integration."""

import json
from pathlib import Path

from somni_graph_quiz.adapters.streamlit.mapper import map_streamlit_questionnaire_to_catalog
from somni_graph_quiz.contracts.graph_state import create_graph_state
from somni_graph_quiz.contracts.turn_input import TurnInput
from somni_graph_quiz.llm.client import FakeLLMProvider
from somni_graph_quiz.nodes.layer2.content.apply import ContentApplyNode
from somni_graph_quiz.nodes.layer2.content.attribution import FinalAttributionNode
from somni_graph_quiz.nodes.layer2.content.branch import ContentBranch
from somni_graph_quiz.nodes.layer2.content.mapping import map_content_value
from somni_graph_quiz.nodes.layer2.content.understand import ContentUnderstandNode


def _business9_question_catalog() -> dict:
    payload = json.loads(
        (Path(__file__).resolve().parents[4] / "data" / "streamlit_dynamic_questionnaire.json").read_text(
            encoding="utf-8"
        )
    )
    return map_streamlit_questionnaire_to_catalog(payload["questionnaire"])


def test_content_branch_records_partial_schedule(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-1",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-1",
            channel="grpc",
            input_mode="message",
            raw_input="11点睡",
        ),
    )

    partial_entry = result["state_patch"]["session_memory"]["pending_partial_answers"]["question-02"]
    assert result["partial_question_ids"] == ["question-02"]
    assert partial_entry["filled_fields"] == {"bedtime": "23:00"}
    assert partial_entry["missing_fields"] == ["wake_time"]


def test_content_branch_turns_answered_question_into_modify(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-1",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="en",
    )
    graph_state["session_memory"]["answered_records"]["question-01"] = {
        "question_id": "question-01",
        "selected_options": [],
        "input_value": "22",
        "field_updates": {},
    }
    graph_state["session_memory"]["answered_question_ids"] = ["question-01"]
    graph_state["session_memory"]["unanswered_question_ids"] = ["question-02", "question-03", "question-04"]
    graph_state["session_memory"]["question_states"]["question-01"] = {
        "status": "answered",
        "attempt_count": 0,
        "last_action_mode": "answer",
    }
    graph_state["session_memory"]["current_question_id"] = "question-01"

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-1",
            channel="grpc",
            input_mode="message",
            raw_input="29",
            language_preference="en",
        ),
    )

    assert result["modified_question_ids"] == ["question-01"]
    updated = result["state_patch"]["session_memory"]["answered_records"]["question-01"]
    assert updated["selected_options"] == []
    assert updated["input_value"] == "29"


def test_content_understand_uses_llm_output_to_split_multi_question_turn(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-llm-1",
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
                  "unit_text": "我22岁",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-01"],
                  "winner_question_id": "question-01",
                  "needs_attribution": false,
                  "raw_extracted_value": "22"
                },
                {
                  "unit_id": "unit-2",
                  "unit_text": "每天11点睡觉，7点起床",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-02"],
                  "winner_question_id": "question-02",
                  "needs_attribution": false,
                  "raw_extracted_value": {
                    "bedtime": "23:00",
                    "wake_time": "07:00"
                  }
                }
              ],
              "clarification_needed": false,
              "clarification_reason": null
            }
            """
        }
    )

    understood = ContentUnderstandNode().run(
        graph_state,
        TurnInput(
            session_id="session-llm-1",
            channel="grpc",
            input_mode="message",
            raw_input="我22岁，每天11点睡觉，7点起床",
            language_preference="zh-CN",
        ),
    )

    assert [unit["winner_question_id"] for unit in understood["content_units"]] == [
        "question-01",
        "question-02",
    ]


def test_content_understand_defaults_plain_times_to_regular_schedule_without_relaxed_context(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-plain-regular-schedule",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )

    understood = ContentUnderstandNode().run(
        graph_state,
        TurnInput(
            session_id="session-plain-regular-schedule",
            channel="grpc",
            input_mode="message",
            raw_input="18岁，11点起。23点睡",
            language_preference="zh-CN",
        ),
    )

    assert [unit["winner_question_id"] for unit in understood["content_units"]] == [
        "question-01",
        "question-02",
    ]
    schedule_unit = understood["content_units"][1]
    assert schedule_unit["candidate_question_ids"] == ["question-02"]
    assert schedule_unit["field_updates"] == {"bedtime": "23:00", "wake_time": "11:00"}


def test_content_understand_overrides_llm_free_schedule_misattribution_without_relaxed_context(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-llm-regular-schedule-override",
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
                  "unit_text": "18岁",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-01"],
                  "winner_question_id": "question-01",
                  "needs_attribution": false,
                  "raw_extracted_value": "18"
                },
                {
                  "unit_id": "unit-2",
                  "unit_text": "11点起。23点睡",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-03"],
                  "winner_question_id": "question-03",
                  "needs_attribution": false,
                  "raw_extracted_value": {
                    "bedtime": "23:00",
                    "wake_time": "11:00"
                  },
                  "selected_options": [],
                  "input_value": "",
                  "field_updates": {
                    "bedtime": "23:00",
                    "wake_time": "11:00"
                  },
                  "missing_fields": []
                }
              ],
              "clarification_needed": false,
              "clarification_reason": null
            }
            """
        }
    )

    understood = ContentUnderstandNode().run(
        graph_state,
        TurnInput(
            session_id="session-llm-regular-schedule-override",
            channel="grpc",
            input_mode="message",
            raw_input="18岁，11点起。23点睡",
            language_preference="zh-CN",
        ),
    )

    assert [unit["winner_question_id"] for unit in understood["content_units"]] == [
        "question-01",
        "question-02",
    ]
    schedule_unit = understood["content_units"][1]
    assert schedule_unit["candidate_question_ids"] == ["question-02"]
    assert schedule_unit["field_updates"] == {"bedtime": "23:00", "wake_time": "11:00"}


def test_content_understand_reverts_llm_wake_fragment_to_regular_schedule_without_relaxed_context(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-llm-wake-regular-schedule",
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
                  "unit_text": "11点起",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-04"],
                  "winner_question_id": "question-04",
                  "needs_attribution": false,
                  "raw_extracted_value": "11点起"
                }
              ],
              "clarification_needed": false,
              "clarification_reason": null
            }
            """
        }
    )

    understood = ContentUnderstandNode().run(
        graph_state,
        TurnInput(
            session_id="session-llm-wake-regular-schedule",
            channel="grpc",
            input_mode="message",
            raw_input="11点起",
            language_preference="zh-CN",
        ),
    )

    schedule_unit = understood["content_units"][0]
    assert schedule_unit["winner_question_id"] == "question-02"
    assert schedule_unit["candidate_question_ids"] == ["question-02"]


def test_content_understand_keeps_current_wake_fragment_question(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-llm-current-wake",
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
                  "unit_text": "11点起",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-04"],
                  "winner_question_id": "question-04",
                  "needs_attribution": false,
                  "raw_extracted_value": "11点起"
                }
              ],
              "clarification_needed": false,
              "clarification_reason": null
            }
            """
        }
    )
    graph_state["session_memory"]["current_question_id"] = "question-04"

    understood = ContentUnderstandNode().run(
        graph_state,
        TurnInput(
            session_id="session-llm-current-wake",
            channel="grpc",
            input_mode="message",
            raw_input="11点起",
            language_preference="zh-CN",
        ),
    )

    schedule_unit = understood["content_units"][0]
    assert schedule_unit["winner_question_id"] == "question-04"
    assert schedule_unit["candidate_question_ids"] == ["question-04"]


def test_content_branch_handles_same_turn_answer_and_modify(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-2",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["answered_records"]["question-01"] = {
        "question_id": "question-01",
        "selected_options": [],
        "input_value": "28",
        "field_updates": {},
    }
    graph_state["session_memory"]["answered_question_ids"] = ["question-01"]
    graph_state["session_memory"]["unanswered_question_ids"] = ["question-02", "question-03", "question-04"]
    graph_state["session_memory"]["question_states"]["question-01"] = {
        "status": "answered",
        "attempt_count": 0,
        "last_action_mode": "answer",
    }
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-2",
            channel="grpc",
            input_mode="message",
            raw_input="年龄不是28，是29；每天11点睡觉，7点起床",
            language_preference="zh-CN",
        ),
    )

    updated = result["state_patch"]["session_memory"]["answered_records"]
    assert result["modified_question_ids"] == ["question-01"]
    assert sorted(result["applied_question_ids"]) == ["question-02"]
    assert updated["question-01"]["selected_options"] == []
    assert updated["question-01"]["input_value"] == "29"
    assert updated["question-02"]["input_value"] == "23:00-07:00"


def test_content_apply_rejects_same_turn_same_question_conflict(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-3",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="en",
    )

    result = ContentApplyNode().run(
        graph_state,
        [
            {
                "unit_id": "unit-1",
                "unit_text": "I am 22",
                "action_mode": "answer",
                "candidate_question_ids": ["question-01"],
                "winner_question_id": "question-01",
                "needs_attribution": False,
                "raw_extracted_value": "22",
            },
            {
                "unit_id": "unit-2",
                "unit_text": "Actually 29",
                "action_mode": "answer",
                "candidate_question_ids": ["question-01"],
                "winner_question_id": "question-01",
                "needs_attribution": False,
                "raw_extracted_value": "29",
            },
        ],
    )

    assert result["clarification_needed"] is True
    assert sorted(result["rejected_unit_ids"]) == ["unit-1", "unit-2"]
    assert result["state_patch"]["session_memory"]["answered_records"] == {}


def test_final_attribution_prefers_regular_schedule_for_plain_timepoint(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-4",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]

    resolved = FinalAttributionNode().run(
        graph_state,
        {
            "unit_id": "unit-1",
            "unit_text": "23点",
            "action_mode": "answer",
            "candidate_question_ids": ["question-02", "question-03", "question-04"],
            "winner_question_id": None,
            "needs_attribution": True,
            "raw_extracted_value": "23点",
        },
    )

    assert resolved["winner_question_id"] == "question-02"
    assert resolved["needs_clarification"] is False


def test_content_branch_maps_23_to_question_03_option_b_in_free_sleep_context(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-5",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-03"
    graph_state["session_memory"]["pending_question_ids"] = ["question-03", "question-04"]
    graph_state["session_memory"]["unanswered_question_ids"] = ["question-01", "question-02", "question-03", "question-04"]

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-5",
            channel="grpc",
            input_mode="message",
            raw_input="23点",
            language_preference="zh-CN",
        ),
    )

    answer = result["state_patch"]["session_memory"]["answered_records"]["question-03"]
    assert result["applied_question_ids"] == ["question-03"]
    assert answer["selected_options"] == ["B"]
    assert answer["input_value"] == ""


def test_content_branch_keeps_ambiguous_time_point_on_current_free_sleep_question(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-free-sleep-ambiguous-hour",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-03"
    graph_state["session_memory"]["pending_question_ids"] = ["question-03", "question-04"]
    graph_state["session_memory"]["unanswered_question_ids"] = [
        "question-01",
        "question-02",
        "question-03",
        "question-04",
    ]

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-free-sleep-ambiguous-hour",
            channel="grpc",
            input_mode="message",
            raw_input="7点",
            language_preference="zh-CN",
        ),
    )

    answer = result["state_patch"]["session_memory"]["answered_records"]["question-03"]
    assert result["applied_question_ids"] == ["question-03"]
    assert "question-04" not in result["state_patch"]["session_memory"]["answered_records"]
    assert answer["selected_options"] == ["D"]
    assert answer["input_value"] == ""


def test_content_branch_keeps_ambiguous_time_point_on_current_free_sleep_question_for_business9() -> None:
    question_catalog = _business9_question_catalog()
    graph_state = create_graph_state(
        session_id="session-business9-free-sleep-ambiguous-hour",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["answered_records"]["question-01"] = {
        "question_id": "question-01",
        "selected_options": ["A"],
        "input_value": "",
        "field_updates": {},
    }
    graph_state["session_memory"]["answered_records"]["question-02"] = {
        "question_id": "question-02",
        "selected_options": [],
        "input_value": "23:00-11:00",
        "field_updates": {"bedtime": "23:00", "wake_time": "11:00"},
    }
    graph_state["session_memory"]["answered_question_ids"] = ["question-01", "question-02"]
    graph_state["session_memory"]["unanswered_question_ids"] = [
        question_id
        for question_id in question_catalog["question_order"]
        if question_id not in {"question-01", "question-02"}
    ]
    graph_state["session_memory"]["pending_question_ids"] = [
        question_id
        for question_id in question_catalog["question_order"]
        if question_id not in {"question-01", "question-02"}
    ]
    graph_state["session_memory"]["current_question_id"] = "question-03"
    graph_state["session_memory"]["question_states"]["question-01"] = {
        "status": "answered",
        "attempt_count": 0,
        "last_action_mode": "answer",
    }
    graph_state["session_memory"]["question_states"]["question-02"] = {
        "status": "answered",
        "attempt_count": 0,
        "last_action_mode": "answer",
    }

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-business9-free-sleep-ambiguous-hour",
            channel="grpc",
            input_mode="message",
            raw_input="7点",
            language_preference="zh-CN",
        ),
    )

    answers = result["state_patch"]["session_memory"]["answered_records"]
    assert result["applied_question_ids"] == ["question-03"]
    assert answers["question-03"]["selected_options"] == ["D"]
    assert "question-04" not in answers


def test_content_understand_defaults_bare_time_point_to_regular_schedule_without_relaxed_context(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-regular-schedule-default-hour",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]
    graph_state["session_memory"]["unanswered_question_ids"] = [
        "question-01",
        "question-02",
        "question-03",
        "question-04",
    ]

    understood = ContentUnderstandNode().run(
        graph_state,
        TurnInput(
            session_id="session-regular-schedule-default-hour",
            channel="grpc",
            input_mode="message",
            raw_input="7点",
            language_preference="zh-CN",
        ),
    )

    assert understood["content_units"][0]["winner_question_id"] == "question-02"
    assert understood["content_units"][0]["candidate_question_ids"] == ["question-02"]
    assert understood["content_units"][0]["needs_attribution"] is False


def test_content_branch_maps_around_7_to_question_04_option_b_in_free_wake_context(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-6",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-04"
    graph_state["session_memory"]["pending_question_ids"] = ["question-04"]
    graph_state["session_memory"]["unanswered_question_ids"] = ["question-01", "question-02", "question-03", "question-04"]

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-6",
            channel="grpc",
            input_mode="message",
            raw_input="那7左右",
            language_preference="zh-CN",
        ),
    )

    answer = result["state_patch"]["session_memory"]["answered_records"]["question-04"]
    assert result["applied_question_ids"] == ["question-04"]
    assert answer["selected_options"] == ["B"]
    assert answer["input_value"] == ""


def test_content_branch_prefers_current_free_wake_question_over_regular_schedule_partial(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-current-free-wake-soft-priority",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-04"
    graph_state["session_memory"]["pending_question_ids"] = ["question-04"]
    graph_state["session_memory"]["unanswered_question_ids"] = ["question-01", "question-03", "question-04"]
    graph_state["session_memory"]["pending_partial_answers"]["question-02"] = {
        "question_id": "question-02",
        "filled_fields": {"bedtime": "23:00"},
        "missing_fields": ["wake_time"],
        "source_question_state": "partial",
    }
    graph_state["session_memory"]["partial_question_ids"] = ["question-02"]
    graph_state["session_memory"]["question_states"]["question-02"] = {
        "status": "partial",
        "attempt_count": 0,
        "last_action_mode": "partial_completion",
    }

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-current-free-wake-soft-priority",
            channel="grpc",
            input_mode="message",
            raw_input="11点起",
            language_preference="zh-CN",
        ),
    )

    answers = result["state_patch"]["session_memory"]["answered_records"]
    assert result["applied_question_ids"] == ["question-04"]
    assert result["partial_question_ids"] == []
    assert answers["question-04"]["selected_options"] == ["D"]
    assert "question-02" not in answers
    assert result["state_patch"]["session_memory"]["pending_partial_answers"]["question-02"]["filled_fields"] == {
        "bedtime": "23:00"
    }


def test_content_branch_soft_priority_only_affects_matching_unit_not_other_units(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-soft-priority-multi-unit",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-04"
    graph_state["session_memory"]["pending_question_ids"] = ["question-04"]
    graph_state["session_memory"]["unanswered_question_ids"] = ["question-01", "question-03", "question-04"]
    graph_state["session_memory"]["pending_partial_answers"]["question-02"] = {
        "question_id": "question-02",
        "filled_fields": {"bedtime": "23:00"},
        "missing_fields": ["wake_time"],
        "source_question_state": "partial",
    }
    graph_state["session_memory"]["partial_question_ids"] = ["question-02"]
    graph_state["session_memory"]["question_states"]["question-02"] = {
        "status": "partial",
        "attempt_count": 0,
        "last_action_mode": "partial_completion",
    }
    graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
        responses={
            "layer2/content_understand.md": """
            {
              "content_units": [
                {
                  "unit_id": "unit-1",
                  "unit_text": "18岁",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-01"],
                  "winner_question_id": "question-01",
                  "needs_attribution": false,
                  "raw_extracted_value": "18"
                },
                {
                  "unit_id": "unit-2",
                  "unit_text": "11点起",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-02", "question-04"],
                  "winner_question_id": "question-04",
                  "needs_attribution": false,
                  "raw_extracted_value": {
                    "wake_time": "11:00"
                  },
                  "selected_options": [],
                  "input_value": "",
                  "field_updates": {},
                  "missing_fields": []
                }
              ],
              "clarification_needed": false,
              "clarification_reason": null
            }
            """
        }
    )

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-soft-priority-multi-unit",
            channel="grpc",
            input_mode="message",
            raw_input="18岁，11点起",
            language_preference="zh-CN",
        ),
    )

    answers = result["state_patch"]["session_memory"]["answered_records"]
    assert sorted(result["applied_question_ids"]) == ["question-01", "question-04"]
    assert answers["question-01"]["input_value"] == "18"
    assert answers["question-04"]["selected_options"] == ["D"]
    assert "question-02" not in answers


def test_content_understand_keeps_llm_free_wake_winner_in_current_question_context(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-llm-current-free-wake-priority",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-04"
    graph_state["session_memory"]["pending_question_ids"] = ["question-04"]
    graph_state["session_memory"]["pending_partial_answers"]["question-02"] = {
        "question_id": "question-02",
        "filled_fields": {"bedtime": "23:00"},
        "missing_fields": ["wake_time"],
        "source_question_state": "partial",
    }
    graph_state["session_memory"]["partial_question_ids"] = ["question-02"]
    graph_state["session_memory"]["question_states"]["question-02"] = {
        "status": "partial",
        "attempt_count": 0,
        "last_action_mode": "partial_completion",
    }
    graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
        responses={
            "layer2/content_understand.md": """
            {
              "content_units": [
                {
                  "unit_id": "unit-1",
                  "unit_text": "11点起",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-02", "question-04"],
                  "winner_question_id": "question-04",
                  "needs_attribution": false,
                  "raw_extracted_value": {
                    "wake_time": "11:00"
                  },
                  "selected_options": [],
                  "input_value": "",
                  "field_updates": {},
                  "missing_fields": []
                }
              ],
              "clarification_needed": false,
              "clarification_reason": null
            }
            """
        }
    )

    understood = ContentUnderstandNode().run(
        graph_state,
        TurnInput(
            session_id="session-llm-current-free-wake-priority",
            channel="grpc",
            input_mode="message",
            raw_input="11点起",
            language_preference="zh-CN",
        ),
    )

    assert understood["content_units"][0]["winner_question_id"] == "question-04"
    assert understood["content_units"][0]["raw_extracted_value"] == {"wake_time": "11:00"}
    assert understood["content_units"][0]["field_updates"] == {}


def test_content_understand_preserves_llm_question_02_wake_fragment_from_input_value_only(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-llm-question-02-wake-input-only",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]
    graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
        responses={
            "layer2/content_understand.md": """
            {
              "content_units": [
                {
                  "unit_id": "unit-1",
                  "unit_text": "11点起",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-02"],
                  "winner_question_id": "question-02",
                  "needs_attribution": false,
                  "raw_extracted_value": "11:00",
                  "selected_options": [],
                  "input_value": "11:00",
                  "field_updates": {},
                  "missing_fields": []
                }
              ],
              "clarification_needed": false,
              "clarification_reason": null
            }
            """
        }
    )

    understood = ContentUnderstandNode().run(
        graph_state,
        TurnInput(
            session_id="session-llm-question-02-wake-input-only",
            channel="grpc",
            input_mode="message",
            raw_input="11点起",
            language_preference="zh-CN",
        ),
    )

    assert understood["content_units"] == [
        {
            "unit_id": "unit-1",
            "unit_text": "11点起",
            "action_mode": "answer",
            "candidate_question_ids": ["question-02"],
            "winner_question_id": "question-02",
            "needs_attribution": False,
            "raw_extracted_value": "11:00",
            "selected_options": [],
            "input_value": "11:00",
            "field_updates": {"wake_time": "11:00"},
            "missing_fields": ["bedtime"],
        }
    ]


def test_content_apply_uses_implicit_modify_when_answered_question_receives_new_content(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-7",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["answered_records"]["question-03"] = {
        "question_id": "question-03",
        "selected_options": ["C"],
        "input_value": "",
        "field_updates": {},
    }
    graph_state["session_memory"]["answered_question_ids"] = ["question-03"]
    graph_state["session_memory"]["unanswered_question_ids"] = ["question-01", "question-02", "question-04"]
    graph_state["session_memory"]["question_states"]["question-03"] = {
        "status": "answered",
        "attempt_count": 0,
        "last_action_mode": "answer",
    }

    result = ContentApplyNode().run(
        graph_state,
        [
            {
                "unit_id": "unit-1",
                "unit_text": "23点",
                "action_mode": "answer",
                "candidate_question_ids": ["question-03"],
                "winner_question_id": "question-03",
                "needs_attribution": False,
                "raw_extracted_value": "23点",
            }
        ],
    )

    updated = result["state_patch"]["session_memory"]["answered_records"]["question-03"]
    assert result["modified_question_ids"] == ["question-03"]
    assert updated["selected_options"] == ["B"]
    assert updated["input_value"] == ""


def test_content_branch_modifies_answered_free_wake_from_contextual_sentence(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-9",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["answered_records"]["question-04"] = {
        "question_id": "question-04",
        "selected_options": ["C"],
        "input_value": "",
        "field_updates": {},
    }
    graph_state["session_memory"]["answered_question_ids"] = ["question-04"]
    graph_state["session_memory"]["unanswered_question_ids"] = ["question-01", "question-02", "question-03"]
    graph_state["session_memory"]["question_states"]["question-04"] = {
        "status": "answered",
        "attempt_count": 0,
        "last_action_mode": "answer",
    }
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03"]

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-9",
            channel="grpc",
            input_mode="message",
            raw_input="自由安排的话，我会七点起床",
            language_preference="zh-CN",
        ),
    )

    updated = result["state_patch"]["session_memory"]["answered_records"]["question-04"]
    assert result["modified_question_ids"] == ["question-04"]
    assert updated["selected_options"] == ["B"]
    assert updated["input_value"] == ""


def test_content_branch_prefers_latest_answered_time_question_for_change_request(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-10",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["answered_records"]["question-04"] = {
        "question_id": "question-04",
        "selected_options": ["C"],
        "input_value": "",
        "field_updates": {},
    }
    graph_state["session_memory"]["answered_question_ids"] = ["question-04"]
    graph_state["session_memory"]["unanswered_question_ids"] = ["question-01", "question-02", "question-03"]
    graph_state["session_memory"]["question_states"]["question-04"] = {
        "status": "answered",
        "attempt_count": 0,
        "last_action_mode": "answer",
    }
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03"]
    graph_state["session_memory"]["recent_turns"] = [
        {
            "turn_index": 1,
            "raw_input": "那7左右",
            "main_branch": "content",
            "turn_outcome": "answered",
            "recorded_question_ids": ["question-04"],
            "modified_question_ids": [],
            "partial_question_ids": [],
            "skipped_question_ids": [],
        }
    ]

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-10",
            channel="grpc",
            input_mode="message",
            raw_input="改成十点",
            language_preference="zh-CN",
        ),
    )

    updated = result["state_patch"]["session_memory"]["answered_records"]["question-04"]
    assert result["modified_question_ids"] == ["question-04"]
    assert updated["selected_options"] == ["D"]
    assert updated["input_value"] == ""


def test_map_content_value_maps_ten_minutes_to_question_08_option_a() -> None:
    assert map_content_value("question-08", "十来分钟") == {
        "selected_options": ["A"],
        "input_value": "",
    }


def test_map_content_value_maps_age_number_to_question_01_option_b() -> None:
    assert map_content_value("question-01", "34") == {
        "selected_options": ["B"],
        "input_value": "",
    }


def test_content_understand_time_candidates_include_free_schedule_questions_with_radio_input() -> None:
    question_catalog = {
        "question_order": ["question-01", "question-02", "question-03", "question-04"],
        "question_index": {
            "question-01": {"question_id": "question-01", "input_type": "radio"},
            "question-02": {"question_id": "question-02", "input_type": "time_range"},
            "question-03": {"question_id": "question-03", "input_type": "radio"},
            "question-04": {"question_id": "question-04", "input_type": "radio"},
        },
    }
    graph_state = create_graph_state(
        session_id="session-8",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-03"
    graph_state["session_memory"]["pending_question_ids"] = ["question-03", "question-04"]

    result = ContentUnderstandNode().run(
        graph_state,
        TurnInput(
            session_id="session-8",
            channel="grpc",
            input_mode="message",
            raw_input="23点",
            language_preference="zh-CN",
        ),
    )

    assert result["content_units"][0]["candidate_question_ids"] == [
        "question-02",
        "question-03",
        "question-04",
    ]


def test_content_apply_rejects_greeting_for_age_radio_question() -> None:
    question_catalog = {
        "question_order": ["question-01"],
        "question_index": {
            "question-01": {
                "question_id": "question-01",
                "title": "您的年龄段？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "18-24", "aliases": []},
                    {"option_id": "B", "label": "25-34", "aliases": []},
                ],
                "tags": ["profile"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["年龄"],
                },
            }
        },
    }
    graph_state = create_graph_state(
        session_id="session-invalid-age",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-invalid-age",
            channel="grpc",
            input_mode="message",
            raw_input="你好",
            language_preference="zh-CN",
        ),
    )

    assert result["applied_question_ids"] == []
    assert result["clarification_needed"] is True
    assert result["state_patch"]["session_memory"]["answered_records"] == {}


def test_content_understand_bypasses_llm_for_direct_answer_time_range(question_catalog: dict) -> None:
    provider = FakeLLMProvider(
        responses={
            "layer2/content_understand.md": """
            {
              "content_units": [],
              "clarification_needed": true,
              "clarification_reason": "should-not-be-used"
            }
            """
        }
    )
    graph_state = create_graph_state(
        session_id="session-direct-understand",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = provider

    understood = ContentUnderstandNode().run(
        graph_state,
        TurnInput(
            session_id="session-direct-understand",
            channel="grpc",
            input_mode="direct_answer",
            raw_input="11点睡",
            direct_answer_payload={
                "question_id": "question-02",
                "selected_options": [],
                "input_value": "11点睡",
            },
            language_preference="zh-CN",
        ),
    )

    assert provider.calls == []
    assert understood["clarification_needed"] is False
    assert understood["content_units"] == [
        {
            "unit_id": "unit-1",
            "unit_text": "11点睡",
            "action_mode": "answer",
            "candidate_question_ids": ["question-02"],
            "winner_question_id": "question-02",
            "needs_attribution": False,
            "raw_extracted_value": {"bedtime": "23:00"},
        }
    ]


def test_content_branch_records_direct_answer_time_range_partial(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-direct-partial",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = FakeLLMProvider(responses={})
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-direct-partial",
            channel="grpc",
            input_mode="direct_answer",
            raw_input="11点睡",
            direct_answer_payload={
                "question_id": "question-02",
                "selected_options": [],
                "input_value": "11点睡",
            },
            language_preference="zh-CN",
        ),
    )

    partial_entry = result["state_patch"]["session_memory"]["pending_partial_answers"]["question-02"]
    assert result["partial_question_ids"] == ["question-02"]
    assert result["applied_question_ids"] == []
    assert partial_entry["filled_fields"] == {"bedtime": "23:00"}
    assert partial_entry["missing_fields"] == ["wake_time"]


def test_content_branch_records_direct_answer_selected_options_without_mapping() -> None:
    question_catalog = {
        "question_order": ["question-05"],
        "question_index": {
            "question-05": {
                "question_id": "question-05",
                "title": "压力会影响睡眠吗？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "不会", "aliases": []},
                    {"option_id": "B", "label": "会", "aliases": []},
                ],
                "tags": ["sleep"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["pressure"],
                },
            }
        },
    }
    graph_state = create_graph_state(
        session_id="session-direct-selected-options",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["runtime"]["llm_provider"] = FakeLLMProvider(responses={})

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-direct-selected-options",
            channel="grpc",
            input_mode="direct_answer",
            raw_input="会",
            direct_answer_payload={
                "question_id": "question-05",
                "selected_options": ["B"],
                "input_value": "会",
            },
            language_preference="zh-CN",
        ),
    )

    answer = result["state_patch"]["session_memory"]["answered_records"]["question-05"]
    assert result["applied_question_ids"] == ["question-05"]
    assert answer["selected_options"] == ["B"]
    assert answer["input_value"] == "会"


def test_content_understand_resumes_skipped_partial_schedule_on_missing_field(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-skipped-partial-understand",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-01"
    graph_state["session_memory"]["pending_question_ids"] = ["question-01", "question-03", "question-04"]
    graph_state["session_memory"]["pending_partial_answers"]["question-02"] = {
        "question_id": "question-02",
        "filled_fields": {"bedtime": "23:00"},
        "missing_fields": ["wake_time"],
        "source_question_state": "partial",
    }
    graph_state["session_memory"]["partial_question_ids"] = ["question-02"]
    graph_state["session_memory"]["skipped_question_ids"] = ["question-02"]
    graph_state["session_memory"]["question_states"]["question-02"] = {
        "status": "skipped",
        "attempt_count": 1,
        "last_action_mode": "answer",
    }

    understood = ContentUnderstandNode().run(
        graph_state,
        TurnInput(
            session_id="session-skipped-partial-understand",
            channel="grpc",
            input_mode="message",
            raw_input="9点起",
            language_preference="zh-CN",
        ),
    )

    assert understood["clarification_needed"] is False
    assert understood["content_units"] == [
        {
            "unit_id": "unit-1",
            "unit_text": "9点起",
            "action_mode": "partial_completion",
            "candidate_question_ids": ["question-02"],
            "winner_question_id": "question-02",
            "needs_attribution": False,
            "raw_extracted_value": {"wake_time": "09:00"},
            "selected_options": [],
            "input_value": "",
            "field_updates": {"wake_time": "09:00"},
            "missing_fields": [],
        }
    ]


def test_content_understand_rule_maps_dynamic_radio_text_to_selected_option() -> None:
    question_catalog = {
        "question_order": ["custom-01"],
        "question_index": {
            "custom-01": {
                "question_id": "custom-01",
                "title": "您对卧室里的光线、声音敏感度如何？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "完全不敏感，在哪都能睡", "aliases": []},
                    {"option_id": "B", "label": "轻微敏感，但影响不大", "aliases": []},
                    {"option_id": "C", "label": "需要相对安静和避光的环境", "aliases": []},
                    {"option_id": "D", "label": "一点微光或细小声音就会惊醒", "aliases": []},
                    {"option_id": "E", "label": "必须绝对黑暗安静", "aliases": []},
                ],
                "tags": ["sleep"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["敏感", "光线", "声音"],
                },
            }
        },
    }
    graph_state = create_graph_state(
        session_id="session-dynamic-radio",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "custom-01"
    graph_state["session_memory"]["pending_question_ids"] = ["custom-01"]

    understood = ContentUnderstandNode().run(
        graph_state,
        TurnInput(
            session_id="session-dynamic-radio",
            channel="grpc",
            input_mode="message",
            raw_input="一点微光或细小声音就会惊醒",
            language_preference="zh-CN",
        ),
    )

    assert understood["clarification_needed"] is False
    assert understood["content_units"] == [
        {
            "unit_id": "unit-1",
            "unit_text": "一点微光或细小声音就会惊醒",
            "action_mode": "answer",
            "candidate_question_ids": ["custom-01"],
            "winner_question_id": "custom-01",
            "needs_attribution": False,
            "raw_extracted_value": "一点微光或细小声音就会惊醒",
            "selected_options": ["D"],
            "input_value": "",
            "field_updates": {},
            "missing_fields": [],
        }
    ]


def test_content_apply_consumes_preselected_options_without_remapping() -> None:
    question_catalog = {
        "question_order": ["custom-01"],
        "question_index": {
            "custom-01": {
                "question_id": "custom-01",
                "title": "您对卧室里的光线、声音敏感度如何？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "完全不敏感，在哪都能睡", "aliases": []},
                    {"option_id": "B", "label": "轻微敏感，但影响不大", "aliases": []},
                    {"option_id": "C", "label": "需要相对安静和避光的环境", "aliases": []},
                    {"option_id": "D", "label": "一点微光或细小声音就会惊醒", "aliases": []},
                    {"option_id": "E", "label": "必须绝对黑暗安静", "aliases": []},
                ],
                "tags": ["sleep"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["敏感", "光线", "声音"],
                },
            }
        },
    }
    graph_state = create_graph_state(
        session_id="session-preselected-radio",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )

    result = ContentApplyNode().run(
        graph_state,
        [
            {
                "unit_id": "unit-1",
                "unit_text": "很敏感",
                "action_mode": "answer",
                "candidate_question_ids": ["custom-01"],
                "winner_question_id": "custom-01",
                "needs_attribution": False,
                "raw_extracted_value": "很敏感",
                "selected_options": ["D"],
                "input_value": "",
                "field_updates": {},
                "missing_fields": [],
            }
        ],
    )

    answer = result["state_patch"]["session_memory"]["answered_records"]["custom-01"]
    assert result["applied_question_ids"] == ["custom-01"]
    assert answer["selected_options"] == ["D"]
    assert answer["input_value"] == ""


def test_content_understand_llm_can_return_selected_options_for_dynamic_radio() -> None:
    question_catalog = {
        "question_order": ["custom-02"],
        "question_index": {
            "custom-02": {
                "question_id": "custom-02",
                "title": "遇到压力或重要事情，您的睡眠会受影响吗？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "毫无影响，倒头就睡", "aliases": []},
                    {"option_id": "B", "label": "略有波动，但入睡时间不会变太长", "aliases": []},
                    {"option_id": "C", "label": "会翻来覆去一阵子才能睡着", "aliases": []},
                    {"option_id": "D", "label": "显著紧张，伴有心跳快或身体紧绷", "aliases": []},
                    {"option_id": "E", "label": "大脑停不下来，几乎睡不着", "aliases": []},
                ],
                "tags": ["sleep"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["压力", "睡眠"],
                },
            }
        },
    }
    graph_state = create_graph_state(
        session_id="session-llm-radio",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "custom-02"
    graph_state["session_memory"]["pending_question_ids"] = ["custom-02"]
    graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
        responses={
            "layer2/content_understand.md": """
            {
              "content_units": [
                {
                  "unit_id": "unit-1",
                  "unit_text": "大脑停不下来，几乎睡不着",
                  "action_mode": "answer",
                  "candidate_question_ids": ["custom-02"],
                  "winner_question_id": "custom-02",
                  "needs_attribution": false,
                  "raw_extracted_value": "大脑停不下来，几乎睡不着",
                  "selected_options": ["E"],
                  "input_value": "",
                  "field_updates": {},
                  "missing_fields": []
                }
              ],
              "clarification_needed": false,
              "clarification_reason": null
            }
            """
        }
    )

    understood = ContentUnderstandNode().run(
        graph_state,
        TurnInput(
            session_id="session-llm-radio",
            channel="grpc",
            input_mode="message",
            raw_input="大脑停不下来，几乎睡不着",
            language_preference="zh-CN",
        ),
    )

    assert understood["content_units"][0]["selected_options"] == ["E"]
    assert understood["content_units"][0]["input_value"] == ""


def test_content_branch_maps_sensitive_spoken_phrase_for_current_radio_question() -> None:
    question_catalog = {
        "question_order": ["custom-01"],
        "question_index": {
            "custom-01": {
                "question_id": "custom-01",
                "title": "您对卧室里的光线、声音敏感度如何？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "完全不敏感，在哪都能睡", "aliases": []},
                    {"option_id": "B", "label": "轻微敏感，但影响不大", "aliases": []},
                    {"option_id": "C", "label": "需要相对安静和避光的环境", "aliases": []},
                    {"option_id": "D", "label": "一点微光或细小声音就会惊醒", "aliases": []},
                    {"option_id": "E", "label": "必须绝对黑暗安静", "aliases": []},
                ],
                "tags": ["sleep"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["敏感", "光线", "声音"],
                },
            }
        },
    }
    graph_state = create_graph_state(
        session_id="session-spoken-sensitive",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "custom-01"
    graph_state["session_memory"]["pending_question_ids"] = ["custom-01"]

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-spoken-sensitive",
            channel="grpc",
            input_mode="message",
            raw_input="很敏感",
            language_preference="zh-CN",
        ),
    )

    answer = result["state_patch"]["session_memory"]["answered_records"]["custom-01"]
    assert result["applied_question_ids"] == ["custom-01"]
    assert answer["selected_options"] == ["D"]


def test_content_branch_skips_attribution_for_single_candidate_closed_by_understand() -> None:
    question_catalog = {
        "question_order": ["question-05"],
        "question_index": {
            "question-05": {
                "question_id": "question-05",
                "title": "遇到压力或重要事情，您的睡眠会受影响吗？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "毫无影响，倒头就睡", "aliases": []},
                    {"option_id": "E", "label": "大脑停不下来，几乎睡不着", "aliases": []},
                ],
                "tags": ["sleep"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["压力", "睡眠"],
                },
            }
        },
    }
    graph_state = create_graph_state(
        session_id="session-branch-skip-attribution",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-05"
    graph_state["session_memory"]["pending_question_ids"] = ["question-05"]

    branch = ContentBranch()

    def _fake_understand(_graph_state: dict, _turn_input: TurnInput) -> dict:
        return {
            "content_units": [
                {
                    "unit_id": "unit-1",
                    "unit_text": "大脑停不下来，几乎睡不着",
                    "action_mode": "answer",
                    "candidate_question_ids": ["question-05"],
                    "winner_question_id": None,
                    "needs_attribution": True,
                    "raw_extracted_value": "大脑停不下来，几乎睡不着",
                    "selected_options": ["E"],
                    "input_value": "",
                    "field_updates": {},
                    "missing_fields": [],
                }
            ],
            "clarification_needed": False,
            "clarification_reason": None,
        }

    def _fail_attribution(_graph_state: dict, _content_unit: dict) -> dict:
        raise AssertionError("FinalAttributionNode should not run for a single closed candidate")

    branch._understand.run = _fake_understand  # type: ignore[method-assign]
    branch._attribution.run = _fail_attribution  # type: ignore[method-assign]

    result = branch.run(
        graph_state,
        TurnInput(
            session_id="session-branch-skip-attribution",
            channel="grpc",
            input_mode="message",
            raw_input="大脑停不下来，几乎睡不着",
            language_preference="zh-CN",
        ),
    )

    assert result["applied_question_ids"] == ["question-05"]
    answer = result["state_patch"]["session_memory"]["answered_records"]["question-05"]
    assert answer["selected_options"] == ["E"]

def test_content_branch_skips_attribution_for_single_candidate_without_selected_options() -> None:
    question_catalog = {
        "question_order": ["question-05"],
        "question_index": {
            "question-05": {
                "question_id": "question-05",
                "title": "遇到压力或重要事情，您的睡眠会受影响吗？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "毫无影响，倒头就睡", "aliases": []},
                    {"option_id": "E", "label": "大脑停不下来，几乎睡不着", "aliases": []},
                ],
                "tags": ["sleep"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["压力", "睡眠"],
                },
            }
        },
    }
    graph_state = create_graph_state(
        session_id="session-branch-skip-attribution-no-options",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-05"
    graph_state["session_memory"]["pending_question_ids"] = ["question-05"]

    branch = ContentBranch()

    def _fake_understand(_graph_state: dict, _turn_input: TurnInput) -> dict:
        return {
            "content_units": [
                {
                    "unit_id": "unit-1",
                    "unit_text": "大脑停不下来，几乎睡不着",
                    "action_mode": "answer",
                    "candidate_question_ids": ["question-05"],
                    "winner_question_id": None,
                    "needs_attribution": True,
                    "raw_extracted_value": "大脑停不下来，几乎睡不着",
                    "selected_options": [],
                    "input_value": "",
                    "field_updates": {},
                    "missing_fields": [],
                }
            ],
            "clarification_needed": False,
            "clarification_reason": None,
        }

    def _fail_attribution(_graph_state: dict, _content_unit: dict) -> dict:
        raise AssertionError("FinalAttributionNode should not run for single-candidate units")

    branch._understand.run = _fake_understand  # type: ignore[method-assign]
    branch._attribution.run = _fail_attribution  # type: ignore[method-assign]

    result = branch.run(
        graph_state,
        TurnInput(
            session_id="session-branch-skip-attribution-no-options",
            channel="grpc",
            input_mode="message",
            raw_input="大脑停不下来，几乎睡不着",
            language_preference="zh-CN",
        ),
    )

    assert result["applied_question_ids"] == ["question-05"]

def test_content_branch_skips_attribution_for_zero_candidate_units() -> None:
    question_catalog = {
        "question_order": ["question-05"],
        "question_index": {
            "question-05": {
                "question_id": "question-05",
                "title": "遇到压力或重要事情，您的睡眠会受影响吗？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "毫无影响，倒头就睡", "aliases": []},
                    {"option_id": "E", "label": "大脑停不下来，几乎睡不着", "aliases": []},
                ],
                "tags": ["sleep"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["压力", "睡眠"],
                },
            }
        },
    }
    graph_state = create_graph_state(
        session_id="session-branch-skip-attribution-no-candidates",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-05"
    graph_state["session_memory"]["pending_question_ids"] = ["question-05"]

    branch = ContentBranch()

    def _fake_understand(_graph_state: dict, _turn_input: TurnInput) -> dict:
        return {
            "content_units": [
                {
                    "unit_id": "unit-1",
                    "unit_text": "大脑停不下来，几乎睡不着",
                    "action_mode": "answer",
                    "candidate_question_ids": [],
                    "winner_question_id": None,
                    "needs_attribution": True,
                    "raw_extracted_value": "大脑停不下来，几乎睡不着",
                    "selected_options": [],
                    "input_value": "",
                    "field_updates": {},
                    "missing_fields": [],
                }
            ],
            "clarification_needed": False,
            "clarification_reason": None,
        }

    def _fail_attribution(_graph_state: dict, _content_unit: dict) -> dict:
        raise AssertionError("FinalAttributionNode should not run for units without candidates")

    branch._understand.run = _fake_understand  # type: ignore[method-assign]
    branch._attribution.run = _fail_attribution  # type: ignore[method-assign]

    result = branch.run(
        graph_state,
        TurnInput(
            session_id="session-branch-skip-attribution-no-candidates",
            channel="grpc",
            input_mode="message",
            raw_input="大脑停不下来，几乎睡不着",
            language_preference="zh-CN",
        ),
    )

    assert result["applied_question_ids"] == []


def test_content_branch_uses_llm_option_mapping_after_attribution_resolution() -> None:
    question_catalog = {
        "question_order": ["question-05", "question-07", "question-08"],
        "question_index": {
            "question-05": {
                "question_id": "question-05",
                "title": "遇到压力或重要事情，您的睡眠会受影响吗？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "毫无影响，倒头就睡", "aliases": []},
                    {"option_id": "E", "label": "大脑停不下来，几乎睡不着", "aliases": []},
                ],
                "tags": ["sleep"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["压力", "睡眠"],
                },
            },
            "question-07": {
                "question_id": "question-07",
                "title": "最影响你睡好的问题是哪一个？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "B", "label": "躺下很久才能睡着", "aliases": []},
                ],
                "tags": ["sleep"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["入睡困难"],
                },
            },
            "question-08": {
                "question_id": "question-08",
                "title": "半夜醒来后，再次入睡困难吗？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "C", "label": "比较困难，需要 30 分钟以上", "aliases": []},
                ],
                "tags": ["sleep"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["再次入睡"],
                },
            },
        },
    }
    graph_state = create_graph_state(
        session_id="session-llm-option-mapping",
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
                  "unit_text": "压力很大睡不着",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-05", "question-07", "question-08"],
                  "winner_question_id": null,
                  "needs_attribution": true,
                  "raw_extracted_value": "压力导致入睡困难",
                  "selected_options": [],
                  "input_value": "压力很大睡不着",
                  "field_updates": {},
                  "missing_fields": []
                }
              ],
              "clarification_needed": false,
              "clarification_reason": null
            }
            """,
            "layer2/final_attribution.md": """
            {
              "winner_question_id": "question-05",
              "needs_clarification": false,
              "reason": "pressure-related sleep impact is the best match"
            }
            """,
            "layer2/text_option_mapping.md": """
            {
              "selected_options": ["E"],
              "confidence": 0.93,
              "reason": "pressure-driven inability to sleep best matches option E"
            }
            """,
        }
    )
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]

    result = ContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-llm-option-mapping",
            channel="grpc",
            input_mode="message",
            raw_input="压力很大睡不着",
            language_preference="zh-CN",
        ),
    )

    answer = result["state_patch"]["session_memory"]["answered_records"]["question-05"]
    assert result["applied_question_ids"] == ["question-05"]
    assert answer["selected_options"] == ["E"]
    assert answer["input_value"] == ""
