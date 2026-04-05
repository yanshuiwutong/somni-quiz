# Non-Content Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the `non_content` flow in `somni-graph-quiz` so record viewing, previous/next navigation, skip/undo/modify-previous, and Somni pullback responses all work consistently across runtime, gRPC, and Streamlit.

**Architecture:** Keep the existing 3-layer graph runtime and extend the current `content | non_content` split rather than re-architecting the branch model. Drive the change with TDD: add failing routing/action tests first, then expand `non_content` action facts, then teach finalize/response to consume those facts, and finally seal the behavior with blackbox regression and optional real-LLM smoke coverage.

**Tech Stack:** Python 3.11, pytest, grpcio, streamlit, markdown prompts, fake/real LLM providers.

---

### Task 1: Save the Action Model in Tests

**Files:**
- Modify: `G:\somni\somni-graph-quiz\tests\unit\nodes\layer1\test_turn_classify.py`
- Modify: `G:\somni\somni-graph-quiz\tests\unit\nodes\layer2\test_non_content_branch.py`
- Test: `G:\somni\somni-graph-quiz\tests\unit\nodes\layer1\test_turn_classify.py`
- Test: `G:\somni\somni-graph-quiz\tests\unit\nodes\layer2\test_non_content_branch.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_turn_classify_routes_identity_question_to_non_content(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-who",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )

    result = TurnClassifyNode().run(
        graph_state,
        TurnInput(
            session_id="session-who",
            channel="grpc",
            input_mode="message",
            raw_input="你是谁",
            language_preference="zh-CN",
        ),
    )

    assert result["branch_decision"]["main_branch"] == "non_content"


def test_non_content_branch_view_previous_returns_previous_record(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-view-prev",
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
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["recent_turns"] = [
        {"turn_index": 0, "recorded_question_ids": ["question-01"], "modified_question_ids": []}
    ]

    result = NonContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-view-prev",
            channel="grpc",
            input_mode="message",
            raw_input="查看上一题记录",
            language_preference="zh-CN",
        ),
    )

    assert result["response_facts"]["non_content_action"] == "view_previous"
    assert result["response_facts"]["view_target_question_id"] == "question-01"


def test_non_content_branch_navigate_previous_switches_current_question(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-prev",
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
    graph_state["session_memory"]["current_question_id"] = "question-02"
    graph_state["session_memory"]["pending_question_ids"] = ["question-02", "question-03", "question-04"]

    result = NonContentBranch().run(
        graph_state,
        TurnInput(
            session_id="session-prev",
            channel="grpc",
            input_mode="message",
            raw_input="上一题",
            language_preference="zh-CN",
        ),
    )

    assert result["response_facts"]["non_content_action"] == "navigate_previous"
    assert result["state_patch"]["session_memory"]["current_question_id"] == "question-01"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m pytest G:\somni\somni-graph-quiz\tests\unit\nodes\layer1\test_turn_classify.py G:\somni\somni-graph-quiz\tests\unit\nodes\layer2\test_non_content_branch.py -q`

Expected: FAIL because the current rule/LLM contracts only expose `control/pullback` and do not support previous/view-previous actions.

- [ ] **Step 3: Write the minimal implementation**

```python
NON_CONTENT_ACTIONS = {
    "查看记录": "view_all",
    "查看上一题记录": "view_previous",
    "查看当前题记录": "view_current",
    "查看下一题": "view_next",
    "上一题": "navigate_previous",
    "下一题": "navigate_next",
    "跳过": "skip",
    "撤回": "undo",
    "改上一题": "modify_previous",
}


def _resolve_previous_question_id(self, session_memory: dict) -> str | None:
    answered_question_ids = list(session_memory["answered_question_ids"])
    if answered_question_ids:
        return answered_question_ids[-1]
    return None


if non_content_action == "view_previous":
    return create_branch_result(
        branch_type="non_content",
        response_facts={
            "non_content_action": "view_previous",
            "view_target_question_id": target_question_id,
            "view_records": [session_memory["answered_records"][target_question_id]],
        },
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m pytest G:\somni\somni-graph-quiz\tests\unit\nodes\layer1\test_turn_classify.py G:\somni\somni-graph-quiz\tests\unit\nodes\layer2\test_non_content_branch.py -q`

Expected: PASS for the new route and action-contract tests.

- [ ] **Step 5: Commit**

```bash
git add G:\somni\somni-graph-quiz\tests\unit\nodes\layer1\test_turn_classify.py G:\somni\somni-graph-quiz\tests\unit\nodes\layer2\test_non_content_branch.py G:\somni\somni-graph-quiz\src\somni_graph_quiz\nodes\layer1\turn_classify.py G:\somni\somni-graph-quiz\src\somni_graph_quiz\nodes\layer2\non_content\branch.py G:\somni\somni-graph-quiz\src\somni_graph_quiz\nodes\layer2\non_content\control_rules.py G:\somni\somni-graph-quiz\src\somni_graph_quiz\nodes\layer2\non_content\pullback_rules.py
git commit -m "feat: expand non-content routing actions"
```

### Task 2: Finalize the Action Facts

**Files:**
- Modify: `G:\somni\somni-graph-quiz\src\somni_graph_quiz\contracts\finalized_turn_context.py`
- Modify: `G:\somni\somni-graph-quiz\src\somni_graph_quiz\nodes\layer3\finalize.py`
- Modify: `G:\somni\somni-graph-quiz\tests\unit\runtime\test_finalize.py`
- Test: `G:\somni\somni-graph-quiz\tests\unit\runtime\test_finalize.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_finalize_preserves_view_previous_response_facts(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-finalize-view",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    branch_result = create_branch_result(
        branch_type="non_content",
        response_facts={
            "non_content_action": "view_previous",
            "view_target_question_id": "question-01",
            "view_records": [{"question_id": "question-01", "input_value": "22"}],
        },
    )

    finalized = TurnFinalizeNode().run(graph_state, branch_result)

    assert finalized.turn_outcome == "view_only"
    assert finalized.response_facts["non_content_action"] == "view_previous"
    assert finalized.response_facts["view_target_question_id"] == "question-01"


def test_finalize_marks_navigation_as_navigate_with_target(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-finalize-nav",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    branch_result = create_branch_result(
        branch_type="non_content",
        state_patch={"session_memory": {"current_question_id": "question-01"}},
        response_facts={
            "non_content_action": "navigate_previous",
            "next_question_id": "question-01",
        },
    )

    finalized = TurnFinalizeNode().run(graph_state, branch_result)

    assert finalized.turn_outcome == "navigate"
    assert finalized.response_facts["non_content_action"] == "navigate_previous"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m pytest G:\somni\somni-graph-quiz\tests\unit\runtime\test_finalize.py -q`

Expected: FAIL because finalize currently only knows `view`, `undo`, `next`, and `modify_previous`.

- [ ] **Step 3: Write the minimal implementation**

```python
if branch_result["branch_type"] == "non_content":
    action = branch_result.get("response_facts", {}).get("non_content_action")
    if action and action.startswith("view_"):
        return "view_only"
    if action in {"navigate_previous", "navigate_next", "modify_previous"}:
        return "navigate"

response_facts = {
    **branch_result.get("response_facts", {}),
    "current_question_title": next_question["title"] if next_question else None,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m pytest G:\somni\somni-graph-quiz\tests\unit\runtime\test_finalize.py -q`

Expected: PASS for the new outcome and action-fact assertions.

- [ ] **Step 5: Commit**

```bash
git add G:\somni\somni-graph-quiz\src\somni_graph_quiz\contracts\finalized_turn_context.py G:\somni\somni-graph-quiz\src\somni_graph_quiz\nodes\layer3\finalize.py G:\somni\somni-graph-quiz\tests\unit\runtime\test_finalize.py
git commit -m "feat: carry non-content action facts through finalize"
```

### Task 3: Make Somni Responses Match the Flow

**Files:**
- Modify: `G:\somni\somni-graph-quiz\prompts\layer3\response_composer.md`
- Modify: `G:\somni\somni-graph-quiz\src\somni_graph_quiz\nodes\layer3\respond.py`
- Modify: `G:\somni\somni-graph-quiz\tests\unit\nodes\layer3\test_response_composer.py`
- Test: `G:\somni\somni-graph-quiz\tests\unit\nodes\layer3\test_response_composer.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_response_composer_pullback_identity_question_reanchors_to_current_question() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="pullback",
        updated_answer_record={"answers": []},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "您平时通常的作息？"},
        finalized=False,
        response_language="zh-CN",
        response_facts={"non_content_action": "pullback", "pullback_reason": "identity_question"},
    )

    message = ResponseComposerNode().run(finalized)

    assert "作息" in message
    assert "你是谁" not in message


def test_response_composer_mentions_previous_record_when_viewing_previous() -> None:
    finalized = create_finalized_turn_context(
        turn_outcome="view_only",
        updated_answer_record={"answers": [{"question_id": "question-01", "selected_options": ["B"], "input_value": ""}]},
        updated_question_states={},
        current_question_id="question-02",
        next_question={"question_id": "question-02", "title": "您平时通常的作息？"},
        finalized=False,
        response_language="zh-CN",
        response_facts={
            "non_content_action": "view_previous",
            "view_records": [{"question_id": "question-01", "selected_options": ["B"], "input_value": ""}],
            "view_target_question_id": "question-01",
        },
    )

    message = ResponseComposerNode().run(finalized)

    assert "上一题" in message
    assert "B" in message
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m pytest G:\somni\somni-graph-quiz\tests\unit\nodes\layer3\test_response_composer.py -q`

Expected: FAIL because the response fallback only has coarse `pullback/view_only/navigate` templates and does not distinguish previous/current/next view scopes.

- [ ] **Step 3: Write the minimal implementation**

```python
if outcome == "pullback":
    if response_facts.get("pullback_reason") == "identity_question":
        return f"我会一直陪你把这份睡眠问卷慢慢答完。我们先回到这题：{next_title}。"
    return f"我听到了，不过我更想先接住你的睡眠情况。我们继续回答{next_title}。"

if outcome == "view_only":
    action = response_facts.get("non_content_action")
    records_summary = self._render_view_records(response_facts.get("view_records", []))
    if action == "view_previous":
        return f"上一题我已经记下的是：{records_summary}。我们现在继续回答{next_title}。"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m pytest G:\somni\somni-graph-quiz\tests\unit\nodes\layer3\test_response_composer.py -q`

Expected: PASS for the persona pullback and scoped record-view responses.

- [ ] **Step 5: Commit**

```bash
git add G:\somni\somni-graph-quiz\prompts\layer3\response_composer.md G:\somni\somni-graph-quiz\src\somni_graph_quiz\nodes\layer3\respond.py G:\somni\somni-graph-quiz\tests\unit\nodes\layer3\test_response_composer.py
git commit -m "feat: align Somni responses with non-content actions"
```

### Task 4: Seal Runtime, gRPC, and Streamlit Behavior with Blackbox Regressions

**Files:**
- Modify: `G:\somni\somni-graph-quiz\tests\integration\runtime\test_engine.py`
- Modify: `G:\somni\somni-graph-quiz\tests\regression\fixtures\regression_support.py`
- Create: `G:\somni\somni-graph-quiz\tests\regression\grpc\grpc_non_content_view_previous.json`
- Create: `G:\somni\somni-graph-quiz\tests\regression\grpc\grpc_non_content_identity_pullback.json`
- Create: `G:\somni\somni-graph-quiz\tests\regression\streamlit\streamlit_non_content_view_previous.json`
- Create: `G:\somni\somni-graph-quiz\tests\regression\streamlit\streamlit_non_content_identity_pullback.json`
- Modify: `G:\somni\somni-graph-quiz\tests\regression\test_grpc_regression.py`
- Modify: `G:\somni\somni-graph-quiz\tests\regression\test_streamlit_regression.py`
- Test: `G:\somni\somni-graph-quiz\tests\integration\runtime\test_engine.py`
- Test: `G:\somni\somni-graph-quiz\tests\regression\test_grpc_regression.py`
- Test: `G:\somni\somni-graph-quiz\tests\regression\test_streamlit_regression.py`

- [ ] **Step 1: Write the failing tests and goldens**

```python
def test_engine_identity_pullback_keeps_current_question_and_reanchors(question_catalog: dict) -> None:
    graph_state = create_graph_state(
        session_id="session-engine-pullback",
        channel="grpc",
        quiz_mode="dynamic",
        question_catalog=question_catalog,
        language_preference="zh-CN",
    )
    graph_state["session_memory"]["current_question_id"] = "question-02"
    engine = GraphRuntimeEngine()

    result = engine.run_turn(
        graph_state,
        TurnInput(
            session_id="session-engine-pullback",
            channel="grpc",
            input_mode="message",
            raw_input="你是谁",
            language_preference="zh-CN",
        ),
    )

    assert result["pending_question"]["question_id"] == "question-02"
    assert "作息" in result["assistant_message"]
```

```json
{
  "case_id": "grpc_non_content_view_previous",
  "initial_state": {
    "answered_records": {
      "question-01": {
        "question_id": "question-01",
        "selected_options": ["B"],
        "input_value": "",
        "field_updates": {}
      }
    },
    "answered_question_ids": ["question-01"],
    "current_question_id": "question-02"
  },
  "turns": [{"input_mode": "message", "raw_input": "查看上一题记录"}],
  "expected": {"pending_question_id": "question-02", "assistant_contains": ["上一题", "B"]}
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m pytest G:\somni\somni-graph-quiz\tests\integration\runtime\test_engine.py G:\somni\somni-graph-quiz\tests\regression\test_grpc_regression.py G:\somni\somni-graph-quiz\tests\regression\test_streamlit_regression.py -q`

Expected: FAIL because the engine and adapters currently expose only the coarse non-content behavior.

- [ ] **Step 3: Write the minimal implementation**

```python
def assert_case_expectations(result: dict, expected: dict) -> None:
    if "assistant_contains" in expected:
        for token in expected["assistant_contains"]:
            assert token in result["assistant_message"]

    if "pending_question_id" in expected:
        assert result["pending_question"]["question_id"] == expected["pending_question_id"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m pytest G:\somni\somni-graph-quiz\tests\integration\runtime\test_engine.py G:\somni\somni-graph-quiz\tests\regression\test_grpc_regression.py G:\somni\somni-graph-quiz\tests\regression\test_streamlit_regression.py -q`

Expected: PASS for runtime, gRPC, and Streamlit blackbox coverage.

- [ ] **Step 5: Commit**

```bash
git add G:\somni\somni-graph-quiz\tests\integration\runtime\test_engine.py G:\somni\somni-graph-quiz\tests\regression\fixtures\regression_support.py G:\somni\somni-graph-quiz\tests\regression\grpc\grpc_non_content_view_previous.json G:\somni\somni-graph-quiz\tests\regression\grpc\grpc_non_content_identity_pullback.json G:\somni\somni-graph-quiz\tests\regression\streamlit\streamlit_non_content_view_previous.json G:\somni\somni-graph-quiz\tests\regression\streamlit\streamlit_non_content_identity_pullback.json G:\somni\somni-graph-quiz\tests\regression\test_grpc_regression.py G:\somni\somni-graph-quiz\tests\regression\test_streamlit_regression.py
git commit -m "test: add non-content regression coverage"
```

### Task 5: Extend Real-LLM Smoke and Final Verification

**Files:**
- Modify: `G:\somni\somni-graph-quiz\tests\integration\llm\test_real_provider_smoke.py`
- Modify: `G:\somni\somni-graph-quiz\docs\superpowers\regression-docx-coverage.md`
- Test: `G:\somni\somni-graph-quiz\tests\integration\llm\test_real_provider_smoke.py`

- [ ] **Step 1: Write the failing smoke expectations**

```python
@pytest.mark.llm
def test_real_provider_pullback_identity_question_returns_non_empty_message(real_runtime_state: dict) -> None:
    result = GraphRuntimeEngine().run_turn(
        real_runtime_state,
        TurnInput(
            session_id="session-llm-pullback",
            channel="grpc",
            input_mode="message",
            raw_input="你是谁",
            language_preference="zh-CN",
        ),
    )

    assert result["pending_question"]["question_id"] == real_runtime_state["session_memory"]["current_question_id"]
    assert result["assistant_message"].strip()
```

- [ ] **Step 2: Run smoke tests to verify they fail or skip for the right reason**

Run: `E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m pytest -m llm G:\somni\somni-graph-quiz\tests\integration\llm\test_real_provider_smoke.py -q`

Expected: SKIP when `SOMNI_LLM_*` is incomplete; otherwise FAIL until the new non-content smoke cases are added.

- [ ] **Step 3: Write the minimal implementation**

```python
@pytest.mark.llm
def test_real_provider_view_records_smoke(real_runtime_state: dict) -> None:
    result = GraphRuntimeEngine().run_turn(...)
    assert result["assistant_message"].strip()
    assert result["answer_record"]["answers"]
```

- [ ] **Step 4: Run the full verification**

Run: `E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m pytest G:\somni\somni-graph-quiz\tests -q`

Run: `E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m ruff check G:\somni\somni-graph-quiz\src G:\somni\somni-graph-quiz\tests`

Expected: PASS for offline suite and lint. The `-m llm` suite should PASS with configured Ark credentials or SKIP cleanly with the documented missing-config reason.

- [ ] **Step 5: Commit**

```bash
git add G:\somni\somni-graph-quiz\tests\integration\llm\test_real_provider_smoke.py G:\somni\somni-graph-quiz\docs\superpowers\regression-docx-coverage.md
git commit -m "test: extend non-content real-llm smoke coverage"
```
