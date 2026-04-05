"""gRPC mapper."""

from __future__ import annotations

from google.protobuf.struct_pb2 import Struct

from somni_quiz_ai.grpc.generated import somni_quiz_pb2

from somni_graph_quiz.contracts.turn_input import TurnInput


def map_questionnaire_to_catalog(questionnaire: list) -> dict:
    """Map proto questionnaire messages into the runtime catalog shape."""
    question_order = []
    question_index = {}
    for question in questionnaire:
        question_order.append(question.question_id)
        question_index[question.question_id] = {
            "question_id": question.question_id,
            "title": question.title,
            "description": question.description,
            "input_type": question.input_type,
            "tags": list(question.tags),
            "options": [
                {
                    "option_id": option.option_id,
                    "label": option.option_text,
                    "aliases": [option.label_value] if option.label_value else [],
                }
                for option in question.options
            ],
            "metadata": {
                "allow_partial": question.input_type == "time_range",
                "structured_kind": question.input_type or None,
                "response_style": "followup" if question.input_type == "time_range" else "default",
                "matching_hints": list(question.tags),
            },
        }
    return {"question_order": question_order, "question_index": question_index}


def map_chat_request_to_turn_input(
    request: somni_quiz_pb2.ChatQuizRequest,
    *,
    language_preference: str,
) -> TurnInput:
    """Map a gRPC chat request into runtime input."""
    if request.HasField("direct_answer"):
        raw_input = request.direct_answer.input_value or " ".join(request.direct_answer.selected_options)
        direct_answer_payload = {
            "question_id": request.direct_answer.question_id,
            "selected_options": list(request.direct_answer.selected_options),
            "input_value": request.direct_answer.input_value,
        }
        return TurnInput(
            session_id=request.session_id,
            channel="grpc",
            input_mode="direct_answer",
            raw_input=raw_input,
            direct_answer_payload=direct_answer_payload,
            language_preference=language_preference,
        )
    return TurnInput(
        session_id=request.session_id,
        channel="grpc",
        input_mode="message",
        raw_input=request.message,
        language_preference=language_preference,
    )


def build_pending_question_message(pending_question: dict | None) -> somni_quiz_pb2.PendingQuestion:
    """Map a runtime pending question into the proto response shape."""
    if pending_question is None:
        return somni_quiz_pb2.PendingQuestion()
    return somni_quiz_pb2.PendingQuestion(
        question_id=pending_question.get("question_id", ""),
        qid=pending_question.get("question_id", ""),
        title=pending_question.get("title", ""),
        input_type=pending_question.get("input_type", ""),
        tags=list(pending_question.get("tags", [])),
        options=[
            somni_quiz_pb2.PendingOption(
                option_id=option.get("option_id", ""),
                option_text=option.get("label", option.get("option_text", "")),
            )
            for option in pending_question.get("options", [])
        ],
    )


def build_answer_record_message(answer_record: dict) -> somni_quiz_pb2.AnswerRecord:
    """Map a runtime answer record into the proto response shape."""
    answers = []
    for answer in answer_record.get("answers", []):
        value = somni_quiz_pb2.AnswerValue(option_codes=list(answer.get("selected_options", [])))
        field_updates = answer.get("field_updates", {})
        if "bedtime" in field_updates:
            value.bedtime = field_updates["bedtime"]
        if "wake_time" in field_updates:
            value.wake_time = field_updates["wake_time"]
        answers.append(
            somni_quiz_pb2.AnswerItem(
                question_id=answer.get("question_id", ""),
                value=value,
                direct_answer=somni_quiz_pb2.DirectAnswer(
                    question_id=answer.get("question_id", ""),
                    selected_options=list(answer.get("selected_options", [])),
                    input_value=answer.get("input_value", ""),
                ),
            )
        )
    return somni_quiz_pb2.AnswerRecord(answer_id="", answers=answers)


def build_final_result_message(final_result: dict | None) -> Struct:
    """Map an optional final result dictionary into google.protobuf.Struct."""
    message = Struct()
    if final_result:
        message.update(final_result)
    return message
