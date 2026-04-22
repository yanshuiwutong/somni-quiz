# Companion Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add companion-mode overlay behavior that can enter from eligible non-content turns and answer-plus-emotion content turns, preserve existing answer extraction, keep gRPC shapes unchanged, and force `answer_status_code = NOT_RECORDED` for companion-owned turns.

**Architecture:** Keep the existing graph flow intact and insert a new `CompanionTransition` runtime step between branch execution and finalization. Companion mode owns only session-state decisions, answer-status masking, and response ownership; all answer extraction and question-state mutation stay in the existing content/non-content branches.

**Tech Stack:** Python 3.11, pytest, existing runtime graph contracts, gRPC adapter, prompt-based LLM fallback.

---

### Task 1: Add Companion State Fixtures And Failing Runtime Tests

**Files:**
- Modify: `tests/conftest.py`
- Create: `tests/unit/runtime/test_companion_transition.py`
- Modify: `tests/unit/runtime/test_engine.py`

- [ ] **Step 1: Write the failing fixture and runtime tests**

```python
# tests/conftest.py
@pytest.fixture()
def companion_question_catalog() -> dict:
    return {
        "question_order": ["question-01", "question-02", "question-03"],
        "question_index": {
            "question-01": {
                "question_id": "question-01",
                "title": "您的年龄段？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "18-24 岁"},
                    {"option_id": "B", "label": "25-34 岁"},
                ],
                "tags": ["基础信息"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["年龄", "age"],
                },
            },
            "question-02": {
                "question_id": "question-02",
                "title": "您平时通常几点睡？",
                "description": "",
                "input_type": "text",
                "options": [],
                "tags": ["作息"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": None,
                    "response_style": "default",
                    "matching_hints": ["入睡", "几点睡", "睡觉"],
                },
            },
            "question-03": {
                "question_id": "question-03",
                "title": "您醒来后多久能彻底清醒？",
                "description": "",
                "input_type": "radio",
                "options": [
                    {"option_id": "A", "label": "几乎立刻"},
                    {"option_id": "B", "label": "需要缓冲"},
                ],
                "tags": ["恢复"],
                "metadata": {
                    "allow_partial": False,
                    "structured_kind": "radio",
                    "response_style": "default",
                    "matching_hints": ["清醒", "恢复"],
                },
            },
        },
    }
```

```python
# tests/unit/runtime/test_companion_transition.py
from somni_graph_quiz.contracts.graph_state import create_graph_state
from somni_graph_quiz.contracts.turn_input import TurnInput
from somni_graph_quiz.runtime.companion_transition import CompanionTransition


def test_transition_enters_smalltalk_from_pullback_chat(companion_question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="companion-smalltalk",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "pullback_chat"
    branch_result = {"branch_type": "non_content", "state_patch": {}, "response_facts": {}}

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-smalltalk",
            channel="grpc",
            input_mode="message",
            raw_input="你好",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is True
    assert result["state_patch"]["session_memory"]["companion_context"]["mode"] == "smalltalk"
    assert result["response_facts"]["stay_in_companion"] is True
    assert result["response_facts"]["answer_status_override"] == "NOT_RECORDED"


def test_transition_enters_supportive_after_content_answer_with_distress(companion_question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="companion-content-entry",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["turn"]["main_branch"] = "content"
    graph_state["turn"]["non_content_intent"] = "none"
    branch_result = {
        "branch_type": "content",
        "state_patch": {
            "session_memory": {
                "answered_records": {
                    "question-02": {
                        "question_id": "question-02",
                        "selected_options": [],
                        "input_value": "12点",
                        "field_updates": {},
                    }
                },
                "answered_question_ids": ["question-02"],
                "pending_question_ids": ["question-01", "question-03"],
                "current_question_id": "question-01",
            }
        },
        "applied_question_ids": ["question-02"],
        "modified_question_ids": [],
        "partial_question_ids": [],
        "skipped_question_ids": [],
        "rejected_unit_ids": [],
        "clarification_needed": False,
        "response_facts": {},
    }

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-content-entry",
            channel="grpc",
            input_mode="message",
            raw_input="我一般12点睡，但最近总头疼睡不着",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["response_facts"]["stay_in_companion"] is True
    assert result["state_patch"]["session_memory"]["companion_context"]["mode"] == "supportive"
    assert result["response_facts"]["silent_recorded_question_ids"] == ["question-02"]


def test_transition_exits_when_current_question_answered_in_companion_mode(companion_question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="companion-exit-current-answer",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "supportive",
        "entered_from_question_id": "question-01",
        "rounds_since_enter": 2,
        "last_turn_continue_chat_intent": "strong",
        "last_trigger_reason": "distress",
    }
    graph_state["session_memory"]["current_question_id"] = "question-01"
    graph_state["turn"]["main_branch"] = "content"
    branch_result = {
        "branch_type": "content",
        "state_patch": {
            "session_memory": {
                "answered_records": {
                    "question-01": {
                        "question_id": "question-01",
                        "selected_options": ["B"],
                        "input_value": "",
                        "field_updates": {},
                    }
                },
                "answered_question_ids": ["question-01"],
                "current_question_id": "question-02",
            }
        },
        "applied_question_ids": ["question-01"],
        "modified_question_ids": [],
        "partial_question_ids": [],
        "skipped_question_ids": [],
        "rejected_unit_ids": [],
        "clarification_needed": False,
        "response_facts": {},
    }

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-exit-current-answer",
            channel="grpc",
            input_mode="message",
            raw_input="我25到34岁",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["response_facts"]["return_to_quiz"] is True
    assert result["response_facts"]["answer_status_override"] == "NOT_RECORDED"
    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is False
```

```python
# tests/unit/runtime/test_engine.py
def test_engine_keeps_companion_turn_status_masked(companion_question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="engine-companion-mask",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )

    result = GraphRuntimeEngine().run_turn(
        graph_state,
        TurnInput(
            session_id="engine-companion-mask",
            channel="grpc",
            input_mode="message",
            raw_input="你好",
            language_preference="zh-CN",
        ),
    )

    assert result["updated_graph_state"]["session_memory"]["companion_context"]["active"] is True
    assert result["updated_graph_state"]["session_memory"]["recent_turns"][-1]["turn_outcome"] == "pullback"
    assert result["updated_graph_state"]["session_memory"]["recent_turns"][-1]["answer_status_override"] == "NOT_RECORDED"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/unit/runtime/test_companion_transition.py tests/unit/runtime/test_engine.py -q
```

Expected:

- import failure for `somni_graph_quiz.runtime.companion_transition`, or
- assertion failures because `companion_context` and `answer_status_override` do not exist yet

- [ ] **Step 3: Write minimal fixture support and engine metadata support**

Implement only enough to let the tests compile once the runtime step exists:

```python
# tests/conftest.py
@pytest.fixture()
def companion_question_catalog() -> dict:
    ...
```

```python
# future engine expectation
recent_turns.append(
    {
        ...
        "answer_status_override": finalized.response_facts.get("answer_status_override"),
    }
)
```

- [ ] **Step 4: Run the runtime tests again**

Run:

```bash
python -m pytest tests/unit/runtime/test_companion_transition.py tests/unit/runtime/test_engine.py -q
```

Expected:

- still FAIL, but now only because production companion runtime code is missing or incomplete


### Task 2: Implement CompanionTransition With TDD

**Files:**
- Create: `src/somni_graph_quiz/runtime/companion_rules.py`
- Create: `src/somni_graph_quiz/runtime/companion_transition.py`
- Modify: `src/somni_graph_quiz/contracts/session_memory.py`
- Modify: `src/somni_graph_quiz/runtime/engine.py`

- [ ] **Step 1: Write the next failing lifecycle tests**

Add these tests to `tests/unit/runtime/test_companion_transition.py`:

```python
def test_transition_resets_supportive_round_counter_on_strong_turn_at_round_four(
    companion_question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="companion-reset-rounds",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "supportive",
        "entered_from_question_id": "question-02",
        "rounds_since_enter": 4,
        "last_turn_continue_chat_intent": "strong",
        "last_trigger_reason": "distress",
    }
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "pullback_chat"
    branch_result = {"branch_type": "non_content", "state_patch": {}, "response_facts": {}}

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-reset-rounds",
            channel="grpc",
            input_mode="message",
            raw_input="其实还有一件事让我更烦",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["state_patch"]["session_memory"]["companion_context"]["rounds_since_enter"] == 0
    assert result["response_facts"]["stay_in_companion"] is True


def test_transition_returns_to_quiz_when_supportive_turn_is_no_longer_strong(
    companion_question_catalog: dict,
) -> None:
    graph_state = create_graph_state(
        session_id="companion-return-round-four",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=companion_question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["companion_context"] = {
        "active": True,
        "mode": "supportive",
        "entered_from_question_id": "question-02",
        "rounds_since_enter": 4,
        "last_turn_continue_chat_intent": "weak",
        "last_trigger_reason": "distress",
    }
    graph_state["turn"]["main_branch"] = "non_content"
    graph_state["turn"]["non_content_intent"] = "pullback_chat"
    branch_result = {"branch_type": "non_content", "state_patch": {}, "response_facts": {}}

    result = CompanionTransition().apply(
        graph_state,
        TurnInput(
            session_id="companion-return-round-four",
            channel="grpc",
            input_mode="message",
            raw_input="嗯，谢谢你",
            language_preference="zh-CN",
        ),
        branch_result,
    )

    assert result["response_facts"]["return_to_quiz"] is True
    assert result["state_patch"]["session_memory"]["companion_context"]["active"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/unit/runtime/test_companion_transition.py -q
```

Expected:

- FAIL because transition logic does not yet support lifecycle counting and round reset

- [ ] **Step 3: Implement minimal companion rules and transition**

Implement focused runtime helpers:

```python
# src/somni_graph_quiz/runtime/companion_rules.py
from __future__ import annotations

import re

_SMALLTALK_TOKENS = ("你好", "您好", "hi", "hello", "谢谢", "thanks", "你是谁", "在吗", "哈哈")
_SUPPORTIVE_TOKENS = ("头疼", "难受", "睡不着", "失眠", "烦", "焦虑", "崩溃", "委屈", "压力", "怎么办")
_RETURN_TOKENS = ("继续问卷", "下一题", "先不聊了")
_STRONG_TOKENS = ("其实还有", "而且", "怎么办", "为什么", "很烦", "头疼", "睡不着", "压力")


def detect_entry_mode(*, raw_input: str, main_branch: str, non_content_intent: str, applied_question_ids: list[str]) -> str | None:
    text = raw_input.strip().lower()
    if non_content_intent == "identity":
        return "smalltalk"
    if non_content_intent == "pullback_chat":
        if any(token in text for token in _SUPPORTIVE_TOKENS):
            return "supportive"
        return "smalltalk"
    if main_branch == "content" and applied_question_ids and any(token in text for token in _SUPPORTIVE_TOKENS):
        return "supportive"
    return None


def detect_continue_chat_intent(raw_input: str) -> str:
    text = raw_input.strip().lower()
    if any(token in text for token in _RETURN_TOKENS):
        return "none"
    if any(token in text for token in _STRONG_TOKENS):
        return "strong"
    if text:
        return "weak"
    return "weak"
```

```python
# src/somni_graph_quiz/runtime/companion_transition.py
from __future__ import annotations

from copy import deepcopy

from somni_graph_quiz.runtime.companion_rules import detect_continue_chat_intent, detect_entry_mode


class CompanionTransition:
    def apply(self, graph_state: dict, turn_input: object, branch_result: dict) -> dict:
        raw_input = getattr(turn_input, "raw_input", "")
        session_memory = graph_state["session_memory"]
        companion_context = deepcopy(session_memory.get("companion_context") or self._empty_context())
        response_facts = dict(branch_result.get("response_facts", {}))
        state_patch = deepcopy(branch_result.get("state_patch", {}))
        state_patch.setdefault("session_memory", {})
        applied_question_ids = list(branch_result.get("applied_question_ids", []))
        current_question_id = session_memory.get("current_question_id")
        companion_owned = False

        if companion_context.get("active"):
            intent = detect_continue_chat_intent(raw_input)
            companion_context["last_turn_continue_chat_intent"] = intent
            companion_context["rounds_since_enter"] = int(companion_context.get("rounds_since_enter", 0)) + 1
            if current_question_id and current_question_id in applied_question_ids:
                companion_context = self._empty_context()
                response_facts["return_to_quiz"] = True
                companion_owned = True
            elif companion_context.get("mode") == "supportive" and companion_context["rounds_since_enter"] >= 4:
                if intent == "strong":
                    companion_context["rounds_since_enter"] = 0
                    response_facts["stay_in_companion"] = True
                    companion_owned = True
                else:
                    companion_context = self._empty_context()
                    response_facts["return_to_quiz"] = True
                    companion_owned = True
            elif companion_context.get("mode") == "smalltalk" and companion_context["rounds_since_enter"] >= 2:
                companion_context = self._empty_context()
                response_facts["return_to_quiz"] = True
                companion_owned = True
            else:
                response_facts["stay_in_companion"] = True
                companion_owned = True
        else:
            mode = detect_entry_mode(
                raw_input=raw_input,
                main_branch=graph_state["turn"].get("main_branch", "content"),
                non_content_intent=graph_state["turn"].get("non_content_intent", "none"),
                applied_question_ids=applied_question_ids,
            )
            if mode is not None:
                companion_context = {
                    "active": True,
                    "mode": mode,
                    "entered_from_question_id": session_memory.get("current_question_id"),
                    "rounds_since_enter": 0,
                    "last_turn_continue_chat_intent": None,
                    "last_trigger_reason": mode,
                }
                response_facts["stay_in_companion"] = True
                companion_owned = True

        if companion_owned:
            response_facts["companion_mode"] = companion_context.get("mode")
            response_facts["answer_status_override"] = "NOT_RECORDED"
            response_facts["silent_recorded_question_ids"] = applied_question_ids

        state_patch["session_memory"]["companion_context"] = companion_context
        return {
            **branch_result,
            "state_patch": state_patch,
            "response_facts": response_facts,
        }

    def _empty_context(self) -> dict:
        return {
            "active": False,
            "mode": None,
            "entered_from_question_id": None,
            "rounds_since_enter": 0,
            "last_turn_continue_chat_intent": None,
            "last_trigger_reason": None,
        }
```

```python
# src/somni_graph_quiz/contracts/session_memory.py
"companion_context": {
    "active": False,
    "mode": None,
    "entered_from_question_id": None,
    "rounds_since_enter": 0,
    "last_turn_continue_chat_intent": None,
    "last_trigger_reason": None,
},
```

```python
# src/somni_graph_quiz/runtime/engine.py
from somni_graph_quiz.runtime.companion_transition import CompanionTransition

...
self._companion = CompanionTransition()
...
branch_result = self._companion.apply(classified_state, turn_input, branch_result)
...
"answer_status_override": finalized.response_facts.get("answer_status_override"),
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python -m pytest tests/unit/runtime/test_companion_transition.py tests/unit/runtime/test_engine.py -q
```

Expected: PASS


### Task 3: Add Companion Response Ownership With TDD

**Files:**
- Modify: `tests/unit/nodes/layer3/test_response_composer.py`
- Modify: `src/somni_graph_quiz/nodes/layer3/respond.py`
- Create: `prompts/layer3/companion_response.md`

- [ ] **Step 1: Write the failing response tests**

```python
def test_response_composer_prefers_companion_message_when_staying_in_companion() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="answered",
        updated_answer_record={"answers": [{"question_id": "question-02", "input_value": "12点"}]},
        updated_question_states={},
        current_question_id="question-01",
        next_question={"question_id": "question-01", "title": "您的年龄段？"},
        finalized=False,
        response_language="zh-CN",
        response_facts={
            "stay_in_companion": True,
            "companion_mode": "supportive",
            "silent_recorded_question_ids": ["question-02"],
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "已记录" not in message
    assert "下一题" not in message


def test_response_composer_prefers_return_to_quiz_when_companion_answers_current_question() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="answered",
        updated_answer_record={"answers": [{"question_id": "question-01", "selected_options": ["B"]}]},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "您平时通常几点睡？"},
        finalized=False,
        response_language="zh-CN",
        response_facts={
            "return_to_quiz": True,
            "companion_mode": "supportive",
            "silent_recorded_question_ids": ["question-01"],
            "recorded_question_summaries": [{"question_id": "question-01", "title": "您的年龄段？"}],
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "年龄" in message
    assert "几点睡" in message or "下一题" in message
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/unit/nodes/layer3/test_response_composer.py -q
```

Expected:

- FAIL because the current composer still uses ordinary `answered` / `pullback` logic

- [ ] **Step 3: Implement minimal response-priority overlay**

```python
# src/somni_graph_quiz/nodes/layer3/respond.py
def run(self, finalized: object) -> str:
    ...
    response_facts = getattr(finalized, "response_facts", {})
    companion_message = self._try_companion(finalized)
    if companion_message is not None:
        return companion_message
    ...

def _try_companion(self, finalized: object) -> str | None:
    response_facts = getattr(finalized, "response_facts", {})
    if response_facts.get("return_to_quiz"):
        return self._compose_companion_return_zh(finalized)
    if response_facts.get("stay_in_companion"):
        return self._compose_companion_stay_zh(finalized)
    return None

def _compose_companion_stay_zh(self, finalized: object) -> str:
    response_facts = getattr(finalized, "response_facts", {})
    if response_facts.get("companion_mode") == "smalltalk":
        return "我在呢。你也可以继续跟我说说。"
    return "听起来你最近确实不太舒服。如果你愿意，可以继续跟我说说。"

def _compose_companion_return_zh(self, finalized: object) -> str:
    next_question = getattr(finalized, "next_question", None) or {}
    next_title = next_question.get("title", "下一题")
    return f"我先记下你刚才说的这些，我们继续回到问卷。接下来请回答{next_title}。"
```

```markdown
<!-- prompts/layer3/companion_response.md -->
# Companion Response

You are Somni's caring companion mode.

- Be warm and concise.
- Do not diagnose.
- Do not provide medical advice.
- Do not provide psychological treatment advice.
- If needed, gently encourage professional help.

## Input Payload

```json
{{ payload | tojson(indent=2) }}
```
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python -m pytest tests/unit/nodes/layer3/test_response_composer.py -q
```

Expected: PASS


### Task 4: Add gRPC Status Masking And Integration Tests

**Files:**
- Modify: `tests/integration/adapters/grpc/test_service.py`
- Modify: `src/somni_graph_quiz/adapters/grpc/service.py`

- [ ] **Step 1: Write the failing gRPC tests**

```python
def test_chat_quiz_companion_greeting_masks_answer_status_code() -> None:
    service = GrpcQuizService()
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="session-companion-greeting",
            language="zh-CN",
            questionnaire=_build_questionnaire(),
            quiz_mode="dynamic",
        ),
        context=None,
    )

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-companion-greeting",
            message="你好",
        ),
        context=None,
    )

    assert response.success is True
    assert response.answer_status_code == "NOT_RECORDED"


def test_chat_quiz_answer_plus_distress_keeps_answer_record_but_masks_status() -> None:
    service = GrpcQuizService()
    service.InitQuiz(
        somni_quiz_pb2.InitQuizRequest(
            session_id="session-answer-plus-distress",
            language="zh-CN",
            questionnaire=_build_questionnaire(),
            quiz_mode="dynamic",
        ),
        context=None,
    )

    service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-answer-plus-distress",
            message="22",
        ),
        context=None,
    )

    response = service.ChatQuiz(
        somni_quiz_pb2.ChatQuizRequest(
            session_id="session-answer-plus-distress",
            message="我一般11点睡，但最近总头疼睡不着",
        ),
        context=None,
    )

    assert response.success is True
    assert len(response.answer_record.answers) >= 1
    assert response.answer_status_code == "NOT_RECORDED"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/integration/adapters/grpc/test_service.py -q
```

Expected:

- FAIL because the service still derives `RECORDED` / `UPDATED` from recent turns without reading companion override

- [ ] **Step 3: Implement minimal status masking**

```python
# src/somni_graph_quiz/adapters/grpc/service.py
response_facts = result["updated_graph_state"].get("turn", {}).get("response_facts")
recent_turns = snapshot.graph_state["session_memory"].get("recent_turns", [])
recent_turn = recent_turns[-1] if recent_turns else None
answer_status_override = None
if isinstance(recent_turn, dict):
    answer_status_override = recent_turn.get("answer_status_override")
answer_status_code = answer_status_override or derive_answer_status_code(recent_turn)
```

If `recent_turn` cannot be relied on, instead read:

```python
companion_context = snapshot.graph_state["session_memory"].get("companion_context") or {}
if recent_turn and recent_turn.get("answer_status_override"):
    answer_status_code = recent_turn["answer_status_override"]
elif companion_context.get("active"):
    answer_status_code = "NOT_RECORDED"
else:
    answer_status_code = derive_answer_status_code(recent_turn)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python -m pytest tests/integration/adapters/grpc/test_service.py -q
```

Expected: PASS


### Task 5: Run Focused Verification And Final Regression Sweep

**Files:**
- No production file edits expected

- [ ] **Step 1: Run focused unit and integration suite**

Run:

```bash
python -m pytest tests/unit/runtime/test_companion_transition.py tests/unit/runtime/test_engine.py tests/unit/nodes/layer3/test_response_composer.py tests/integration/adapters/grpc/test_service.py -q
```

Expected: PASS

- [ ] **Step 2: Run the broader impacted suite**

Run:

```bash
python -m pytest tests/unit/nodes/layer2/test_non_content_branch.py tests/unit/runtime/test_finalize.py tests/unit/nodes/layer3/test_response_composer_weather_llm.py tests/integration/adapters/grpc/test_weather_default_city_grpc.py -q
```

Expected: PASS

- [ ] **Step 3: Run lint on impacted files**

Run:

```bash
python -m ruff check src/somni_graph_quiz/runtime src/somni_graph_quiz/nodes/layer3 src/somni_graph_quiz/adapters/grpc tests/unit/runtime tests/unit/nodes/layer3 tests/integration/adapters/grpc
```

Expected: PASS

- [ ] **Step 4: Commit**

Because this workspace currently has no `.git`, do not attempt `git add` or `git commit` here. If a git repository is restored later, use:

```bash
git add src/somni_graph_quiz/contracts/session_memory.py src/somni_graph_quiz/runtime/companion_rules.py src/somni_graph_quiz/runtime/companion_transition.py src/somni_graph_quiz/runtime/engine.py src/somni_graph_quiz/nodes/layer3/respond.py src/somni_graph_quiz/adapters/grpc/service.py tests/conftest.py tests/unit/runtime/test_companion_transition.py tests/unit/runtime/test_engine.py tests/unit/nodes/layer3/test_response_composer.py tests/integration/adapters/grpc/test_service.py prompts/layer3/companion_response.md docs/superpowers/plans/2026-04-17-companion-mode.md
git commit -m "add_companion_mode_runtime_and_status_masking"
```
