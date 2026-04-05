"""Integration tests for the minimal runtime engine."""

from somni_graph_quiz.contracts.graph_state import create_graph_state
from somni_graph_quiz.contracts.turn_input import TurnInput
from somni_graph_quiz.runtime.engine import GraphRuntimeEngine


def test_engine_routes_non_content_turn_to_pullback_response(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-1",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-1",
        channel="grpc",
        input_mode="message",
        raw_input="谢谢你",
        language_preference="zh-CN",
    ))

    assert result["finalized"] is False
    assert result["pending_question"]["question_id"] == "question-01"
    assert "谢谢" in result["assistant_message"] or "不客气" in result["assistant_message"]
    assert "How old are you?" in result["assistant_message"]


def test_engine_greeting_pullback_does_not_record_answer(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-greeting",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-greeting",
        channel="grpc",
        input_mode="message",
        raw_input="你好",
        language_preference="zh-CN",
    ))

    assert result["answer_record"]["answers"] == []
    assert result["pending_question"]["question_id"] == "question-01"
    assert "你好" in result["assistant_message"]
    assert "How old are you?" in result["assistant_message"]


def test_engine_routes_content_turn_and_updates_answer_record(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-1",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="en",
    )
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-1",
        channel="grpc",
        input_mode="message",
        raw_input="22",
        language_preference="en",
    ))

    assert result["answer_record"]["answers"] == [
        {
            "question_id": "question-01",
            "selected_options": [],
            "input_value": "22",
            "field_updates": {},
        }
    ]
    assert result["pending_question"]["question_id"] == "question-02"
    assert "next question" in result["assistant_message"].lower()


def test_engine_records_direct_answer_time_range_full(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-direct-full",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-direct-full",
        channel="grpc",
        input_mode="direct_answer",
        raw_input="23点睡，7点起",
        direct_answer_payload={
            "question_id": "question-02",
            "selected_options": [],
            "input_value": "23点睡，7点起",
        },
        language_preference="zh-CN",
    ))

    assert result["answer_record"]["answers"] == [
        {
            "question_id": "question-02",
            "selected_options": [],
            "input_value": "23:00-07:00",
            "field_updates": {"bedtime": "23:00", "wake_time": "07:00"},
        }
    ]
    assert result["pending_question"]["question_id"] == "question-03"


def test_engine_keeps_direct_answer_time_range_partial_and_asks_followup(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-direct-partial",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
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
    ))

    assert result["answer_record"]["answers"] == []
    assert result["pending_question"]["question_id"] == "question-02"
    assert result["updated_graph_state"]["session_memory"]["pending_partial_answers"]["question-02"]["filled_fields"] == {
        "bedtime": "23:00"
    }
    assert "起床" in result["assistant_message"]


def test_engine_keeps_partial_schedule_and_asks_for_missing_field(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-1",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-1",
        channel="grpc",
        input_mode="message",
        raw_input="11点睡",
        language_preference="zh-CN",
    ))

    assert result["answer_record"]["answers"] == []
    assert result["pending_question"]["question_id"] == "question-02"
    assert result["updated_graph_state"]["session_memory"]["pending_partial_answers"]["question-02"]["filled_fields"] == {
        "bedtime": "23:00"
    }
    assert "起床" in result["assistant_message"]


def test_engine_completes_partial_schedule_on_followup(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-1",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]
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
        "last_action_mode": "answer",
    }
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-1",
        channel="grpc",
        input_mode="message",
        raw_input="7点起",
        language_preference="zh-CN",
    ))

    assert result["answer_record"]["answers"][0]["question_id"] == "question-02"
    assert result["answer_record"]["answers"][0]["input_value"] == "23:00-07:00"
    assert result["pending_question"]["question_id"] == "question-03"


def test_engine_auto_skips_partial_after_two_invalid_followups(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-1",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]
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
        "last_action_mode": "answer",
    }
    engine = GraphRuntimeEngine()

    first = engine.run_turn(graph_state, TurnInput(
        session_id="session-1",
        channel="grpc",
        input_mode="message",
        raw_input="不知道",
        language_preference="zh-CN",
    ))
    second = engine.run_turn(first["updated_graph_state"], TurnInput(
        session_id="session-1",
        channel="grpc",
        input_mode="message",
        raw_input="还是不知道",
        language_preference="zh-CN",
    ))

    assert second["updated_graph_state"]["session_memory"]["skipped_question_ids"] == ["question-02"]
    assert second["updated_graph_state"]["session_memory"]["pending_partial_answers"]["question-02"]["filled_fields"] == {
        "bedtime": "23:00"
    }
    assert second["pending_question"]["question_id"] == "question-03"


def test_engine_resumes_skipped_partial_schedule_on_later_followup(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-skip-resume",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    engine = GraphRuntimeEngine()

    first = engine.run_turn(graph_state, TurnInput(
        session_id="session-skip-resume",
        channel="grpc",
        input_mode="message",
        raw_input="11点睡",
        language_preference="zh-CN",
    ))
    skipped = engine.run_turn(first["updated_graph_state"], TurnInput(
        session_id="session-skip-resume",
        channel="grpc",
        input_mode="message",
        raw_input="跳过",
        language_preference="zh-CN",
    ))
    resumed = engine.run_turn(skipped["updated_graph_state"], TurnInput(
        session_id="session-skip-resume",
        channel="grpc",
        input_mode="message",
        raw_input="9点起",
        language_preference="zh-CN",
    ))

    answers = {item["question_id"]: item for item in resumed["answer_record"]["answers"]}
    assert answers["question-02"]["input_value"] == "23:00-09:00"
    assert resumed["updated_graph_state"]["session_memory"]["pending_partial_answers"] == {}
    assert resumed["updated_graph_state"]["session_memory"]["skipped_question_ids"] == []
    assert resumed["pending_question"]["question_id"] == "question-01"


def test_engine_keeps_skipped_partial_when_followup_input_targets_other_question(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-skip-keep",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    engine = GraphRuntimeEngine()

    first = engine.run_turn(graph_state, TurnInput(
        session_id="session-skip-keep",
        channel="grpc",
        input_mode="message",
        raw_input="11点睡",
        language_preference="zh-CN",
    ))
    skipped = engine.run_turn(first["updated_graph_state"], TurnInput(
        session_id="session-skip-keep",
        channel="grpc",
        input_mode="message",
        raw_input="跳过",
        language_preference="zh-CN",
    ))
    answered_age = engine.run_turn(skipped["updated_graph_state"], TurnInput(
        session_id="session-skip-keep",
        channel="grpc",
        input_mode="message",
        raw_input="29岁",
        language_preference="zh-CN",
    ))

    answers = {item["question_id"]: item for item in answered_age["answer_record"]["answers"]}
    assert answers["question-01"]["input_value"] == "29"
    assert "question-02" not in answers
    assert answered_age["updated_graph_state"]["session_memory"]["pending_partial_answers"]["question-02"][
        "filled_fields"
    ] == {"bedtime": "23:00"}
    assert answered_age["updated_graph_state"]["session_memory"]["skipped_question_ids"] == ["question-02"]
    assert answered_age["pending_question"]["question_id"] == "question-03"


def test_engine_undo_restores_previous_answer(question_catalog: dict) -> None:
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
        "input_value": "29",
        "field_updates": {},
    }
    graph_state["session_memory"]["previous_answer_record"] = {
        "question-01": {
            "question_id": "question-01",
            "selected_options": [],
            "input_value": "22",
            "field_updates": {},
        }
    }
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-1",
        channel="grpc",
        input_mode="message",
        raw_input="undo",
        language_preference="en",
    ))

    assert result["updated_graph_state"]["session_memory"]["answered_records"]["question-01"]["input_value"] == "22"
    assert "continue" in result["assistant_message"].lower() or "restored" in result["assistant_message"].lower()


def test_engine_view_records_keeps_current_question(question_catalog: dict) -> None:
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
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-1",
        channel="grpc",
        input_mode="message",
        raw_input="view",
        language_preference="en",
    ))

    assert result["pending_question"]["question_id"] == graph_state["session_memory"]["current_question_id"]
    assert "summary" in result["assistant_message"].lower()


def test_engine_routes_modify_previous_control_to_last_answered_question(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-modify-prev",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
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
    graph_state["session_memory"]["recent_turns"] = [
        {
            "turn_index": 0,
            "recorded_question_ids": ["question-01"],
            "modified_question_ids": [],
            "raw_input": "22",
        }
    ]
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-modify-prev",
        channel="grpc",
        input_mode="message",
        raw_input="改上一题",
        language_preference="zh-CN",
    ))

    assert result["pending_question"]["question_id"] == "question-01"
    assert result["updated_graph_state"]["session_memory"]["pending_modify_context"]["question_id"] == "question-01"


def test_engine_handles_same_turn_modify_and_answer(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-mixed",
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
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-mixed",
        channel="grpc",
        input_mode="message",
        raw_input="年龄不是28，是29；每天11点睡觉，7点起床",
        language_preference="zh-CN",
    ))

    answers = {item["question_id"]: item for item in result["answer_record"]["answers"]}
    assert answers["question-01"]["input_value"] == "29"
    assert answers["question-02"]["input_value"] == "23:00-07:00"
    assert result["updated_graph_state"]["session_memory"]["previous_answer_record"]["question-01"]["input_value"] == "28"
    assert result["pending_question"]["question_id"] == "question-03"


def test_engine_identity_pullback_keeps_current_question(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-identity-pullback",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-identity-pullback",
        channel="grpc",
        input_mode="message",
        raw_input="你是谁",
        language_preference="zh-CN",
    ))

    assert result["pending_question"]["question_id"] == "question-02"
    assert "睡眠" in result["assistant_message"]


def test_engine_view_previous_keeps_current_question_and_mentions_previous_answer(
    question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="session-view-previous",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["answered_records"]["question-01"] = {
        "question_id": "question-01",
        "selected_options": ["B"],
        "input_value": "",
        "field_updates": {},
    }
    graph_state["session_memory"]["answered_question_ids"] = ["question-01"]
    graph_state["session_memory"]["recent_turns"] = [
        {
            "turn_index": 0,
            "recorded_question_ids": ["question-01"],
            "modified_question_ids": [],
            "raw_input": "B",
        }
    ]
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]
    engine = GraphRuntimeEngine()

    result = engine.run_turn(graph_state, TurnInput(
        session_id="session-view-previous",
        channel="grpc",
        input_mode="message",
        raw_input="查看上一题记录",
        language_preference="zh-CN",
    ))

    assert result["pending_question"]["question_id"] == "question-02"
    assert "上一题" in result["assistant_message"]
    assert "B" in result["assistant_message"]


def test_engine_does_not_force_unrelated_content_into_current_age_question() -> None:
    question_catalog = {
        "question_order": ["question-01", "question-05", "question-06"],
        "question_index": {
            "question-01": {
                "question_id": "question-01",
                "title": "您的年龄段？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "18-24 岁", "aliases": []},
                    {"option_id": "B", "label": "25-34 岁", "aliases": []},
                ],
                "tags": ["基础信息"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["年龄"],
                },
            },
            "question-05": {
                "question_id": "question-05",
                "title": "遇到压力或重要事情，您的睡眠会受影响吗？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "毫无影响，倒头就睡", "aliases": []},
                    {"option_id": "E", "label": "大脑停不下来，几乎睡不着", "aliases": []},
                ],
                "tags": ["人格判定"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["压力", "睡眠"],
                },
            },
            "question-06": {
                "question_id": "question-06",
                "title": "您对卧室里的光线、声音敏感度如何？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "B", "label": "轻微敏感，但影响不大", "aliases": []},
                    {"option_id": "D", "label": "一点微光或细小声音就会惊醒", "aliases": []},
                ],
                "tags": ["人格判定"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["声光", "敏感"],
                },
            },
        },
    }
    graph_state = create_graph_state(
        session_id="session-unrelated-age",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    engine = GraphRuntimeEngine()

    pressure_result = engine.run_turn(graph_state, TurnInput(
        session_id="session-unrelated-age",
        channel="grpc",
        input_mode="message",
        raw_input="大脑停不下来，几乎睡不着",
        language_preference="zh-CN",
    ))

    pressure_answers = {item["question_id"]: item for item in pressure_result["answer_record"]["answers"]}
    assert pressure_answers["question-05"]["selected_options"] == ["E"]
    assert pressure_result["pending_question"]["question_id"] == "question-01"
    assert "年龄" in pressure_result["assistant_message"]

    sensitivity_result = engine.run_turn(pressure_result["updated_graph_state"], TurnInput(
        session_id="session-unrelated-age",
        channel="grpc",
        input_mode="message",
        raw_input="对声光轻微敏感，但影响不大",
        language_preference="zh-CN",
    ))

    sensitivity_answers = {item["question_id"]: item for item in sensitivity_result["answer_record"]["answers"]}
    assert sensitivity_answers["question-06"]["selected_options"] == ["B"]
    assert sensitivity_result["pending_question"]["question_id"] == "question-01"
    assert "年龄" in sensitivity_result["assistant_message"]
