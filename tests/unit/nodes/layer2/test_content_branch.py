"""Tests for content branch integration."""

from somni_graph_quiz.contracts.graph_state import create_graph_state
from somni_graph_quiz.contracts.turn_input import TurnInput
from somni_graph_quiz.llm.client import FakeLLMProvider
from somni_graph_quiz.nodes.layer2.content.apply import ContentApplyNode
from somni_graph_quiz.nodes.layer2.content.attribution import FinalAttributionNode
from somni_graph_quiz.nodes.layer2.content.branch import ContentBranch
from somni_graph_quiz.nodes.layer2.content.mapping import map_content_value
from somni_graph_quiz.nodes.layer2.content.understand import ContentUnderstandNode


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
        }
    ]
