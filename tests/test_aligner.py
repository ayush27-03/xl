"""Tests for the Aligner (M4): column and row correspondence.

The RSU collision is a property, not a comment: a normalized key that maps to
more than one column on either side must never be merged.
"""

from __future__ import annotations

from _helpers import col, dataset
from excel_analysis.domain.aligner import align
from excel_analysis.domain.diagnostics import Diagnostics
from excel_analysis.domain.models import ColumnMatchBasis, ColumnType, RowMatchBasis

N = ColumnType.NUMBER


def _align(left, right):
    diags = Diagnostics()
    return align(left, right, diags), [d.code for d in diags.to_tuple()]


# --- columns ----------------------------------------------------------------


def test_exact_column_matches():
    left = dataset([col("Employee_ID", [1, 2], N), col("Name", ["a", "b"])])
    right = dataset([col("Employee_ID", [1, 2], N), col("Name", ["a", "b"])])
    al, _ = _align(left, right)
    assert {m.left for m in al.column_matches} == {"Employee_ID", "Name"}
    assert all(m.basis is ColumnMatchBasis.EXACT and m.confidence == 1.0 for m in al.column_matches)
    assert al.columns_only_in_left == () and al.columns_only_in_right == ()


def test_normalized_column_match_one_to_one():
    left = dataset([col("Employee ID", [1, 2], N)])
    right = dataset([col("employee_id", [1, 2], N)])
    al, _ = _align(left, right)
    assert len(al.column_matches) == 1
    m = al.column_matches[0]
    assert (m.left, m.right, m.basis) == ("Employee ID", "employee_id", ColumnMatchBasis.NORMALIZED)


def test_normalized_match_never_merges_a_collision():
    # Two left columns normalize alike; one right column shares that key. Exact
    # fails (case), so a naive normalizer would merge one and drop the other.
    left = dataset([col("Net Pay", [1, 2], N), col("Net_Pay", [3, 4], N)])
    right = dataset([col("net pay", [1, 2], N)])
    al, codes = _align(left, right)
    assert al.column_matches == ()  # nothing merged
    assert set(al.columns_only_in_left) == {"Net Pay", "Net_Pay"}
    assert al.columns_only_in_right == ("net pay",)
    assert "ambiguous-column-match" in codes


def test_unmatched_columns_reported_per_side():
    left = dataset([col("Employee_ID", [1, 2], N), col("DOR", ["x", "y"])])
    right = dataset([col("Employee_ID", [1, 2], N), col("Reason", ["p", "q"])])
    al, _ = _align(left, right)
    assert al.columns_only_in_left == ("DOR",)
    assert al.columns_only_in_right == ("Reason",)


# --- rows -------------------------------------------------------------------


def test_keyed_alignment_with_partial_overlap():
    left = dataset([col("Employee_ID", [1, 2, 3], N), col("Name", ["a", "a", "b"])])
    right = dataset([col("Employee_ID", [2, 3, 4], N), col("Name", ["a", "b", "c"])])
    al, _ = _align(left, right)
    assert al.row_basis is RowMatchBasis.KEY
    assert al.row_key == "Employee_ID"
    assert {(m.left_row, m.right_row) for m in al.row_matches} == {(1, 0), (2, 1)}
    assert al.rows_only_in_left == (0,)
    assert al.rows_only_in_right == (2,)
    assert al.row_confidence == 0.5  # Jaccard {2,3} / {1,2,3,4}


def test_overlap_ranking_picks_the_better_key():
    left = dataset([col("Employee_ID", [1, 2, 3], N), col("Alt_ID", [10, 20, 30], N)])
    right = dataset([col("Employee_ID", [1, 2, 3], N), col("Alt_ID", [10, 20, 99], N)])
    al, _ = _align(left, right)
    assert al.row_key == "Employee_ID"  # 1.0 overlap beats Alt_ID's 0.5
    assert al.row_confidence == 1.0


def test_self_alignment_is_identity():
    ds = dataset([col("Employee_ID", [1, 2, 3], N), col("Name", ["a", "b", "c"])])
    al, _ = _align(ds, ds)
    assert al.row_basis is RowMatchBasis.KEY
    assert al.row_confidence == 1.0
    assert [(m.left_row, m.right_row) for m in al.row_matches] == [(0, 0), (1, 1), (2, 2)]
    assert al.rows_only_in_left == () and al.rows_only_in_right == ()
    assert al.columns_only_in_left == () and al.columns_only_in_right == ()


def test_key_normalization_matches_text_number_and_leading_zeros():
    left = dataset([col("Employee_ID", ["01", "2", "003"], ColumnType.TEXT)])
    right = dataset([col("Employee_ID", [1, 2, 3], N)])
    al, _ = _align(left, right)
    assert al.row_basis is RowMatchBasis.KEY
    assert al.row_confidence == 1.0
    assert len(al.row_matches) == 3


def test_positional_fallback_when_no_unique_key():
    left = dataset([col("Group", ["x", "x"]), col("Val", [1, 1], N)])
    right = dataset([col("Group", ["x", "x"]), col("Val", [1, 1], N)])
    al, codes = _align(left, right)
    assert al.row_basis is RowMatchBasis.POSITION
    assert [(m.left_row, m.right_row) for m in al.row_matches] == [(0, 0), (1, 1)]
    assert al.row_confidence == 0.3
    assert "row-positional" in codes


def test_keyed_disjoint_keys_match_nothing():
    left = dataset([col("Employee_ID", [1, 2], N)])
    right = dataset([col("Employee_ID", [3, 4], N)])
    al, codes = _align(left, right)
    assert al.row_basis is RowMatchBasis.KEY
    assert al.row_matches == ()
    assert al.rows_only_in_left == (0, 1) and al.rows_only_in_right == (0, 1)
    assert al.row_confidence == 0.0
    assert "row-key" in codes


def test_not_comparable_when_no_shared_columns():
    left = dataset([col("A", [1, 2], N)])
    right = dataset([col("B", [1, 2], N)])
    al, codes = _align(left, right)
    assert al.row_basis is RowMatchBasis.NONE
    assert al.column_matches == ()
    assert al.rows_only_in_left == (0, 1) and al.rows_only_in_right == (0, 1)
    assert "not-comparable" in codes
