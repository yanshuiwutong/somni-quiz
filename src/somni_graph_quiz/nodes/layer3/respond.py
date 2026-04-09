"""Response composer node."""

from __future__ import annotations

from pathlib import Path
import re

from somni_graph_quiz.llm.invocation import invoke_json
from somni_graph_quiz.llm.prompt_loader import PromptLoader


_PROMPTS_ROOT = Path(__file__).resolve().parents[4] / "prompts"


class ResponseComposerNode:
    """Convert finalized facts into a user-facing message."""

    def __init__(self, prompt_loader: PromptLoader | None = None) -> None:
        self._prompt_loader = prompt_loader or PromptLoader(_PROMPTS_ROOT)

    def run(self, finalized: object) -> str:
        raw_input = str(getattr(finalized, "raw_input", "") or "")
        language = getattr(finalized, "response_language", "zh-CN")
        outcome = getattr(finalized, "turn_outcome", "clarification")
        current_question = getattr(finalized, "current_question", None)
        next_question = getattr(finalized, "next_question", None)
        non_content_intent = getattr(finalized, "non_content_intent", "none")
        response_facts = getattr(finalized, "response_facts", {})
        llm_message = self._try_llm(finalized, outcome=outcome)
        if llm_message is not None:
            return llm_message
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

    def _try_llm(self, finalized: object, *, outcome: str) -> str | None:
        response_facts = getattr(finalized, "response_facts", {})
        provider = response_facts.get("llm_provider")
        if not response_facts.get("llm_available", False) or provider is None:
            return None
        prompt_response_facts = self._prompt_response_facts(response_facts)
        payload = self._build_llm_payload(finalized, outcome=outcome, response_facts=prompt_response_facts)
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
        stripped_message = message.strip()
        if not self._is_llm_message_grounded(
            stripped_message,
            outcome=outcome,
            response_facts=prompt_response_facts,
            current_question=getattr(finalized, "current_question", None),
            next_question=getattr(finalized, "next_question", None),
        ):
            return None
        return stripped_message

    def _build_llm_payload(self, finalized: object, *, outcome: str, response_facts: dict) -> dict:
        updated_answer_record = getattr(finalized, "updated_answer_record", {"answers": []})
        if outcome != "completed":
            updated_answer_record = {"answers": []}
        current_question = getattr(finalized, "current_question", None)
        next_question = getattr(finalized, "next_question", None)
        payload = {
            "raw_input": getattr(finalized, "raw_input", ""),
            "input_mode": getattr(finalized, "input_mode", "message"),
            "main_branch": getattr(finalized, "main_branch", "content"),
            "non_content_intent": getattr(finalized, "non_content_intent", "none"),
            "response_language": getattr(finalized, "response_language", "zh-CN"),
            "turn_outcome": getattr(finalized, "turn_outcome", "clarification"),
            "updated_answer_record": updated_answer_record,
            "response_facts": response_facts,
            "turn_focus": {
                "response_focus": outcome,
                "turn_recorded_question_summaries": response_facts.get("recorded_question_summaries", []),
                "turn_modified_question_summaries": response_facts.get("modified_question_summaries", []),
                "turn_partial_question_summaries": response_facts.get("partial_question_summaries", []),
                "active_question": current_question,
                "next_question": next_question,
            },
            "current_question": current_question,
            "next_question": next_question,
            "finalized": getattr(finalized, "finalized", False),
        }
        partial_followup = response_facts.get("partial_followup")
        if partial_followup is not None:
            payload["partial_followup"] = partial_followup
        return payload

    def _prompt_response_facts(self, response_facts: dict) -> dict:
        prompt_response_facts = {
            key: value
            for key, value in response_facts.items()
            if key not in {"llm_provider", "llm_available"}
        }
        prompt_response_facts.setdefault(
            "turn_recorded_question_summaries",
            prompt_response_facts.get("recorded_question_summaries", []),
        )
        prompt_response_facts.setdefault(
            "turn_modified_question_summaries",
            prompt_response_facts.get("modified_question_summaries", []),
        )
        prompt_response_facts.setdefault(
            "turn_partial_question_summaries",
            prompt_response_facts.get("partial_question_summaries", []),
        )
        return prompt_response_facts

    def _is_llm_message_grounded(
        self,
        message: str,
        *,
        outcome: str,
        response_facts: dict,
        current_question: dict | None,
        next_question: dict | None,
    ) -> bool:
        if response_facts.get("non_content_mode") == "weather":
            return self._is_weather_message_grounded(
                message,
                response_facts=response_facts,
                current_question=current_question,
                next_question=next_question,
            )
        if outcome == "answered":
            titles = self._grounding_titles(
                primary=self._summary_title(response_facts.get("recorded_question_summaries")),
                next_question=next_question,
            )
            return self._message_mentions_titles(message, titles)
        if outcome == "modified":
            titles = self._grounding_titles(
                primary=self._summary_title(response_facts.get("modified_question_summaries")),
                next_question=next_question,
            )
            return self._message_mentions_titles(message, titles)
        del response_facts
        del current_question
        return True

    def _is_weather_message_grounded(
        self,
        message: str,
        *,
        response_facts: dict,
        current_question: dict | None,
        next_question: dict | None,
    ) -> bool:
        normalized_message = self._normalize_text(message)
        status = str(response_facts.get("weather_status", "")).strip()
        city = str(response_facts.get("weather_city", "")).strip()
        if status == "missing_city":
            if not any(token in normalized_message for token in ("城市", "city")):
                return False
            active_titles = self._grounding_titles(primary="", next_question=current_question or next_question)
            if active_titles and self._message_mentions_titles(message, active_titles):
                return False
            return True
        if status == "success":
            if city and self._normalize_text(city) not in normalized_message:
                return False
            active_titles = self._grounding_titles(primary="", next_question=current_question or next_question)
            return self._message_mentions_titles(message, active_titles) if active_titles else True
        if status == "error":
            if city and self._normalize_text(city) not in normalized_message:
                return False
            active_titles = self._grounding_titles(primary="", next_question=current_question or next_question)
            return self._message_mentions_titles(message, active_titles) if active_titles else True
        return True

    def _grounding_titles(self, *, primary: str, next_question: dict | None) -> list[str]:
        titles: list[str] = []
        if primary:
            titles.append(primary)
        next_title = self._next_title(next_question, fallback="")
        if next_title and next_title != primary:
            titles.append(next_title)
        return titles

    def _message_mentions_titles(self, message: str, titles: list[str]) -> bool:
        normalized_message = self._normalize_text(message)
        checks_performed = 0
        for title in titles:
            terms = self._title_terms(title)
            if not terms:
                continue
            checks_performed += 1
            if not any(term in normalized_message for term in terms):
                return False
        return checks_performed > 0

    def _title_terms(self, title: str) -> list[str]:
        normalized_title = self._normalize_text(title)
        if not normalized_title:
            return []
        preferred_terms = [
            "入睡时间",
            "起床时间",
            "年龄段",
            "作息",
            "敏感度",
            "光线",
            "声音",
            "压力",
            "睡眠",
            "question",
            "next",
        ]
        matched = [term for term in preferred_terms if term in normalized_title]
        if matched:
            return matched
        if re.search(r"[\u4e00-\u9fff]", title):
            compact = normalized_title
            for token in (
                "完全自由安排时",
                "您平时通常的",
                "您的",
                "您对",
                "您",
                "最自然的",
                "通常",
                "如何",
                "几点",
                "什么",
                "多少",
                "是否",
                "会受影响吗",
                "会受影响",
                "是",
            ):
                compact = compact.replace(token, "")
            return [compact] if len(compact) >= 2 else []
        return [
            token
            for token in re.findall(r"[a-z0-9]+", normalized_title)
            if token not in {"the", "what", "when", "your", "you", "are", "question", "next"}
        ]

    def _normalize_text(self, text: str) -> str:
        lowered = text.strip().lower()
        return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", lowered)

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
            recorded_title = self._summary_title(response_facts.get("recorded_question_summaries"))
            if recorded_title and recorded_title != next_title:
                return f"Recorded your answer for {recorded_title}. Let's continue with {next_title}."
            return f"Recorded. Let's continue with the next question: {next_title}."
        if outcome == "modified":
            modified_title = self._summary_title(response_facts.get("modified_question_summaries"))
            if modified_title and modified_title != next_title:
                return f"Updated your answer for {modified_title}. Let's continue with {next_title}."
            return f"Updated. Let's continue with {next_title}."
        if outcome == "completed":
            return (
                "Thank you for sharing. I now have a clearer picture of your sleep habits, "
                "and next I will organize a more personalized sound, light, and scent sleep plan for you."
            )
        if outcome == "pullback":
            if response_facts.get("non_content_mode") == "weather":
                return self._compose_weather_pullback_en(response_facts, active_title=next_title)
            if response_facts.get("pullback_reason") == "identity_question":
                return f"I'm Somni, here to stay with you through this sleep questionnaire. Let's come back to {next_title}."
            if self._looks_like_thanks(raw_input):
                return f"You're welcome. Let's come back to {next_title}."
            if self._looks_like_greeting(raw_input):
                return f"Hello. Let's keep going with {next_title}."
            return f"I hear you. Let's come back to your sleep and continue with {next_title}."
        if outcome == "partial_recorded":
            return self._compose_partial_recorded_message(response_facts, language="en")
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
            recorded_title = self._summary_title(response_facts.get("recorded_question_summaries"))
            if recorded_title and recorded_title != next_title:
                return f"已记下你关于{recorded_title}的回答。接下来请回答{next_title}。"
            return f"已记录，我们继续回答下一题：{next_title}。"
        if outcome == "modified":
            modified_title = self._summary_title(response_facts.get("modified_question_summaries"))
            if modified_title and modified_title != next_title:
                return f"已更新你关于{modified_title}的回答。接下来请回答{next_title}。"
            return f"已更新，我们继续回答{next_title}。"
        if outcome == "completed":
            return (
                "感谢你的分享。我已经大致了解了你的睡眠习惯，"
                "接下来会结合你记录下来的作息与感受，为你整理更适合你的专属声、光、香睡眠方案。"
            )
        if outcome == "pullback":
            if response_facts.get("non_content_mode") == "weather":
                return self._compose_weather_pullback_zh(response_facts, active_title=active_title)
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
            return self._compose_partial_recorded_message(response_facts, language="zh")
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

    def _compose_partial_recorded_message(self, response_facts: dict, *, language: str) -> str:
        fallback_messages = {
            "zh": "已先记下部分作息，请再告诉我你通常几点起床。",
            "en": "I noted part of your schedule. What time do you wake up?",
        }
        special_messages = {
            "zh": {
                "bedtime": "已先记下你的起床时间，请告诉我你通常几点睡吧。",
                "wake_time": "已先记下你的入睡时间，请再告诉我你通常几点起床。",
            },
            "en": {
                "bedtime": "I've noted your wake-up time; please tell me when you usually go to sleep.",
                "wake_time": "I've noted your bedtime; please tell me when you usually wake up.",
            },
        }
        fallback = fallback_messages.get(language, fallback_messages["en"])
        language_messages = special_messages.get(language, special_messages["en"])
        partial_followup = response_facts.get("partial_followup")
        if not isinstance(partial_followup, dict):
            return fallback
        missing_fields = partial_followup.get("missing_fields")
        if not isinstance(missing_fields, list):
            return fallback
        normalized_fields = [field for field in missing_fields if isinstance(field, str)]
        if len(normalized_fields) != 1:
            return fallback
        return language_messages.get(normalized_fields[0], fallback)

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

    def _summary_title(self, summaries: object) -> str:
        if not isinstance(summaries, list) or not summaries:
            return ""
        first = summaries[0]
        if not isinstance(first, dict):
            return ""
        return str(first.get("title", "")).strip()

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

    def _compose_weather_pullback_zh(self, response_facts: dict, *, active_title: str) -> str:
        status = str(response_facts.get("weather_status", "")).strip()
        if status == "missing_city":
            return "你想查询哪个城市的天气？"
        city = str(response_facts.get("weather_city", "")).strip()
        summary = str(response_facts.get("weather_summary", "")).strip()
        if status == "success" and city and summary:
            return f"{city}今天天气：{summary}。我们继续回答{active_title}。"
        if city:
            return f"暂时没查到{city}的天气。我们继续回答{active_title}。"
        return f"暂时没查到天气信息。我们继续回答{active_title}。"

    def _compose_weather_pullback_en(self, response_facts: dict, *, active_title: str) -> str:
        status = str(response_facts.get("weather_status", "")).strip()
        if status == "missing_city":
            return "Which city's weather would you like to check?"
        city = str(response_facts.get("weather_city", "")).strip()
        summary = str(response_facts.get("weather_summary", "")).strip()
        if status == "success" and city and summary:
            return f"{city} weather today: {summary}. Let's continue with {active_title}."
        if city:
            return f"I couldn't get the weather for {city} right now. Let's continue with {active_title}."
        return f"I couldn't get the weather right now. Let's continue with {active_title}."
