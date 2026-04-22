"""gRPC adapter tests for weather default city behavior."""

from somni_quiz_ai.grpc.generated import somni_quiz_pb2

from somni_graph_quiz.adapters.grpc.service import GrpcQuizService
from somni_graph_quiz.llm.client import FakeLLMProvider


def _build_questionnaire() -> list:
    return [
        somni_quiz_pb2.BusinessQuestion(
            question_id="question-01",
            title="How old are you?",
            input_type="text",
        ),
        somni_quiz_pb2.BusinessQuestion(
            question_id="question-02",
            title="What time do you usually sleep and wake?",
            input_type="time_range",
        ),
    ]


def test_init_quiz_without_default_city_keeps_empty_session_default_city() -> None:
    service = GrpcQuizService()
    request = somni_quiz_pb2.InitQuizRequest(
        session_id="session-no-default-city",
        language="zh-CN",
        questionnaire=_build_questionnaire(),
        quiz_mode="dynamic",
    )

    response = service.InitQuiz(request, context=None)

    assert response.success is True
    assert service._sessions["session-no-default-city"].graph_state["session"]["default_city"] == ""


def test_chat_quiz_weather_query_without_default_city_asks_for_city() -> None:
    service = GrpcQuizService()
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="session-weather-no-city",
            language="zh-CN",
            questionnaire=_build_questionnaire(),
            quiz_mode="dynamic",
        ),
        context=None,
    )
    service._sessions["session-weather-no-city"].graph_state["runtime"]["llm_provider"] = None
    service._sessions["session-weather-no-city"].graph_state["runtime"]["llm_available"] = False

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-weather-no-city",
            message="今天天气怎么样",
        ),
        context=None,
    )

    assert response.success is True
    assert response.answer_status_code == "NOT_RECORDED"
    assert response.progress_percent == 0.0
    assert response.pending_question.question_id == "question-01"
    assert "城市" in response.assistant_message


def test_chat_quiz_single_partial_completion_does_not_emit_companion_overlay_when_inactive() -> None:
    service = GrpcQuizService()
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="session-single-partial-completion-no-overlay",
            language="zh-CN",
            questionnaire=[
                somni_quiz_pb2.BusinessQuestion(
                    question_id="question-01",
                    title="您的年龄段？",
                    input_type="radio",
                    tags=["基础信息"],
                    options=[
                        somni_quiz_pb2.BusinessOption(option_id="A", option_text="18-24 岁"),
                        somni_quiz_pb2.BusinessOption(option_id="B", option_text="25-34 岁"),
                    ],
                ),
                somni_quiz_pb2.BusinessQuestion(
                    question_id="question-02",
                    title="您平时通常的作息？",
                    input_type="time_range",
                    tags=["基础信息"],
                ),
                somni_quiz_pb2.BusinessQuestion(
                    question_id="question-03",
                    title="您对卧室环境的敏感度更接近哪种情况？",
                    input_type="radio",
                    tags=["睡眠环境"],
                    options=[
                        somni_quiz_pb2.BusinessOption(option_id="A", option_text="不太敏感"),
                        somni_quiz_pb2.BusinessOption(option_id="B", option_text="一般"),
                        somni_quiz_pb2.BusinessOption(option_id="C", option_text="比较敏感"),
                    ],
                ),
            ],
            quiz_mode="dynamic",
        ),
        context=None,
    )
    snapshot = service._sessions["session-single-partial-completion-no-overlay"]
    snapshot.graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "content",
              "non_content_intent": "none",
              "normalized_input": "11点睡"
            }
            """,
            "layer2/content_understand.md": """
            {
              "content_units": [
                {
                  "unit_id": "unit-1",
                  "unit_text": "11点睡",
                  "action_mode": "partial_completion",
                  "candidate_question_ids": ["question-02"],
                  "winner_question_id": "question-02",
                  "needs_attribution": false,
                  "raw_extracted_value": "11点睡",
                  "selected_options": [],
                  "input_value": "",
                  "field_updates": {"bedtime": "23:00"},
                  "missing_fields": []
                }
              ],
              "clarification_needed": false,
              "clarification_reason": null
            }
            """,
            "layer1/companion_decision.md": """
            {
              "companion_action": "exit",
              "companion_mode": "none",
              "continue_chat_intent": "weak",
              "answer_status_override": "NOT_RECORDED",
              "reason": "return to quiz"
            }
            """,
            "layer3/companion_response.md": """
            {
              "assistant_message": "这是一条不该出现的 companion 拉回文案。"
            }
            """,
        }
    )
    snapshot.graph_state["runtime"]["llm_available"] = True
    snapshot.graph_state["session_memory"]["answered_records"] = {
        "question-01": {
            "question_id": "question-01",
            "selected_options": ["A"],
            "input_value": "",
            "field_updates": {},
        }
    }
    snapshot.graph_state["session_memory"]["answered_question_ids"] = ["question-01"]
    snapshot.graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03"]
    snapshot.graph_state["session_memory"]["current_question_id"] = "question-02"
    snapshot.graph_state["session_memory"]["unanswered_question_ids"] = ["question-02", "question-03"]
    snapshot.graph_state["session_memory"]["pending_partial_answers"]["question-02"] = {
        "question_id": "question-02",
        "filled_fields": {"wake_time": "11:00"},
        "missing_fields": ["bedtime"],
        "source_question_state": "partial",
    }
    snapshot.graph_state["session_memory"]["partial_question_ids"] = ["question-02"]
    snapshot.graph_state["session_memory"]["question_states"]["question-01"]["status"] = "answered"
    snapshot.graph_state["session_memory"]["question_states"]["question-02"] = {
        "status": "partial",
        "attempt_count": 0,
        "last_action_mode": "answer",
    }
    snapshot.graph_state["session_memory"]["companion_context"] = {
        "active": False,
        "mode": None,
        "entered_from_question_id": None,
        "rounds_since_enter": 0,
        "last_turn_continue_chat_intent": None,
        "last_trigger_reason": None,
    }

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-single-partial-completion-no-overlay",
            message="11点睡",
        ),
        context=None,
    )

    assert response.success is True
    assert response.answer_status_code == "RECORDED"
    assert response.pending_question.question_id == "question-03"
    assert "companion" not in response.assistant_message.lower()
    assert "不该出现" not in response.assistant_message


def test_chat_quiz_pure_current_partial_answer_exits_active_companion_even_when_llm_marks_strong_chat() -> None:
    service = GrpcQuizService()
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="session-active-companion-pure-answer-should-exit",
            language="zh-CN",
            questionnaire=[
                somni_quiz_pb2.BusinessQuestion(
                    question_id="question-01",
                    title="您的年龄段？",
                    input_type="radio",
                    tags=["基础信息"],
                    options=[
                        somni_quiz_pb2.BusinessOption(option_id="A", option_text="18-24 岁"),
                        somni_quiz_pb2.BusinessOption(option_id="B", option_text="25-34 岁"),
                    ],
                ),
                somni_quiz_pb2.BusinessQuestion(
                    question_id="question-02",
                    title="您平时通常几点睡？",
                    input_type="text",
                    tags=["作息"],
                ),
                somni_quiz_pb2.BusinessQuestion(
                    question_id="question-03",
                    title="您更希望调整哪方面的睡眠问题？",
                    input_type="radio",
                    tags=["睡眠目标"],
                    options=[
                        somni_quiz_pb2.BusinessOption(option_id="A", option_text="入睡"),
                        somni_quiz_pb2.BusinessOption(option_id="B", option_text="起床"),
                    ],
                ),
            ],
            quiz_mode="dynamic",
        ),
        context=None,
    )
    snapshot = service._sessions["session-active-companion-pure-answer-should-exit"]
    snapshot.graph_state["runtime"]["llm_provider"] = FakeLLMProvider(
        responses={
            "layer1/turn_classify.md": """
            {
              "main_branch": "content",
              "non_content_intent": "none",
              "normalized_input": "11点睡"
            }
            """,
            "layer2/content_understand.md": """
            {
              "content_units": [
                {
                  "unit_id": "unit-1",
                  "unit_text": "11点睡",
                  "action_mode": "answer",
                  "candidate_question_ids": ["question-02"],
                  "winner_question_id": "question-02",
                  "needs_attribution": false,
                  "raw_extracted_value": "11点睡",
                  "selected_options": [],
                  "input_value": "23:00",
                  "field_updates": {},
                  "missing_fields": []
                }
              ],
              "clarification_needed": false,
              "clarification_reason": null
            }
            """,
            "layer1/companion_decision.md": """
            {
              "companion_action": "stay",
              "companion_mode": "supportive",
              "continue_chat_intent": "strong",
              "answer_status_override": "NOT_RECORDED",
              "reason": "user still wants to keep chatting"
            }
            """,
            "layer3/companion_response.md": """
            {
              "assistant_message": "这是一条不该出现的 companion 挽留文案。"
            }
            """,
        }
    )
    snapshot.graph_state["runtime"]["llm_available"] = True
    snapshot.graph_state["session_memory"]["answered_records"] = {
        "question-01": {
            "question_id": "question-01",
            "selected_options": ["A"],
            "input_value": "",
            "field_updates": {},
        }
    }
    snapshot.graph_state["session_memory"]["answered_question_ids"] = ["question-01"]
    snapshot.graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03"]
    snapshot.graph_state["session_memory"]["current_question_id"] = "question-02"
    snapshot.graph_state["session_memory"]["unanswered_question_ids"] = ["question-02", "question-03"]
    snapshot.graph_state["session_memory"]["question_states"]["question-01"]["status"] = "answered"
    snapshot.graph_state["session_memory"]["question_states"]["question-02"] = {
        "status": "unanswered",
        "attempt_count": 0,
        "last_action_mode": "answer",
    }
    snapshot.graph_state["session_memory"]["question_states"]["question-03"] = {
        "status": "unanswered",
        "attempt_count": 0,
        "last_action_mode": "answer",
    }
    snapshot.graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "supportive",
        "entered_from_question_id": "question-02",
        "rounds_since_enter": 1,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "distress",
    }

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-active-companion-pure-answer-should-exit",
            message="11点睡",
        ),
        context=None,
    )

    assert response.success is True
    assert response.answer_status_code == "PARTIAL"
    assert response.pending_question.question_id == "question-02"
    assert "companion" not in response.assistant_message.lower()
    assert "不该出现" not in response.assistant_message
