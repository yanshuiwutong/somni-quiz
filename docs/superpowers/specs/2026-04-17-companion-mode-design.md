# Companion Mode Design

## Summary

Add a lightweight companion-mode overlay to the conversational quiz runtime so non-control non-content turns can temporarily route to a "companion assistant" persona without changing the existing answer extraction pipeline or the gRPC API shape.

The feature must preserve current questionnaire behavior:

- content understanding, attribution, apply, and progress logic stay unchanged
- control-style non-content intents stay unchanged
- weather handling stays unchanged
- gRPC request and response message shapes stay unchanged

The new behavior applies only to:

- `pullback_chat`
- `identity`

These intents may enter companion mode. While companion mode is active, the system may still silently record answers from chat text, but the outward response remains companion-style until the runtime decides to return to the quiz.

## Goals

- Make the assistant feel caring and emotionally responsive during side conversations.
- Keep answer extraction and session progress working in the background.
- Avoid breaking existing content logic, non-content control logic, or gRPC contracts.
- Ensure companion mode can be implemented as an internal runtime overlay rather than a rewrite of the graph.

## Non-Goals

- No changes to protobuf definitions.
- No changes to `TurnInput` or public turn result shape.
- No new control intents.
- No medical or psychological advice beyond light companionship and optional escalation to professional help.

## Runtime Placement

Add a new internal runtime step after branch execution and before finalization:

- `classify`
- `content` or `non_content` branch
- `CompanionTransition`
- `finalize`
- `respond`

`CompanionTransition` is responsible for:

- deciding whether to enter companion mode
- deciding whether companion mode stays active
- deciding whether to return to the quiz
- updating companion-related session state
- setting response-fact overrides such as `answer_status_override`

It must not:

- re-run answer extraction
- mutate question answers directly
- generate final user-facing text

## Session State Changes

Extend `session_memory` with a new optional `companion_context` object.

Suggested fields:

- `active: bool`
- `mode: "smalltalk" | "supportive" | null`
- `entered_from_question_id: str | null`
- `rounds_since_enter: int`
- `last_turn_continue_chat_intent: "none" | "weak" | "strong" | null`
- `last_trigger_reason: str | null`

Meaning:

- `smalltalk` is for lightweight side chat such as greetings, thanks, or identity questions.
- `supportive` is for emotional discomfort, distress, insomnia complaints, personal troubles, or question-like support seeking.
- `rounds_since_enter` counts only turns spent inside companion mode.

No existing session-memory fields should change meaning.

## Non-Content Entry Rules

Existing non-content intents split into three groups.

### Control Intents

Remain unchanged and never enter companion mode:

- `view_all`
- `view_previous`
- `view_current`
- `view_next`
- `navigate_previous`
- `navigate_next`
- `skip`
- `undo`
- `modify_previous`

### Tool Intent

Remain unchanged and never enter companion mode:

- `weather_query`

### Companion-Eligible Intents

May enter companion mode:

- `pullback_chat`
- `identity`

Entry behavior:

- `identity` enters companion mode as `smalltalk`
- `pullback_chat` enters companion mode as either `smalltalk` or `supportive`

## Companion Entry vs Continue Logic

These are separate phases and should not be evaluated as parallel labels for the same turn.

### Entry Phase

Only used when companion mode is currently inactive.

The runtime decides:

- `mode = smalltalk`
- `mode = supportive`
- `mode = none`

Rules:

- `smalltalk`
  - greetings
  - thanks
  - identity-style chat
  - short harmless chatter
  - empty or near-empty non-content chat
- `supportive`
  - emotional discomfort
  - bodily discomfort related to sleep, such as headache or hard-to-sleep complaints
  - support-seeking questions
  - distress, stress, anxiety, frustration, loneliness, or similar themes

### Continue Phase

Only used when companion mode is already active.

The runtime decides:

- `continue_chat_intent = none`
- `continue_chat_intent = weak`
- `continue_chat_intent = strong`

Rules:

- `strong`
  - new emotional distress or discomfort content
  - explicit wish to keep talking
  - support-seeking question
  - clear elaboration of the previous companion-topic thread
  - answer-containing turns that also still contain emotional/supportive content
- `weak`
  - brief acknowledgements
  - light chatter
  - thanks without new topic expansion
- `none`
  - explicit return-to-quiz language
  - pure control intent
  - pure answer content with no residual companion-chat signal

This continue-phase judgment may use LLM assistance, but only inside `CompanionTransition` and always behind hard rule boundaries and a rule-based fallback.

## Companion Mode Lifecycle

### Smalltalk Mode

`smalltalk` follows the same practical behavior as the previously agreed "two-turn weak chat" path.

Behavior:

- enter on companion-eligible lightweight chat
- allow at most 2 companion turns
- after the second turn, return to the quiz unless the current turn escalates to a clear supportive conversation

If a later turn inside `smalltalk` clearly becomes emotional/supportive, companion mode may upgrade from `smalltalk` to `supportive`.

### Supportive Mode

`supportive` allows longer multi-turn emotional conversation.

Behavior:

- continue counting `rounds_since_enter`
- at `rounds_since_enter >= 4`, evaluate whether the current turn still has `continue_chat_intent = strong`
- if yes, reset `rounds_since_enter` to `0` and continue in supportive mode
- if not, return to the quiz

### Explicit Return

At any time, explicit return-to-quiz language immediately exits companion mode.

Examples:

- "继续问卷"
- "下一题吧"
- "先不聊了"

## Answer Handling While Companion Mode Is Active

Current answer extraction must continue to work exactly as it does now.

That means:

- content turns still run through the current content branch
- detected answers still update `answered_records`
- partial answers still work
- modifications still work

Additional rule:

- if companion mode is active, outward messaging may hide the fact that an answer was recorded

Two cases matter:

### Silent Recording of Other Questions

If the user mentions an answer for another question while chatting in companion mode:

- record it normally in backend state
- keep the front-end response in companion style
- do not emit quiz-style "recorded" language

### Answering the Current Question

If companion mode is active and the user clearly answers the current quiz question:

- record it normally
- return to the quiz on that same runtime turn
- restore normal questionnaire response flow

This is the main bridge back into the quiz from natural conversation.

## Response-Facts Additions

`CompanionTransition` should enrich `branch_result.response_facts` with internal control flags.

Suggested fields:

- `stay_in_companion: bool`
- `return_to_quiz: bool`
- `companion_mode: "smalltalk" | "supportive" | null`
- `answer_status_override: "NOT_RECORDED" | null`
- `silent_recorded_question_ids: list[str]`
- `silent_modified_question_ids: list[str]`

These are internal runtime facts, not protocol changes.

## Response Layer Behavior

`respond.py` should gain a companion-priority overlay above current quiz-style response generation.

Priority order:

1. `return_to_quiz = True`
2. `stay_in_companion = True`
3. existing normal response logic

Implications:

- while companion mode is active, existing `answered`, `modified`, `clarification`, `navigate`, or `pullback` outcomes still exist internally, but they do not directly own the outward message
- once the runtime returns to the quiz, normal response composition resumes

### Companion Prompt

Add a dedicated prompt for companion-mode responses, for example:

- `prompts/layer3/companion_response.md`

Prompt inputs should include:

- companion mode
- current question summary
- whether this turn silently recorded answers
- whether this turn returns to the quiz
- short recent companion-topic memory

Prompt guardrails:

- warm, caring, and light
- no diagnosis
- no medical advice
- no psychological treatment advice
- when necessary, gently suggest professional support

### Fallback Templates

If no LLM is available, use simple deterministic templates:

- `smalltalk`
  - short friendly response
- `supportive`
  - empathy plus invitation to continue briefly
- `return_to_quiz`
  - gentle wrap-up plus natural transition back to the quiz

## gRPC Compatibility

No protobuf changes are allowed.

The only runtime-specific behavior change is `answer_status_code`.

Rule:

- while companion mode is active, always return `NOT_RECORDED`

This applies even if answers were silently recorded in backend state.

Implementation detail:

- gRPC service should first check `answer_status_override`
- if set, return that value
- otherwise keep using the existing `derive_answer_status_code(...)`

`answer_record` must still return the latest backend answer state.

This preserves data integrity without changing the client protocol shape.

## Recommended Module Changes

Primary changes:

- `src/somni_graph_quiz/contracts/session_memory.py`
  - initialize `companion_context`
- `src/somni_graph_quiz/runtime/companion_transition.py`
  - new runtime decision step
- `src/somni_graph_quiz/runtime/engine.py`
  - invoke `CompanionTransition` between branch execution and finalization
- `src/somni_graph_quiz/nodes/layer3/respond.py`
  - add companion-priority overlay
- `src/somni_graph_quiz/adapters/grpc/service.py`
  - apply `answer_status_override`

Optional support modules:

- `src/somni_graph_quiz/runtime/companion_rules.py`
  - rule fallback for entry and continue decisions

Prompt additions:

- `prompts/layer3/companion_response.md`

## Test Plan

### Unit Tests

- `pullback_chat` greeting enters `smalltalk`
- `identity` enters `smalltalk`
- distress-style non-content input enters `supportive`
- control intents never enter companion mode
- `weather_query` never enters companion mode
- `supportive` at round 4 with `strong` intent resets `rounds_since_enter`
- `supportive` at round 4 without `strong` intent returns to quiz
- current-question answer while in companion mode exits companion mode
- other-question answer while in companion mode records silently and stays in companion mode
- companion mode sets `answer_status_override = NOT_RECORDED`

### Integration Tests

- gRPC chat greeting enters companion mode but keeps response shape unchanged
- companion-mode turn silently records answers and still returns `answer_status_code = NOT_RECORDED`
- exiting companion mode restores normal `answer_status_code`
- normal content path remains unchanged when companion mode is never entered
- normal control non-content path remains unchanged
- weather flow remains unchanged

### Regression Scenarios

- `你好` -> companion smalltalk -> second light chat -> return to quiz
- `你是谁` -> companion self-intro -> return to quiz
- `我最近头疼睡不着` -> supportive companion
- supportive chat reaches 4 turns and gets reset because user clearly keeps talking
- supportive chat reaches 4 turns and returns to quiz because user no longer keeps talking
- companion chat includes an answer to another question and answer is silently captured
- companion chat answers the current question and returns to quiz

## Assumptions

- Existing answer extraction behavior must remain source-of-truth and must not be reimplemented inside companion mode.
- Companion mode is an internal runtime overlay, not a separate session or adapter protocol.
- LLM-based semantic judgment is optional and must always have a rule-based fallback.
- "Non-content non-control" companion entry currently means only `pullback_chat` and `identity`.
- Companion-mode outward behavior intentionally hides answer-recording status by forcing `NOT_RECORDED` while active.
