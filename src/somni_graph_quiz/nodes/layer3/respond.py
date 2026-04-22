"""Response composer node."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re

from somni_graph_quiz.llm.invocation import invoke_json
from somni_graph_quiz.llm.prompt_loader import PromptLoader


_PROMPTS_ROOT = Path(__file__).resolve().parents[4] / "prompts"
_DIAGNOSTIC_LOGGER = logging.getLogger("somni_graph_quiz.diagnostics.companion_response")


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
        companion_message = self._try_companion_overlay(finalized)
        if companion_message is not None:
            return companion_message
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
        if outcome == "partial_recorded":
            return self._is_partial_recorded_message_grounded(message, response_facts=response_facts)
        del response_facts
        del current_question
        return True

    def _is_partial_recorded_message_grounded(self, message: str, *, response_facts: dict) -> bool:
        partial_followup = response_facts.get("partial_followup")
        if not isinstance(partial_followup, dict):
            return True
        missing_fields = partial_followup.get("missing_fields")
        if not isinstance(missing_fields, list):
            return True
        normalized_fields = [field for field in missing_fields if isinstance(field, str)]
        if len(normalized_fields) != 1:
            return True
        required_terms = {
            "wake_time": (
                "起床",
                "几点起",
                "wake up",
                "wake-up",
                "wakeup",
                "get up",
            ),
            "bedtime": (
                "入睡",
                "几点睡",
                "睡觉",
                "上床",
                "bedtime",
                "go to sleep",
                "fall asleep",
            ),
        }
        terms = required_terms.get(normalized_fields[0])
        if not terms:
            return True
        normalized_message = self._normalize_text(message)
        return any(self._normalize_text(term) in normalized_message for term in terms)

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

    def _try_companion_overlay(self, finalized: object) -> str | None:
        response_facts = getattr(finalized, "response_facts", {})
        language = str(getattr(finalized, "response_language", "zh-CN"))
        next_question = getattr(finalized, "next_question", None)
        if response_facts.get("companion_completion_wrapup"):
            return self._compose_companion_completion_message(language=language)
        if response_facts.get("companion_soft_return_to_quiz"):
            llm_message, llm_failure_reason = self._try_companion_llm(finalized)
            if llm_message is not None:
                return llm_message
            if llm_failure_reason not in {None, "llm_unavailable"}:
                return self._compose_companion_llm_failure_message(
                    overlay_mode="soft_return_to_quiz",
                    language=language,
                )
            return self._compose_companion_soft_return_message(
                finalized=finalized,
                language=language,
                next_question=next_question,
            )
        if response_facts.get("return_to_quiz"):
            llm_message, llm_failure_reason = self._try_companion_llm(finalized)
            if llm_message is not None:
                return llm_message
            if llm_failure_reason not in {None, "llm_unavailable"}:
                return self._compose_companion_llm_failure_message(
                    overlay_mode="return_to_quiz",
                    language=language,
                )
            return self._compose_companion_return_message(
                language=language,
                next_question=next_question,
            )
        if response_facts.get("stay_in_companion"):
            llm_message, llm_failure_reason = self._try_companion_llm(finalized)
            if llm_message is not None:
                return llm_message
            if llm_failure_reason not in {None, "llm_unavailable"}:
                return self._compose_companion_llm_failure_message(
                    overlay_mode="stay_in_companion",
                    language=language,
                )
            return self._compose_companion_stay_message(
                finalized=finalized,
                language=language,
                response_facts=response_facts,
            )
        return None

    def _try_companion_llm(self, finalized: object) -> tuple[str | None, str | None]:
        message, failure_reason = self._attempt_companion_llm(finalized, attempt=1)
        if message is not None:
            return message, None
        if failure_reason in {None, "llm_unavailable"}:
            return None, failure_reason
        retry_message, _ = self._attempt_companion_llm(
            finalized,
            attempt=2,
            retry_reason=failure_reason,
        )
        if retry_message is not None:
            return retry_message, None
        return None, failure_reason

    def _attempt_companion_llm(
        self,
        finalized: object,
        *,
        attempt: int,
        retry_reason: str | None = None,
    ) -> tuple[str | None, str | None]:
        response_facts = getattr(finalized, "response_facts", {})
        raw_input = str(getattr(finalized, "raw_input", "") or "")
        provider = response_facts.get("llm_provider")
        if not response_facts.get("llm_available", False) or provider is None:
            self._log_companion_diagnostic(
                "llm_not_attempted",
                raw_input=raw_input,
                reason="llm_unavailable",
                llm_provider_available=bool(response_facts.get("llm_available", False) and provider is not None),
                overlay_mode=self._companion_overlay_mode(response_facts),
                attempt=attempt,
            )
            return None, "llm_unavailable"
        payload = self._build_companion_payload(
            finalized,
            retry_reason=retry_reason,
            retry_attempt=attempt,
        )
        self._log_companion_diagnostic(
            "llm_attempt_started",
            raw_input=raw_input,
            llm_provider_available=True,
            overlay_mode=self._companion_overlay_mode(response_facts),
            attempt=attempt,
            retry_reason=retry_reason,
        )
        try:
            prompt_text = self._prompt_loader.render("layer3/companion_response.md", payload)
            output = invoke_json(
                provider,
                prompt_key="layer3/companion_response.md",
                prompt_text=prompt_text,
            )
        except Exception as exc:
            self._log_companion_diagnostic(
                "llm_exception",
                raw_input=raw_input,
                llm_provider_available=True,
                overlay_mode=self._companion_overlay_mode(response_facts),
                error_type=type(exc).__name__,
                error_message=str(exc),
                attempt=attempt,
            )
            return None, "llm_exception"
        message = output.get("assistant_message")
        self._log_companion_diagnostic(
            "llm_result_received",
            raw_input=raw_input,
            llm_provider_available=True,
            overlay_mode=self._companion_overlay_mode(response_facts),
            has_message=isinstance(message, str) and bool(message.strip()),
            attempt=attempt,
        )
        if not isinstance(message, str) or not message.strip():
            self._log_companion_diagnostic(
                "llm_empty_message",
                raw_input=raw_input,
                llm_provider_available=True,
                overlay_mode=self._companion_overlay_mode(response_facts),
                attempt=attempt,
            )
            return None, "llm_empty_message"
        stripped_message = message.strip()
        if self._companion_message_mentions_recording(stripped_message):
            self._log_companion_diagnostic(
                "llm_rejected_recording_ack",
                raw_input=raw_input,
                llm_provider_available=True,
                overlay_mode=self._companion_overlay_mode(response_facts),
                attempt=attempt,
            )
            return None, "llm_rejected_recording_ack"
        if not self._is_companion_message_acceptable(stripped_message, finalized=finalized):
            self._log_companion_diagnostic(
                "llm_rejected_pullback_copy",
                raw_input=raw_input,
                llm_provider_available=True,
                overlay_mode=self._companion_overlay_mode(response_facts),
                attempt=attempt,
            )
            return None, "llm_rejected_pullback_copy"
        self._log_companion_diagnostic(
            "llm_result_consumed",
            raw_input=raw_input,
            llm_provider_available=True,
            overlay_mode=self._companion_overlay_mode(response_facts),
            attempt=attempt,
        )
        return stripped_message, None

    def _build_companion_payload(
        self,
        finalized: object,
        *,
        retry_reason: str | None = None,
        retry_attempt: int = 1,
    ) -> dict:
        response_facts = getattr(finalized, "response_facts", {})
        silent_recorded_question_ids = response_facts.get("silent_recorded_question_ids", [])
        silent_modified_question_ids = response_facts.get("silent_modified_question_ids", [])
        return {
            "raw_input": getattr(finalized, "raw_input", ""),
            "response_language": getattr(finalized, "response_language", "zh-CN"),
            "turn_outcome": getattr(finalized, "turn_outcome", "clarification"),
            "companion_mode": response_facts.get("companion_mode"),
            "companion_distress_level": response_facts.get("companion_distress_level", "none"),
            "stay_in_companion": bool(response_facts.get("stay_in_companion")),
            "soft_return_to_quiz": bool(response_facts.get("companion_soft_return_to_quiz")),
            "return_to_quiz": bool(response_facts.get("return_to_quiz")),
            "current_question": getattr(finalized, "current_question", None),
            "next_question": getattr(finalized, "next_question", None),
            "recorded_question_summaries": response_facts.get("recorded_question_summaries", []),
            "modified_question_summaries": response_facts.get("modified_question_summaries", []),
            "silent_recorded_question_ids": silent_recorded_question_ids,
            "silent_modified_question_ids": silent_modified_question_ids,
            "silent_answer_event": bool(silent_recorded_question_ids or silent_modified_question_ids),
            "must_not_acknowledge_recording": True,
            "companion_recent_turns": response_facts.get("companion_recent_turns", []),
            "continue_chat_intent": response_facts.get("continue_chat_intent", "none"),
            "companion_can_soft_return": bool(response_facts.get("companion_soft_return_to_quiz")),
            "llm_retry_reason": retry_reason,
            "llm_retry_attempt": retry_attempt,
        }

    def _companion_message_mentions_recording(self, message: str) -> bool:
        normalized_message = self._normalize_text(message)
        forbidden_terms = (
            "已记录",
            "已记下",
            "记下",
            "记录了",
            "已更新",
            "recorded",
            "noted",
            "updated",
        )
        return any(self._normalize_text(term) in normalized_message for term in forbidden_terms)

    def _compose_companion_stay_message(self, *, finalized: object, language: str, response_facts: dict) -> str:
        raw_input = str(getattr(finalized, "raw_input", "") or "")
        topic_message = self._compose_companion_topic_reply(
            raw_input=raw_input,
            language=language,
            continue_chat_intent=str(response_facts.get("continue_chat_intent", "none")),
            recent_turns=response_facts.get("companion_recent_turns", []),
            next_question=getattr(finalized, "next_question", None),
            allow_silent_record_context=bool(
                response_facts.get("silent_recorded_question_ids") or response_facts.get("silent_modified_question_ids")
            ),
        )
        if topic_message is not None:
            return topic_message
        if response_facts.get("companion_mode") == "smalltalk":
            if language.lower().startswith("en"):
                if self._looks_like_thanks(raw_input):
                    return "You're welcome. I'm here with you if you want to keep talking."
                if self._looks_like_greeting(raw_input):
                    return "Hi. I'm here, and you can keep chatting with me."
                return "I'm here with you. If you want to keep talking, go ahead."
            if self._looks_like_thanks(raw_input):
                return "不客气呀，我在这儿陪你。你要是还想聊，就继续说。"
            if self._looks_like_greeting(raw_input):
                return "你好呀，我在呢。你想聊什么都可以。"
            return "我在呢，你想接着聊什么都可以。"
        if response_facts.get("companion_distress_level") == "high_risk":
            if language.lower().startswith("en"):
                return (
                    "I'm here with you. Please don't carry this alone right now. "
                    "Reach out to someone you trust and ask them to stay with you."
                )
            return "我在这儿。你先别一个人扛着，尽快联系一个你信任的人陪着你，好吗？"
        if language.lower().startswith("en"):
            return "I'm here with you. Take your time and tell me whatever feels worth saying next."
        return "我在这儿，你可以慢慢说。不管是想吐槽两句，还是想换个话题聊聊，都可以。"

    def _compose_companion_llm_failure_message(self, *, overlay_mode: str, language: str) -> str:
        if language.lower().startswith("en"):
            if overlay_mode == "soft_return_to_quiz":
                return "We can keep this gentle for a moment, and when you're ready we can slowly keep going."
            if overlay_mode == "return_to_quiz":
                return "Let's hold this gently for a second. I'll stay with you and we can keep moving when you're ready."
            return "I'm here with you. We can keep following this thread for a bit."
        if overlay_mode == "soft_return_to_quiz":
            return "这段我们先轻轻放着，我陪你顺着刚才的话题再说一点，等你准备好了我们再慢慢往下看。"
        if overlay_mode == "return_to_quiz":
            return "我们先把这段话题放稳一点，我陪你缓一下，等你准备好了再继续往后走。"
        return "我在这儿，我们可以接着刚才的话题慢慢说。"

    def _compose_companion_topic_reply(
        self,
        *,
        raw_input: str,
        language: str,
        continue_chat_intent: str,
        recent_turns: object,
        next_question: dict | None,
        allow_silent_record_context: bool = False,
    ) -> str | None:
        lowered = raw_input.strip().lower()
        if language.lower().startswith("en"):
            return None
        recent_topic = self._detect_recent_companion_topic(recent_turns)
        recent_followup_kind = self._detect_recent_assistant_followup_kind(recent_turns)
        recent_pullback_anchor = self._detect_recent_pullback_anchor(recent_turns)
        should_deescalate_follow_up = (
            continue_chat_intent != "strong"
            and recent_followup_kind == "open_followup"
        )
        if continue_chat_intent != "strong":
            pullback_anchor_message = self._compose_recent_pullback_anchor_message(
                raw_input=lowered,
                recent_pullback_anchor=recent_pullback_anchor,
            )
            if pullback_anchor_message is not None:
                return pullback_anchor_message
            topic = self._detect_companion_topic(lowered)
            if allow_silent_record_context and topic is not None:
                return self._compose_companion_topic_message(
                    topic=topic,
                    raw_input=lowered,
                    is_follow_up=False,
                    deescalate=False,
                )
            if recent_topic is not None and (
                self._looks_like_contextual_fragment(lowered, recent_topic=recent_topic)
                or self._looks_like_contextual_choice_reply(lowered)
                or (should_deescalate_follow_up and topic == recent_topic)
            ):
                return self._compose_companion_topic_message(
                    topic=recent_topic,
                    raw_input=lowered,
                    is_follow_up=True,
                    deescalate=should_deescalate_follow_up,
                )
            if not self._looks_like_contextual_assent(lowered):
                return None
            if should_deescalate_follow_up and next_question is not None:
                return self._compose_companion_weak_pullback_message(
                    recent_topic=recent_topic,
                    next_question=next_question,
                )
            if recent_topic is None:
                if next_question is None:
                    return None
                return self._compose_companion_weak_pullback_message(
                    recent_topic=None,
                    next_question=next_question,
                )
            return self._compose_companion_topic_message(
                topic=recent_topic,
                raw_input=lowered,
                is_follow_up=True,
                deescalate=should_deescalate_follow_up,
            )
        topic = self._detect_companion_topic(lowered)
        if topic is not None:
            return self._compose_companion_topic_message(
                topic=topic,
                raw_input=lowered,
                is_follow_up=False,
                deescalate=False,
            )
        if not self._looks_like_companion_follow_up(lowered):
            return None
        if recent_topic is None:
            return None
        return self._compose_companion_topic_message(
            topic=recent_topic,
            raw_input=lowered,
            is_follow_up=True,
            deescalate=False,
        )

    def _detect_companion_topic(self, text: str) -> str | None:
        if any(token in text for token in ("西红柿炒鸡蛋", "中午吃什么", "午饭", "午餐", "吃什么")):
            return "meal"
        if "褪黑素" in text:
            return "melatonin"
        if "奶茶" in text:
            return "milk_tea"
        if any(
            token in text
            for token in (
                "睡不着",
                "睡不太着",
                "失眠",
                "很晚才能睡着",
                "很晚才睡着",
                "压力",
                "脑子停不下来",
                "入睡比较困难",
                "入睡困难",
                "睡眠不太好",
            )
        ):
            return "sleep_stress"
        if any(token in text for token in ("旅游", "旅行", "景点", "去哪玩", "海边", "散散心", "放松")):
            return "travel"
        return None

    def _detect_recent_companion_topic(self, recent_turns: object) -> str | None:
        if not isinstance(recent_turns, list):
            return None
        for turn in reversed(recent_turns[-3:]):
            if not isinstance(turn, dict):
                continue
            assistant_topic = turn.get("assistant_topic")
            if isinstance(assistant_topic, str) and assistant_topic:
                return assistant_topic
            raw_input = str(turn.get("raw_input", "")).strip().lower()
            if not raw_input:
                continue
            topic = self._detect_companion_topic(raw_input)
            if topic is not None:
                return topic
        return None

    def _detect_recent_assistant_followup_kind(self, recent_turns: object) -> str | None:
        if not isinstance(recent_turns, list):
            return None
        for turn in reversed(recent_turns[-3:]):
            if not isinstance(turn, dict):
                continue
            followup_kind = turn.get("assistant_followup_kind")
            if isinstance(followup_kind, str) and followup_kind:
                return followup_kind
        return None

    def _detect_recent_pullback_anchor(self, recent_turns: object) -> str | None:
        if not isinstance(recent_turns, list):
            return None
        for turn in reversed(recent_turns[-3:]):
            if not isinstance(turn, dict):
                continue
            anchor = turn.get("assistant_pullback_anchor")
            if isinstance(anchor, str) and anchor.strip():
                return anchor.strip()
        return None

    def _compose_recent_pullback_anchor_message(
        self,
        *,
        raw_input: str,
        recent_pullback_anchor: str | None,
    ) -> str | None:
        if not recent_pullback_anchor:
            return None
        if not self._looks_like_pullback_anchor_follow_up(raw_input):
            return None
        anchor_title = recent_pullback_anchor.rstrip("？?。！! ")
        return (
            f"可以，我们刚才提到的这部分基础信息，更像是先看看{anchor_title}这一题。"
            f"不用一下子答得很快，我们就顺着{anchor_title}这部分慢慢往下看。"
        )

    def _compose_companion_weak_pullback_message(
        self,
        *,
        recent_topic: str | None,
        next_question: dict | None,
    ) -> str:
        next_title = self._question_title_phrase(next_question, fallback="后面这部分")
        if recent_topic == "sleep_stress":
            return (
                f"刚才那种睡不稳、睡不着的感觉我大概接住了。"
                f"那我们先顺着看看{next_title}这题，你通常更接近哪种情况？"
            )
        if recent_topic == "travel":
            return (
                f"刚才说到想出去走走、换个安静点的地方，这个感觉我记得。"
                f"那我们先顺着看一下{next_title}这题，你会怎么选？"
            )
        return f"这段我先陪你接住。那我们先顺着看一下{next_title}这题，你会怎么选？"

    def _question_title_phrase(self, question: dict | None, *, fallback: str) -> str:
        title = self._next_title(question, fallback=fallback).strip()
        if not title:
            return fallback
        return title.rstrip("？?。！! ")

    def _looks_like_pullback_anchor_follow_up(self, raw_input: str) -> bool:
        normalized = self._normalize_text(raw_input)
        if not normalized:
            return False
        explicit_tokens = (
            "哪些基础信息",
            "什么基础信息",
            "哪部分",
            "哪一部分",
            "什么意思",
            "这一题是什么意思",
            "这部分是什么意思",
        )
        if any(self._normalize_text(token) in normalized for token in explicit_tokens):
            return True
        return normalized in {
            self._normalize_text("哪题"),
            self._normalize_text("哪一题"),
            self._normalize_text("这题"),
            self._normalize_text("这部分"),
        }

    def _looks_like_companion_follow_up(self, raw_input: str) -> bool:
        normalized = self._normalize_text(raw_input)
        if not normalized or len(normalized) > 12:
            return False
        explicit_tokens = (
            "靠不靠谱",
            "靠谱吗",
            "有用吗",
            "有效吗",
            "真的假的",
            "会不会",
            "能不能",
            "可以吗",
            "可以吃吗",
            "副作用",
            "坏处",
            "为什么",
            "怎么说",
            "怎么讲",
            "不舒服",
        )
        if any(self._normalize_text(token) in normalized for token in explicit_tokens):
            return True
        return raw_input.endswith(("吗", "么", "嘛", "呢", "?","？")) and len(normalized) <= 8

    def _looks_like_contextual_assent(self, raw_input: str) -> bool:
        normalized = self._normalize_text(raw_input)
        if not normalized or len(normalized) > 8:
            return False
        assent_tokens = (
            "好的",
            "好啊",
            "嗯",
            "嗯嗯",
            "可以",
            "行",
            "好的呀",
            "是的",
            "对",
            "明白了",
            "好",
        )
        return any(self._normalize_text(token) == normalized for token in assent_tokens)

    def _looks_like_contextual_fragment(self, raw_input: str, *, recent_topic: str) -> bool:
        normalized = self._normalize_text(raw_input)
        if not normalized:
            return False
        if self._looks_like_contextual_assent(raw_input):
            return False
        if raw_input.endswith(("吗", "么", "嘛", "呢", "?", "？")):
            return False
        disallowed = ("谢谢", "好的", "嗯", "嗯嗯", "可以", "行", "是的", "对", "明白了", "下一题", "继续问卷")
        if any(self._normalize_text(token) == normalized for token in disallowed):
            return False
        if recent_topic == "travel":
            if len(normalized) > 12:
                return False
            return len(normalized) <= 6
        if recent_topic == "sleep_stress":
            if len(normalized) > 28:
                return False
            return any(
                token in raw_input
                for token in (
                    "工作",
                    "上班",
                    "晚上",
                    "夜里",
                    "半夜",
                    "忙",
                    "压力",
                    "睡不着",
                    "明天有安排",
                    "第二天有安排",
                    "有安排",
                )
            )
        return False

    def _looks_like_contextual_choice_reply(self, raw_input: str) -> bool:
        normalized = self._normalize_text(raw_input)
        if not normalized or len(normalized) > 12:
            return False
        choice_tokens = (
            "第一个",
            "第二个",
            "前者",
            "后者",
            "前一个",
            "后一个",
            "我选第一个",
            "我选第二个",
            "选第一个",
            "选第二个",
        )
        return any(self._normalize_text(token) == normalized for token in choice_tokens)

    def _compose_companion_topic_message(
        self,
        *,
        topic: str,
        raw_input: str,
        is_follow_up: bool,
        deescalate: bool,
    ) -> str:
        normalized = self._normalize_text(raw_input)
        if topic == "meal":
            if deescalate:
                return (
                    "这顿其实已经很有家常和安稳的感觉了，先把这个偏好放在这儿也挺好。"
                    "后面我们也可以再慢慢顺着看看你最近更想吃得轻一点还是更舒服一点。"
                )
            return (
                "可以啊，西红柿炒鸡蛋挺家常的，酸甜一点也比较下饭。"
                "你要是想中午吃得更舒服些，再配个青菜或者热汤，会更顺口一点。"
            )
        if topic == "melatonin":
            if deescalate:
                return (
                    "你在意的点我大概接住了，先把这个顾虑放在这儿就好。"
                    "后面也可以慢慢顺着看看，你最近更困扰的是节奏乱掉，还是晚上就是不太容易放松下来。"
                )
            if is_follow_up and any(
                token in normalized
                for token in (
                    self._normalize_text("靠不靠谱"),
                    self._normalize_text("靠谱吗"),
                    self._normalize_text("有用吗"),
                    self._normalize_text("有效吗"),
                    self._normalize_text("真的假的"),
                )
            ):
                return (
                    "如果你是问靠不靠谱，褪黑素更像是在帮身体对一下作息节奏，"
                    "不太像那种一下把人按睡着的东西。有人会觉得有点帮助，也有人感觉一般，"
                    "所以更像是因人而异。"
                )
            if is_follow_up and any(
                token in normalized
                for token in (
                    self._normalize_text("不舒服"),
                    self._normalize_text("副作用"),
                    self._normalize_text("坏处"),
                    self._normalize_text("会不会"),
                    self._normalize_text("可以吃吗"),
                    self._normalize_text("能不能"),
                )
            ):
                return (
                    "如果你是在担心会不会不舒服，很多人更在意的通常是吃完之后有没有头昏、"
                    "犯困或者第二天还觉得没缓过来。要不要碰它，往往也和你自己现在最困扰的是节奏乱，"
                    "还是单纯睡不着有关。"
                )
            return (
                "褪黑素更像是在提醒身体“差不多该准备休息了”，不太像一下子把人按睡着的那种东西。"
                "有些人会觉得更容易犯困一点，也有人觉得没太大感觉。你是更想了解它靠不靠谱，还是担心吃了之后会不会不舒服？"
            )
        if topic == "milk_tea":
            if deescalate:
                return (
                    "这种想喝点甜的、让自己缓一下的感觉我接住了，先不用把它越聊越细。"
                    "后面也可以慢慢顺着看看，你最近更像是想提神，还是单纯想让自己放松一点。"
                )
            return (
                "奶茶最大的问题一般还是糖和咖啡因，喝完容易一时舒服，但晚一点可能会更精神，"
                "有些人还会觉得心慌或者口渴。要是你就是想解馋，选小杯、少糖，或者白天喝，会轻一点。"
            )
        if topic == "sleep_stress":
            if deescalate:
                if any(
                    token in normalized
                    for token in (
                        self._normalize_text("我选第二个"),
                        self._normalize_text("第二个"),
                        self._normalize_text("后者"),
                        self._normalize_text("后一个"),
                    )
                ):
                    return (
                        "那更像是脑子一直停不下来这一边。我们先把这点放在这儿，"
                        "后面也可以慢慢顺着看看你的作息和状态。"
                    )
                if any(
                    token in normalized
                    for token in (
                        self._normalize_text("我选第一个"),
                        self._normalize_text("第一个"),
                        self._normalize_text("前者"),
                        self._normalize_text("前一个"),
                    )
                ):
                    return (
                        "那听起来更像是身体也会跟着紧起来那一边。我们先把这点放在这儿，"
                        "后面也可以慢慢顺着看看你的作息和状态。"
                    )
                if any(token in normalized for token in ("压力", "安排", "睡不着")):
                    return (
                        "听起来多半是在压力上来、又惦记着后面安排的时候，这种睡不着会更明显。"
                        "我们先把这点放在这儿，后面也可以慢慢顺着看看你的作息和状态。"
                    )
                if any(token in normalized for token in ("工作忙的时候", "工作忙时", "上班的时候", "忙的时候")):
                    return (
                        "听起来更多是在你工作忙的时候，这种睡不着的感觉会更容易冒出来。"
                        "我们先把这点放在这儿，后面也可以慢慢顺着看看你的作息和状态。"
                    )
                if any(token in normalized for token in ("一般在晚上", "晚上", "夜里", "半夜")):
                    return (
                        "这样看起来，它更像是到了晚上才慢慢翻上来的那种状态。"
                        "这点我们先放在这儿，后面也可以顺着看看你最近晚上的节奏和休息感。"
                    )
                return (
                    "听起来这段时间的睡眠确实一直被这类感觉牵着走，不是一下就能松开的。"
                    "我们先把这点放在这儿，后面也可以慢慢顺着看看你的作息和状态。"
                )
            if is_follow_up and any(token in normalized for token in ("工作忙的时候", "工作忙时", "上班的时候", "忙的时候")):
                return (
                    "听起来这种状态在你工作忙、脑子一直转的时候会更明显。"
                    "那种人已经很累了，但一躺下反而更停不下来的感觉，确实挺磨人的。"
                )
            if is_follow_up and any(token in normalized for token in ("一般在晚上", "晚上", "夜里", "半夜")):
                return (
                    "如果更容易在晚上冒出来，那多半就是白天压着的东西一静下来就一起涌上来了。"
                    "这种越到夜里越清醒的感觉，真的很消耗人。"
                )
            if any(token in normalized for token in ("入睡比较困难", "入睡困难")):
                return (
                    "听起来你最近更明显的困扰是在入睡这一步，明明想睡却不太容易慢慢进去。"
                    "这种卡在开头的感觉其实很消耗人。要是你愿意，也可以和我说说，最近通常是躺下之后脑子停不下来，"
                    "还是身体明明很累却一直松不下去？"
                )
            if "压力" in normalized:
                return (
                    "听起来你像是压力一上来，晚上就更难慢慢松下来，所以才会拖到很晚都睡不着。"
                    "这种时候确实很磨人。要是你愿意，也可以和我说说，那会儿更像是脑子停不下来，"
                    "还是整个人一直绷着放不松？"
                )
            return (
                "那种明明很累却还是睡不着、越到晚上越清醒的感觉，确实很消耗人。"
                "要是你愿意，也可以和我说说，最近这种情况更像是偶尔出现，还是已经反复一阵子了？"
            )
        if topic == "travel":
            if deescalate:
                if normalized:
                    return (
                        f"{raw_input}这个方向其实挺适合慢一点走走、换换节奏的。"
                        "先把这个偏好放在这儿，后面也可以再慢慢顺着看看你更想要哪种放松感。"
                    )
                return (
                    "这个方向本身就挺适合慢下来、换换节奏的。"
                    "先把这个偏好放在这儿，后面也可以再慢慢顺着看看你更想要哪种放松感。"
                )
            if is_follow_up and normalized and not self._detect_companion_topic(raw_input):
                return (
                    f"{raw_input}也不错呀，要是你更想顺着这个方向慢慢安排，其实也挺好落地的。"
                    "你是更想慢慢逛逛，还是更在意吃的和住得舒服一点？"
                )
            return (
                "如果你是想放松一点，海边、小城或者节奏慢一点的地方通常都会舒服些。"
                "比起赶景点，找个能慢慢走、能早点休息的地方，反而更像真的在散心。"
            )
        return None

    def _compose_companion_return_message(self, *, language: str, next_question: dict | None) -> str:
        if language.lower().startswith("en"):
            next_title = self._next_title(next_question, fallback="the next question")
            return f"We can leave that here for now. Let's head back to the quiz and continue with {next_title}."
        next_title = self._next_title(next_question, fallback="下一题")
        return f"我们先回到问卷，我陪你继续往下答。接下来想请你回答{next_title}。"

    def _compose_companion_soft_return_message(
        self,
        *,
        finalized: object,
        language: str,
        next_question: dict | None,
    ) -> str:
        raw_input = str(getattr(finalized, "raw_input", "") or "")
        if language.lower().startswith("en"):
            next_title = self._next_title(next_question, fallback="the next question")
            topic_lead = self._compose_soft_return_topic_lead(raw_input=raw_input, language="en")
            return f"{topic_lead} Can we go one step further and look at {next_title} first?"
        next_title = self._question_title_phrase(next_question, fallback="下一题")
        topic_lead = self._compose_soft_return_topic_lead(raw_input=raw_input, language="zh")
        return f"{topic_lead} 那我们顺着看一下{next_title}这题，你会怎么选？"

    def _compose_soft_return_topic_lead(self, *, raw_input: str, language: str) -> str:
        lowered = raw_input.strip().lower()
        if language == "en":
            if any(token in lowered for token in ("beach", "coast", "travel", "trip", "vacation")):
                return "A slower trip or a couple of days by the water could really help you breathe a bit."
            if any(token in lowered for token in ("food", "restaurant", "eat")):
                return "Finding somewhere to eat well and loosen up sounds like a decent idea."
            return "We can leave this on a gentle note instead of cutting it off abruptly."
        if any(token in lowered for token in ("海边", "旅游", "旅行", "景点")):
            return "想去海边或找个节奏慢一点的地方放空两天，其实挺好的。"
        if "褪黑素" in lowered:
            return "褪黑素这类东西，很多人也是在作息乱掉时才会开始留意。"
        if any(token in lowered for token in ("散散心", "放松", "安静点")):
            return "想找个地方散散心、放松一下，也很正常。"
        if any(token in lowered for token in ("美食", "吃点好的")):
            return "换个地方走走、吃点喜欢的东西，听起来也不错。"
        if any(token in lowered for token in ("西红柿炒鸡蛋", "中午吃什么", "午饭", "午餐", "吃什么")):
            return "西红柿炒鸡蛋这种家常一点的午饭，其实就挺舒服的。"
        if "奶茶" in lowered:
            return "想喝点甜的、让自己缓一缓，也很能理解。"
        return "这段我们先轻轻放在这儿，不用一下子拐得太硬。"

    def _compose_companion_completion_message(self, *, language: str) -> str:
        if language.lower().startswith("en"):
            return (
                "We can gently leave that here for now. Thank you for sharing. "
                "I now have a clearer picture of your sleep habits, and next I will organize a more personalized "
                "sound, light, and scent sleep plan for you."
            )
        return (
            "我们先把这段话轻轻放在这里。感谢你的分享。我已经大致了解了你的睡眠习惯，"
            "接下来会结合你记录下来的作息与感受，为你整理更适合你的专属声、光、香睡眠方案。"
        )

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

    def _is_companion_message_acceptable(self, message: str, *, finalized: object) -> bool:
        response_facts = getattr(finalized, "response_facts", {})
        if not response_facts.get("stay_in_companion"):
            return True
        if str(response_facts.get("continue_chat_intent", "none")) != "strong":
            return True
        normalized_message = self._normalize_text(message)
        forbidden_terms = (
            "问卷",
            "回到问卷",
            "继续回答",
            "下一题",
            "接下来请",
            "接下来想请你回答",
        )
        if any(self._normalize_text(term) in normalized_message for term in forbidden_terms):
            return False
        titles = self._grounding_titles(
            primary=self._next_title(getattr(finalized, "current_question", None), fallback=""),
            next_question=getattr(finalized, "next_question", None),
        )
        return not self._message_mentions_titles(message, titles)

    def _companion_overlay_mode(self, response_facts: dict) -> str:
        if response_facts.get("stay_in_companion"):
            return "stay_in_companion"
        if response_facts.get("companion_soft_return_to_quiz"):
            return "soft_return_to_quiz"
        if response_facts.get("return_to_quiz"):
            return "return_to_quiz"
        if response_facts.get("companion_completion_wrapup"):
            return "completion_wrapup"
        return "none"

    def _log_companion_diagnostic(self, event: str, **fields: object) -> None:
        payload = {
            "diagnostic": "companion_response",
            "event": event,
            **fields,
        }
        _DIAGNOSTIC_LOGGER.warning(json.dumps(payload, ensure_ascii=False, sort_keys=True))
