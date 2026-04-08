# somni-graph-quiz

Independent graph-based conversational quiz runtime with:

- graph runtime for dynamic questionnaire flow
- gRPC adapter with original request/response shape preserved
- standalone Streamlit app
- vendored proto/generated files for independent operation
- Doubao/OpenAI-compatible remote LLM wiring with rule fallback
- targeted clarification for unresolved answers and partial follow-up
- direct single-choice and time-range closure during content understanding when the answer is already identifiable

## Recent Behavior Notes

- `TurnClassifyNode` now consumes both short-term memory and an enhanced question catalog summary, so obvious questionnaire answers are less likely to be misrouted as chat or pullback.
- `ContentUnderstand` can now directly resolve single-choice answers and normalized time fields when one question forms a valid closure, instead of always deferring that work to later stages.
- Clarification responses are now scoped to the identified question whenever possible, so the assistant asks about the specific unresolved question instead of issuing a generic retry prompt.
- Completion responses are generated from the updated answer record, allowing a fuller closing summary without inventing information.

## Setup

Use Python 3.11 and install the project in your environment.

```bash
python -m pip install -e .
```

Configure `.env` from `.env.example`:

```env
SOMNI_LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
SOMNI_LLM_API_KEY=your_api_key_here
SOMNI_LLM_MODEL=
SOMNI_LLM_TEMPERATURE=0.2
SOMNI_LLM_TIMEOUT=30
SOMNI_LLM_REASONING_EFFORT=minimal
SOMNI_GRPC_HOST=0.0.0.0
SOMNI_GRPC_PORT=18000
```

If LLM config is missing, the runtime falls back to rule-based behavior.

You can also fill or update the same settings from the standalone Streamlit sidebar.
The app writes them back into the local `.env` and refreshes the current session runtime.

## Run Streamlit

```bash
streamlit run app.py
```

## Run gRPC Server

```bash
python -m somni_graph_quiz.adapters.grpc
```

The default repository deployment target is port `18000`.

## Test

```bash
python -m pytest tests -q
python -m pytest -m llm tests -q
python -m ruff check src tests app.py
python scripts/check_real_llm.py
```

## Online LLM Smoke Test

This is optional and requires valid `SOMNI_LLM_*` configuration. The smoke flow uses the bundled
business9 questionnaire asset at `data/streamlit_dynamic_questionnaire.json`.

```bash
python -m pytest -m llm tests -q
```

If `SOMNI_LLM_BASE_URL`, `SOMNI_LLM_API_KEY`, or `SOMNI_LLM_MODEL` is missing, the online smoke
tests will be skipped.

## Explicit Real-Provider Check

Use this when you want a direct connectivity and response diagnostic without running the full test suite:

```bash
python scripts/check_real_llm.py
```

The script prints structured JSON with:

- whether configuration is complete
- which `SOMNI_LLM_*` keys are missing
- whether a real request succeeded
- provider model name
- latency and error summary
