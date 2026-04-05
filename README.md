# somni-graph-quiz

Independent graph-based conversational quiz runtime with:

- graph runtime for dynamic questionnaire flow
- gRPC adapter with original request/response shape preserved
- standalone Streamlit app
- vendored proto/generated files for independent operation
- Doubao/OpenAI-compatible remote LLM wiring with rule fallback

## Setup

Use Python 3.11 and install the project in your environment.

Example with the existing conda env:

```bash
E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m pip install -e G:\somni\somni-quiz-ai-main\somni-graph-quiz
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
SOMNI_GRPC_PORT=19000
```

If LLM config is missing, the runtime falls back to rule-based behavior.

You can also fill or update the same settings from the standalone Streamlit sidebar.
The app writes them back into the local `.env` and refreshes the current session runtime.

## Run Streamlit

```bash
E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai streamlit run G:\somni\somni-quiz-ai-main\somni-graph-quiz\app.py
```

## Run gRPC Server

```bash
E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m somni_graph_quiz.adapters.grpc
```

## Test

```bash
E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m pytest G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests -q
E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m ruff check G:\somni\somni-quiz-ai-main\somni-graph-quiz\src G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests G:\somni\somni-quiz-ai-main\somni-graph-quiz\app.py
```

## Online LLM Smoke Test

This is optional and requires valid `SOMNI_LLM_*` configuration. The smoke flow uses the bundled
business9 questionnaire asset at `data/streamlit_dynamic_questionnaire.json`.

```bash
E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python -m pytest -m llm G:\somni\somni-quiz-ai-main\somni-graph-quiz\tests -q
```

If `SOMNI_LLM_BASE_URL`, `SOMNI_LLM_API_KEY`, or `SOMNI_LLM_MODEL` is missing, the online smoke
tests will be skipped.

## Explicit Real-Provider Check

Use this when you want a direct connectivity and response diagnostic without running the full test suite:

```bash
E:\Anaconda\Scripts\conda.exe run -n somni-quiz-ai python G:\somni\somni-quiz-ai-main\somni-graph-quiz\scripts\check_real_llm.py
```

The script prints structured JSON with:

- whether configuration is complete
- which `SOMNI_LLM_*` keys are missing
- whether a real request succeeded
- provider model name
- latency and error summary
