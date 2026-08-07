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
    assert (d.rows_added, d.rows_removed, d.rows_unchanged, len(d.row_changes)) == (1, 1, 0, 3)

    # cell variance: Salary changed in every matched row (systematic), one is +20
    salary = [c for rc in d.row_changes for c in rc.cells if c.column == "Salary"]
    assert len(salary) == 3 and all(c.kind == "numeric" for c in salary)
    assert any(c.delta == 20.0 for c in salary)
    # DoB is type-aware quiet for the 2 aligned rows; exactly 1 genuinely differs
    assert len([c for rc in d.row_changes for c in rc.cells if c.column == "DoB"]) == 1

    # warnings carry the retype; insights populated (M7); profiles present
    assert any(w.code == "column-retyped" for w in result.warnings)
    assert result.insights  # ranked insights fill the slot
    assert (result.left_profile.n_columns, result.right_profile.n_columns) == (6, 6)
