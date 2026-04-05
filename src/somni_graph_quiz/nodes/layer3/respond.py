"""Response composer node."""

from __future__ import annotations

from pathlib import Path

from somni_graph_quiz.llm.invocation import invoke_json
from somni_graph_quiz.llm.prompt_loader import PromptLoader


_PROMPTS_ROOT = Path(__file__).resolve().parents[4] / "prompts"


class ResponseComposerNode:
    """Convert finalized facts into a user-facing message."""

    def __init__(self, prompt_loader: PromptLoader | None = None) -> None:
        self._prompt_loader = prompt_loader or PromptLoader(_PROMPTS_ROOT)

    def run(self, finalized: object) -> str:
        llm_message = self._try_llm(finalized)
        if llm_message is not None:
            return llm_message
        raw_input = str(getattr(finalized, "raw_input", "") or "")
        language = getattr(finalized, "response_language", "zh-CN")
        outcome = getattr(finalized, "turn_outcome", "clarification")
        current_question = getattr(finalized, "current_question", None)
        next_question = getattr(finalized, "next_question", None)
        non_content_intent = getattr(finalized, "non_content_intent", "none")
        response_facts = getattr(finalized, "response_facts", {})
        if str(language).lower().startswith("en"):
            return self._compose_en(
                outcome,
                current_question,
                next_question,
                response_facts,
                raw_input=raw_input,
                non_content_intent=non_content_intent,
            )
        return self._compose_zh(
            outcome,
            current_question,
            next_question,
            response_facts,
            raw_input=raw_input,
            non_content_intent=non_content_intent,
        )

    def _try_llm(self, finalized: object) -> str | None:
        response_facts = getattr(finalized, "response_facts", {})
        provider = response_facts.get("llm_provider")
        if not response_facts.get("llm_available", False) or provider is None:
            return None
        prompt_response_facts = {
            key: value
            for key, value in response_facts.items()
            if key not in {"llm_provider", "llm_available"}
        }
        payload = {
            "raw_input": getattr(finalized, "raw_input", ""),
            "input_mode": getattr(finalized, "input_mode", "message"),
            "main_branch": getattr(finalized, "main_branch", "content"),
            "non_content_intent": getattr(finalized, "non_content_intent", "none"),
            "response_language": getattr(finalized, "response_language", "zh-CN"),
            "turn_outcome": getattr(finalized, "turn_outcome", "clarification"),
            "response_facts": prompt_response_facts,
            "current_question": getattr(finalized, "current_question", None),
            "next_question": getattr(finalized, "next_question", None),
            "finalized": getattr(finalized, "finalized", False),
        }
        try:
            prompt_text = self._prompt_loader.render("layer3/response_composer.md", payload)
            output = invoke_json(
                provider,
                prompt_key="layer3/response_composer.md",
                prompt_text=prompt_text,
            )
        except Exception:
            return None
        message = output.get("assistant_message")
        if not isinstance(message, str) or not message.strip():
            return None
        return message.strip()

    def _compose_en(
        self,
        outcome: str,
        current_question: dict | None,
        next_question: dict | None,
        response_facts: dict,
        *,
        raw_input: str,
        non_content_intent: str,
    ) -> str:
        del current_question
        next_title = self._next_title(next_question, fallback="the next question")
        if outcome == "answered":
            return f"Recorded. Let's continue with the next question: {next_title}."
        if outcome == "completed":
            return "All questions are complete. Thank you for sharing."
        if outcome == "pullback":
            if response_facts.get("pullback_reason") == "identity_question":
                return f"I'm Somni, here to stay with you through this sleep questionnaire. Let's come back to {next_title}."
            if self._looks_like_thanks(raw_input):
                return f"You're welcome. Let's come back to {next_title}."
            if self._looks_like_greeting(raw_input):
                return f"Hello. Let's keep going with {next_title}."
            return f"I hear you. Let's come back to your sleep and continue with {next_title}."
        if outcome == "partial_recorded":
            return "I noted part of your schedule. What time do you wake up?"
        if outcome == "view_only":
            action = response_facts.get("non_content_action")
            records_summary = self._render_view_records(response_facts.get("view_records", []))
            if action == "view_previous" and records_summary:
                return f"Your previous answer was: {records_summary}. Let's continue with {next_title}."
            if records_summary:
                return f"Here is the current record summary: {records_summary}."
            return "Here is the current record summary."
        if outcome == "undo_applied":
            return f"Your previous answer has been restored. Let's continue with {next_title}."
        if outcome == "navigate":
            action = response_facts.get("non_content_action") or non_content_intent
            if action == "navigate_next":
                return f"Okay, I've moved to the next question: {next_title}."
            if action == "navigate_previous":
                return f"Okay, we're back to the previous question: {next_title}."
            if action == "modify_previous":
                return f"Okay, let's go back and adjust the previous answer: {next_title}."
            return f"Okay. Let's continue with {next_title}."
        if outcome == "skipped":
            return f"Skipped. Let's continue with the next question: {next_title}."
        return f"Let's keep going with {next_title}."

    def _compose_zh(
        self,
        outcome: str,
        current_question: dict | None,
        next_question: dict | None,
        response_facts: dict,
        *,
        raw_input: str,
        non_content_intent: str,
    ) -> str:
        active_question = current_question or next_question
        active_title = self._next_title(active_question, fallback="当前这题")
        next_title = self._next_title(next_question, fallback=active_title)
        if outcome == "answered":
            return f"已记录，我们继续回答下一题：{next_title}。"
        if outcome == "completed":
            return "问卷已完成，感谢你的回答。"
        if outcome == "pullback":
            if response_facts.get("pullback_reason") == "identity_question":
                return f"我是 Somni，会一直陪你把这份睡眠问卷答完。我们先回到这题：{active_title}。"
            if self._looks_like_thanks(raw_input):
                return f"不客气，我们继续回答{active_title}。"
            if self._looks_like_greeting(raw_input):
                return f"你好，我们继续回答{active_title}。"
            if non_content_intent == "pullback_chat":
                return f"我们先回到问卷，继续回答{active_title}。"
            return f"收到，我们先回到你的睡眠情况，继续回答{active_title}。"
        if outcome == "partial_recorded":
            return "已先记下部分作息，请再告诉我你通常几点起床。"
        if outcome == "view_only":
            action = response_facts.get("non_content_action")
            records_summary = self._render_view_records(response_facts.get("view_records", []))
            if action == "view_previous" and records_summary:
                return f"上一题我记下的是：{records_summary}。我们现在继续回答{active_title}。"
            if records_summary:
                return f"这是你当前的记录摘要：{records_summary}。"
            return "这是你当前的记录摘要。"
        if outcome == "undo_applied":
            return f"已恢复到上一次答案，我们继续回答{active_title}。"
        if outcome == "navigate":
            action = response_facts.get("non_content_action") or non_content_intent
            if action == "navigate_next":
                return f"好的，已经切到下一题：{next_title}。"
            if action == "navigate_previous":
                return f"好的，已经回到上一题：{next_title}。"
            if action == "modify_previous":
                return f"好的，我们先回到上一题调整一下：{next_title}。"
            return f"好的，我们继续回答{next_title}。"
        if outcome == "skipped":
            return f"这题先跳过，我们继续回答下一题：{next_title}。"
        return f"我们继续这题：{active_title}。"

    def _next_title(self, next_question: dict | None, *, fallback: str) -> str:
        if not next_question:
            return fallback
        return next_question.get("title") or fallback

    def _render_view_records(self, view_records: object) -> str:
        if not isinstance(view_records, list):
            return ""
        tokens: list[str] = []
        for record in view_records:
            if not isinstance(record, dict):
                continue
            selected = record.get("selected_options")
            if isinstance(selected, list) and selected:
                tokens.append("/".join(str(option) for option in selected))
                continue
            input_value = record.get("input_value")
            if isinstance(input_value, str) and input_value.strip():
                tokens.append(input_value.strip())
        return "；".join(tokens[:3])

    def _looks_like_greeting(self, raw_input: str) -> bool:
        lowered = raw_input.strip().lower()
        return any(token in lowered for token in ("你好", "您好", "hi", "hello", "hey"))

    def _looks_like_thanks(self, raw_input: str) -> bool:
        lowered = raw_input.strip().lower()
        return any(token in lowered for token in ("谢谢", "感谢", "thanks", "thank you"))
