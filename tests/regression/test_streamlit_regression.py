"""Structured Streamlit regression cases."""

from pathlib import Path

import pytest

from tests.regression.fixtures.regression_support import (
    REGRESSION_ROOT,
    assert_streamlit_expectations,
    execute_streamlit_case,
    load_case,
)


CASE_DIR = REGRESSION_ROOT / "streamlit"


@pytest.mark.parametrize(
    "case_path",
    sorted(CASE_DIR.glob("*.json")),
    ids=lambda path: path.stem,
)
def test_streamlit_regression_cases(case_path: Path) -> None:
    case = load_case(case_path)

    view = execute_streamlit_case(case)

    assert_streamlit_expectations(view, case["expected"])
