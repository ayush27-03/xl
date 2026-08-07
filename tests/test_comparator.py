"""Tests for the Comparator (M5). The leading property: diff(A, A) is empty."""

from __future__ import annotations

from datetime import datetime

import pytest

from _corpus import FIXTURES
from _helpers import col, dataset
from excel_analysis.adapters.workbook_loader import load_workbook
from excel_analysis.domain.aligner import align
from excel_analysis.domain.comparator import compare
from excel_analysis.domain.detector import detect_tables
from excel_analysis.domain.diagnostics import Diagnostics
from excel_analysis.domain.models import ColumnType
from excel_analysis.domain.normalizer import normalize

N = ColumnType.NUMBER


def _diff(left, right):
    return compare(left, right, align(left, right, Diagnostics()), Diagnostics())


def _is_empty(d) -> bool:
    return (
        not d.columns_added and not d.columns_removed and not d.columns_renamed
        and not d.columns_retyped and not d.column_order_changed
        and d.rows_added == 0 and d.rows_removed == 0 and not d.row_changes
    )


# --- The leading property ---------------------------------------------------


def test_self_diff_is_empty_on_hand_built_dataset():
    ds = dataset([col("ID", [1, 2, 3], N), col("City", ["London", "Paris", "Rome"])])
    assert _is_empty(_diff(ds, ds))


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_self_diff_is_empty_for_every_fixture(corpus, name):
    raw = load_workbook(corpus[name])
    diags = Diagnostics()
    for sheet in raw.sheets:
        for table in detect_tables(sheet, diags):
            ds = normalize(sheet, table, diags)
            assert _is_empty(_diff(ds, ds)), f"{name}: self-diff is not empty"


# --- Type-aware cells -------------------------------------------------------


def test_date_vs_text_date_is_not_a_cell_change():
    left = dataset([col("ID", [1], N), col("DoB", [datetime(1990, 5, 14)], ColumnType.DATE)])
    right = dataset([col("ID", [1], N), col("DoB", ["1990-05-14"], ColumnType.TEXT)])
    d = _diff(left, right)
    assert d.row_changes == ()                       # cell is quiet
    assert any(tc.left == "DoB" for tc in d.columns_retyped)  # but schema notes the retype


def test_number_vs_numeric_text_is_not_a_cell_change():
    left = dataset([col("ID", [1], N), col("Amt", [100], N)])
    right = dataset([col("ID", [1], N), col("Amt", ["100"], ColumnType.TEXT)])
    d = _diff(left, right)
    assert d.row_changes == ()


def test_long_numeric_identifiers_are_categorical_not_a_delta():
    # Premise: these 17-digit ids round to the SAME float.
    assert float("12345678901234567") == float("12345678901234568")
    # A TEXT identifier column: still detected as changed (exact-int canon, no
    # false match), but reported categorically - never a numeric delta.
    left = dataset([col("ID", [1], N), col("Acct", ["12345678901234567"])])
    right = dataset([col("ID", [1], N), col("Acct", ["12345678901234568"])])
    d = _diff(left, right)
    assert len(d.row_changes) == 1
    cell = d.row_changes[0].cells[0]
    assert cell.kind == "categorical" and cell.delta is None


# --- Cell variance ----------------------------------------------------------


def test_numeric_change_reports_delta_and_pct():
    left = dataset([col("ID", [1], N), col("Pay", [100.0], N)])
    right = dataset([col("ID", [1], N), col("Pay", [150.0], N)])
    cell = _diff(left, right).row_changes[0].cells[0]
    assert cell.kind == "numeric"
    assert cell.delta == 50.0 and cell.pct_change == 50.0


def test_categorical_change_reports_before_and_after():
    left = dataset([col("ID", [1], N), col("City", ["London"])])
    right = dataset([col("ID", [1], N), col("City", ["Paris"])])
    cell = _diff(left, right).row_changes[0].cells[0]
    assert cell.kind == "categorical"
    assert (cell.left_value, cell.right_value) == ("London", "Paris")


# --- Schema and row diff ----------------------------------------------------


def test_schema_added_removed_and_renamed():
    left = dataset([col("Employee ID", [1, 2], N), col("DOR", ["x", "y"])])
    right = dataset([col("employee_id", [1, 2], N), col("Reason", ["p", "q"])])
    d = _diff(left, right)
    assert d.columns_removed == ("DOR",)
    assert d.columns_added == ("Reason",)
    assert ("Employee ID", "employee_id") in d.columns_renamed


def test_row_added_removed_and_unchanged_counts():
    left = dataset([col("ID", [1, 2, 3], N)])
    right = dataset([col("ID", [2, 3, 4], N)])
    d = _diff(left, right)
    assert (d.rows_removed, d.rows_added, d.rows_unchanged) == (1, 1, 2)
    assert d.row_changes == ()  # matched rows have no other columns to differ on
