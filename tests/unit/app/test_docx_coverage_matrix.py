"""Tests for the DOCX regression coverage matrix."""

from pathlib import Path


def test_docx_coverage_matrix_lists_both_documents_and_new_cases() -> None:
    coverage_path = (
        Path(__file__).resolve().parents[3]
        / "docs"
        / "superpowers"
        / "regression-docx-coverage.md"
    )

    content = coverage_path.read_text(encoding="utf-8")

    assert "测试结果 .docx" in content
    assert "测试报告 .docx" in content
    assert "runtime_docx_modify_free_wake_answered" in content
    assert "runtime_docx_modify_to_ten_oclock" in content
