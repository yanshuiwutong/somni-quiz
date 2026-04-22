# DOCX 9Q Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align `somni-graph-quiz` with the provided 9-question dynamic questionnaire, convert the `.docx` acceptance examples into local blackbox regressions, and make offline regression plus optional online smoke pass.

**Architecture:** Keep the existing 3-layer graph runtime and extend its test assets plus content-understanding pipeline instead of porting the old monolithic service. Use one canonical 9-question questionnaire JSON for runtime, gRPC, Streamlit, and smoke tests, then drive behavior upgrades with blackbox regression cases and minimal node changes.

**Tech Stack:** Python 3.11, pytest, pydantic, streamlit, grpcio, langchain-openai-compatible provider.

---

### Task 1: Canonical 9-Question Questionnaire Asset

**Files:**
- Create: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\data\questionnaire_business9.json`
- Modify: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\src\somni_graph_quiz\app\streamlit_app.py`
- Modify: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression\fixtures\regression_support.py`
- Test: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\integration\adapters\streamlit\test_app_entry.py`
- Test: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression\test_runtime_regression.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_build_default_questionnaire_returns_9_questions() -> None:
    questionnaire = build_default_questionnaire()
    assert [q["question_id"] for q in questionnaire] == [
        "question-01",
        "question-02",
        "question-03",
        "question-04",
        "question-05",
        "question-06",
        "question-07",
        "question-08",
        "question-09",
    ]


def test_runtime_question_catalog_uses_business9_titles() -> None:
    catalog = runtime_question_catalog()
    assert catalog["question_order"][-1] == "question-09"
    assert catalog["question_index"]["question-08"]["title"] == "半夜醒来后，再次入睡困难吗？"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m pytest G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\integration\adapters\streamlit\test_app_entry.py G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression\test_runtime_regression.py -q`

Expected: FAIL because the bundled questionnaire and regression catalog still use the reduced fixture.

- [ ] **Step 3: Write the minimal implementation**

```python
BUSINESS9_QUESTIONNAIRE_PATH = PROJECT_ROOT / "data" / "questionnaire_business9.json"


def build_default_questionnaire() -> list[dict]:
    payload = json.loads(BUSINESS9_QUESTIONNAIRE_PATH.read_text(encoding="utf-8"))
    questionnaire = payload["questionnaire"]
    if len(questionnaire) != 9:
        raise ValueError("Bundled questionnaire must contain 9 questions")
    return questionnaire


def runtime_question_catalog() -> dict:
    questionnaire = build_default_questionnaire()
    return map_streamlit_questionnaire_to_catalog(questionnaire)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m pytest G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\integration\adapters\streamlit\test_app_entry.py G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression\test_runtime_regression.py -q`

Expected: PASS for the new questionnaire asset and catalog assertions.

- [ ] **Step 5: Commit**

```bash
git add G:\somni\somni-quiz-ai-main\somni-graph-quiz\data\questionnaire_business9.json G:\somni\somni-quiz-ai-main\somni-graph-quiz\src\somni_graph_quiz\app\streamlit_app.py G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression\fixtures\regression_support.py G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\integration\adapters\streamlit\test_app_entry.py
git commit -m "feat: add canonical 9-question questionnaire asset"
```

### Task 2: DOCX Blackbox Regression Cases

**Files:**
- Create: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression\content_cases\runtime_docx_multi_answer.json`
- Create: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression\content_cases\runtime_docx_free_wake_around_7.json`
- Create: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression\content_cases\runtime_docx_free_sleep_23.json`
- Create: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression\content_cases\runtime_docx_modify_answered.json`
- Create: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression\content_cases\runtime_docx_wake_back_ten_minutes.json`
- Create: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression\grpc\grpc_docx_view_all.json`
- Create: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression\streamlit\streamlit_docx_partial_followup.json`
- Modify: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression\fixtures\regression_support.py`
- Test: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression\test_runtime_regression.py`
- Test: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression\test_grpc_regression.py`
- Test: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression\test_streamlit_regression.py`

- [ ] **Step 1: Write the failing regression cases**

```json
{
  "case_id": "runtime_docx_multi_answer",
  "turns": [
    {"input_mode": "message", "raw_input": "我22岁，每天11点睡觉，7点起床"}
  ],
  "expected": {
    "answered_question_ids": ["question-01", "question-02"],
    "partial_question_ids": [],
    "pending_question_id": "question-03",
    "skipped_question_ids": []
  }
}
```

```json
{
  "case_id": "runtime_docx_free_wake_around_7",
  "initial_state": {"current_question_id": "question-04", "pending_question_ids": ["question-04"]},
  "turns": [{"input_mode": "message", "raw_input": "那7左右"}],
  "expected_answer_record": {"question-04": {"selected_options": ["B"]}}
}
```

- [ ] **Step 2: Run regression tests to verify they fail**

Run: `E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m pytest G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression -q`

Expected: FAIL because the new cases are not yet supported by the reduced understanding/mapping rules.

- [ ] **Step 3: Extend the regression assertion helpers minimally**

```python
def assert_runtime_expectations(graph_state: dict, turn_results: list[dict], expected: dict) -> None:
    final_turn = turn_results[-1]
    if "expected_answer_record" in expected:
        for question_id, answer_expectation in expected["expected_answer_record"].items():
            answer = graph_state["session_memory"]["answered_records"][question_id]
            for key, value in answer_expectation.items():
                assert answer[key] == value
```

- [ ] **Step 4: Run regression tests to verify the failures are now behavior-only**

Run: `E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m pytest G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression -q`

Expected: FAIL on runtime behavior assertions rather than missing fixture support.

- [ ] **Step 5: Commit**

```bash
git add G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression
git commit -m "test: add docx blackbox regression cases"
```

### Task 3: Content Understanding and Attribution Upgrades

**Files:**
- Modify: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\src\somni_graph_quiz\nodes\layer2\content\understand.py`
- Modify: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\src\somni_graph_quiz\nodes\layer2\content\attribution.py`
- Modify: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\src\somni_graph_quiz\nodes\layer2\content\mapping.py`
- Modify: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\src\somni_graph_quiz\nodes\layer2\content\apply.py`
- Test: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\unit\nodes\layer2\test_content_branch.py`
- Test: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression\test_runtime_regression.py`

- [ ] **Step 1: Write focused failing unit tests**

```python
def test_content_understand_splits_age_and_regular_schedule_without_hitting_relaxed_questions() -> None:
    result = ContentUnderstandNode().run(graph_state, TurnInput(...raw_input="我22岁，每天11点睡觉，7点起床"))
    assert [unit["winner_question_id"] for unit in result["content_units"]] == ["question-01", "question-02"]


def test_final_attribution_prefers_regular_schedule_without_relaxed_context() -> None:
    resolved = FinalAttributionNode().run(graph_state, ambiguous_time_unit)
    assert resolved["winner_question_id"] == "question-02"


def test_map_content_value_maps_ten_minutes_to_question_08_option_a() -> None:
    assert map_content_value("question-08", "十来分钟") == {"selected_options": ["A"], "input_value": ""}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m pytest G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\unit\nodes\layer2\test_content_branch.py G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression\test_runtime_regression.py -q`

Expected: FAIL because the current node logic only recognizes age and `question-02` plus a generic time ambiguity fallback.

- [ ] **Step 3: Write the minimal implementation**

```python
QUESTION_HINTS = {
    "question-03": {"time_ranges": [("22:00", "23:15", "B"), ...], "context_tokens": ["自由", "自然", "完全自由安排"]},
    "question-04": {"time_ranges": [("06:00", "07:45", "B"), ...], "context_tokens": ["自由", "自然", "完全自由安排"]},
    "question-08": {"synonyms": {"十来分钟": "A"}},
}


def _extract_multi_units(self, raw_input: str) -> list[dict]:
    # split age / regular schedule / single-choice semantic clauses
    ...


def _fallback(self, content_unit: dict) -> dict:
    if not has_relaxed_context(unit_text):
        return choose_regular_schedule_if_present(...)
    if looks_like_free_wake(unit_text):
        return choose_question_04(...)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m pytest G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\unit\nodes\layer2\test_content_branch.py G:\somni\somni-quiz-ai-main\somni-quiz-ai-main\somni-graph-quiz\tests\regression\test_runtime_regression.py -q`

Expected: PASS for the new understanding, attribution, and semantic mapping tests.

- [ ] **Step 5: Commit**

```bash
git add G:\somni\somni-quiz-ai-main\somni-graph-quiz\src\somni_graph_quiz\nodes\layer2\content G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\unit\nodes\layer2\test_content_branch.py G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression\test_runtime_regression.py
git commit -m "feat: support business9 content attribution regressions"
```

### Task 4: Non-Content View/Modify Regression Coverage

**Files:**
- Modify: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\src\somni_graph_quiz\nodes\layer2\non_content\branch.py`
- Modify: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\src\somni_graph_quiz\nodes\layer3\respond.py`
- Test: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\unit\nodes\layer2\test_non_content_branch.py`
- Test: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\unit\nodes\layer3\test_response_composer.py`
- Test: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression\test_grpc_regression.py`

- [ ] **Step 1: Write failing tests for view-all and implicit modify**

```python
def test_non_content_branch_view_all_returns_answer_records() -> None:
    result = NonContentBranch().run(graph_state_with_answers, TurnInput(...raw_input="查看记录"))
    assert result["response_facts"]["non_content_mode"] == "view"
    assert result["response_facts"]["view_records"]


def test_response_composer_mentions_view_records() -> None:
    message = ResponseComposerNode().run(finalized_view_context)
    assert "记录" in message
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m pytest G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\unit\nodes\layer2\test_non_content_branch.py G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\unit\nodes\layer3\test_response_composer.py G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression\test_grpc_regression.py -q`

Expected: FAIL if the response or control path does not expose the expected view-all semantics.

- [ ] **Step 3: Write the minimal implementation**

```python
if control_action == "view_all":
    return create_branch_result(
        branch_type="non_content",
        response_facts={"non_content_mode": "view", "view_records": list(session_memory["answered_records"].values())},
    )

if turn_outcome == "viewing_records":
    return f"当前已记录：{render_records(...)}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m pytest G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\unit\nodes\layer2\test_non_content_branch.py G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\unit\nodes\layer3\test_response_composer.py G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression\test_grpc_regression.py -q`

Expected: PASS for the control/view regression flow.

- [ ] **Step 5: Commit**

```bash
git add G:\somni\somni-quiz-ai-main\somni-graph-quiz\src\somni_graph_quiz\nodes\layer2\non_content\branch.py G:\somni\somni-quiz-ai-main\somni-graph-quiz\src\somni_graph_quiz\nodes\layer3\respond.py G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\unit\nodes\layer2\test_non_content_branch.py G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\unit\nodes\layer3\test_response_composer.py G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\regression\test_grpc_regression.py
git commit -m "feat: cover non-content record viewing regressions"
```

### Task 5: Online Smoke Alignment and Final Verification

**Files:**
- Modify: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\integration\llm\test_real_provider_smoke.py`
- Modify: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\src\somni_graph_quiz\app\real_llm_check.py`
- Modify: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\README.md`
- Test: `G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\integration\llm\test_real_provider_smoke.py`

- [ ] **Step 1: Write the failing smoke-test expectations**

```python
def test_real_provider_smoke_content_answer_uses_business9_questionnaire(question_catalog: dict) -> None:
    result = engine.run_turn(graph_state, TurnInput(...raw_input="我22岁，每天11点睡觉，7点起床"))
    assert result["answer_record"]["answers"]
    assert result["pending_question"]["question_id"] == "question-03"
```

- [ ] **Step 2: Run smoke tests to verify they fail or skip for the right reason**

Run: `E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m pytest -m llm G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\integration\llm\test_real_provider_smoke.py -q`

Expected: SKIP if `SOMNI_LLM_API_KEY` is missing; otherwise FAIL until the smoke test uses the business9 questionnaire.

- [ ] **Step 3: Write the minimal implementation**

```python
def _business9_catalog() -> dict:
    questionnaire = build_default_questionnaire()
    return map_streamlit_questionnaire_to_catalog(questionnaire)


def run_real_llm_check(settings: GraphQuizSettings | None = None) -> dict[str, object]:
    ...
    response = provider.generate("real_provider_check", "Reply with a very short health check acknowledgement.")
    return {"success": True, "questionnaire": "business9", ...}
```

- [ ] **Step 4: Run the full project verification**

Run: `E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m pytest G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests -q`

Run: `E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m ruff check G:\somni\somni-quiz-ai-main\somni-graph-quiz\src G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests G:\somni\somni-quiz-ai-main\somni-graph-quiz\app.py G:\somni\somni-quiz-ai-main\somni-graph-quiz\scripts\check_real_llm.py`

Expected: PASS for offline suite and lint; online smoke either PASS with configured key or SKIP with the expected missing-key message.

- [ ] **Step 5: Commit**

```bash
git add G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests\integration\llm\test_real_provider_smoke.py G:\somni\somni-quiz-ai-main\somni-graph-quiz\src\somni_graph_quiz\app\real_llm_check.py G:\somni\somni-quiz-ai-main\somni-graph-quiz\README.md
git commit -m "test: align real-provider smoke with business9 questionnaire"
```
