"""Tests for the comparison orchestration and AnalysisResult contract (M6)."""

from __future__ import annotations

from excel_analysis.adapters.workbook_loader import load_workbook
from excel_analysis.app.pipeline import compare_workbooks


def test_compare_workbooks_populates_the_full_contract(compare_pair):
    left = load_workbook(compare_pair["compare_left"])
    right = load_workbook(compare_pair["compare_right"])
    result = compare_workbooks(left, right)
    d = result.diff

    # alignment provenance
    assert d.row_basis.value == "key" and d.row_key == "Emp_ID"

    # schema diff
    assert d.columns_removed == ("ExitReason",)
    assert d.columns_added == ("Bonus",)
    assert {m.left for m in d.columns_matched} == {"Emp_ID", "Name", "Salary", "City", "DoB"}
    assert any(
        t.left == "DoB" and t.left_type.value == "date" and t.right_type.value == "text"
        for t in d.columns_retyped
    )

    # row diff
    assert (d.rows_added, d.rows_removed, d.rows_unchanged, len(d.row_changes)) == (1, 1, 1, 2)

    # cell variance: Salary numeric change on emp 2; DoB quiet (type-aware)
    salary = [c for rc in d.row_changes for c in rc.cells if c.column == "Salary"]
    assert salary and salary[0].kind == "numeric" and salary[0].delta == 20.0
    assert [c for rc in d.row_changes for c in rc.cells if c.column == "DoB"] == []

    # warnings carry the retype; insights reserved; profiles present
    assert any(w.code == "column-retyped" for w in result.warnings)
    assert result.insights == ()
    assert (result.left_profile.n_columns, result.right_profile.n_columns) == (6, 6)
