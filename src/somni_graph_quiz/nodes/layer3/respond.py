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
            "updated_answer_record": getattr(finalized, "updated_answer_record", {"answers": []}),
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
            return (
                "Thank you for sharing. I now have a clearer picture of your sleep habits, "
                "and next I will organize a more personalized sound, light, and scent sleep plan for you."
            )
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
        if outcome == "clarification":
            return self._compose_en_clarification(response_facts, active_title=next_title)
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
            return (
                "感谢你的分享。我已经大致了解了你的睡眠习惯，"
                "接下来会结合你记录下来的作息与感受，为你整理更适合你的专属声、光、香睡眠方案。"
            )
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
        if outcome == "clarification":
            return self._compose_zh_clarification(response_facts, fallback_title=active_title)
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

    def _compose_zh_clarification(self, response_facts: dict, *, fallback_title: str) -> str:
        title = str(response_facts.get("clarification_question_title") or fallback_title)
        kind = str(response_facts.get("clarification_kind") or response_facts.get("clarification_reason") or "")
        if "年龄" in title:
            return "不好意思，我这边还没法确定你的年龄段，可以再告诉我一下你的年龄段吗？"
        if any(token in title for token in ("光线", "声音", "敏感")):
            return "我想确认一下，你对卧室里的光线和声音敏感度更接近哪种情况？"
        if any(token in kind for token in ("partial", "missing_fields")):
            return f"我先记下了一部分信息，请再补充一下：{title}"
        if "question_identified_option_not_identified" in kind:
            return f"我想再确认一下，你在“{title}”这题里更接近哪一种情况？"
        return f"不好意思，我想再确认一下：{title}"

    def _compose_en_clarification(self, response_facts: dict, *, active_title: str) -> str:
        title = str(response_facts.get("clarification_question_title") or active_title)
        kind = str(response_facts.get("clarification_kind") or response_facts.get("clarification_reason") or "")
        if "age" in title.lower():
            return "I couldn't determine your age range yet. Could you tell me your age range again?"
        if any(token in title.lower() for token in ("light", "sound", "sensitive")):
            return "I want to confirm your bedroom light and sound sensitivity. Which situation is closer for you?"
        if any(token in kind for token in ("partial", "missing_fields")):
            return f"I've noted part of it. Could you fill in the missing part for {title}?"
        if "question_identified_option_not_identified" in kind:
            return f"I want to confirm which option is closer for {title}."
        return f"I want to confirm one detail about {title}."
