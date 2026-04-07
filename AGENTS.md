# Repository Guidelines

## Project Structure & Module Organization
Core code lives under `src/somni_graph_quiz/`. Keep runtime orchestration in `runtime/`, domain models in `domain/` and `contracts/`, adapter-specific code in `adapters/grpc/` and `adapters/streamlit/`, and prompt-facing LLM helpers in `llm/`. The standalone Streamlit entrypoint is `app.py`; app bootstrap and settings live in `src/somni_graph_quiz/app/`.

Tests mirror the package layout under `tests/` and are split into `unit/`, `integration/`, and `regression/`. Shared regression fixtures live in `tests/regression/fixtures/`, protocol definitions in `proto/`, prompt templates in `prompts/`, and bundled questionnaire data in `data/`. Vendored generated gRPC files live in `src/somni_quiz_ai/grpc/generated/`; treat them as generated artifacts.

## Build, Test, and Development Commands
Use Python 3.11 and install the package in editable mode:

```bash
python -m pip install -e .
```

Run the local app:

```bash
streamlit run app.py
python -m somni_graph_quiz.adapters.grpc
```

Run checks before opening a PR:

```bash
python -m pytest tests -q
python -m pytest -m llm tests -q
python -m ruff check src tests app.py
python scripts/check_real_llm.py
```

The `llm` marker and `check_real_llm.py` require valid `SOMNI_LLM_*` settings in `.env`.

## Coding Style & Naming Conventions
Follow existing Python style: 4-space indentation, type hints on public functions, `snake_case` for modules/functions/tests, `PascalCase` for classes, and short docstrings only where the intent is not obvious. Keep new modules aligned with the current package split instead of creating cross-cutting utility files. Run Ruff before submitting; the repo currently uses Ruff for linting and has per-file ignores for generated gRPC code only.

## Testing Guidelines
Place tests beside the affected layer, for example `tests/unit/runtime/test_finalize.py` or `tests/integration/adapters/grpc/test_service.py`. Name files `test_<subject>.py` and keep regression fixtures descriptive, e.g. `grpc_partial_skip_resume.json`. No hard coverage threshold is configured, so changes should include the narrowest unit coverage possible plus integration or regression coverage when behavior crosses adapters, prompts, or flow state.

## Commit & Pull Request Guidelines
Recent history uses short imperative subjects with underscore-separated wording, such as `refine_time_followup_logic_and_tests`. Keep commit messages focused and scoped to one change. PRs should explain the user-visible behavior change, list verification commands run, link the relevant issue or plan doc, and include screenshots only when Streamlit UI output changed.
