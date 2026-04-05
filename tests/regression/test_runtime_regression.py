"""Structured runtime regression cases."""

from pathlib import Path

import pytest

from tests.regression.fixtures.regression_support import (
    REGRESSION_ROOT,
    assert_runtime_expectations,
    execute_runtime_case,
    load_case,
    runtime_question_catalog,
)


CASE_DIR = REGRESSION_ROOT / "content_cases"


@pytest.mark.parametrize(
    "case_path",
    sorted(CASE_DIR.glob("*.json")),
    ids=lambda path: path.stem,
)
def test_runtime_regression_cases(case_path: Path) -> None:
    case = load_case(case_path)

    graph_state, turn_results = execute_runtime_case(case)

    assert_runtime_expectations(graph_state, turn_results, case["expected"])


def test_runtime_question_catalog_uses_business9_titles() -> None:
    catalog = runtime_question_catalog()

    assert catalog["question_order"][-1] == "question-09"
    assert catalog["question_index"]["question-08"]["title"] == "半夜醒来后，再次入睡困难吗？"
