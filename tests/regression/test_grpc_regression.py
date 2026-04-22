"""Structured gRPC regression cases."""

from pathlib import Path

import pytest

from tests.regression.fixtures.regression_support import (
    REGRESSION_ROOT,
    assert_grpc_expectations,
    execute_grpc_case,
    load_case,
)


CASE_DIR = REGRESSION_ROOT / "grpc"


@pytest.mark.parametrize(
    "case_path",
    sorted(CASE_DIR.glob("*.json")),
    ids=lambda path: path.stem,
)
def test_grpc_regression_cases(case_path: Path) -> None:
    case = load_case(case_path)

    response = execute_grpc_case(case)

    assert_grpc_expectations(response, case["expected"])
