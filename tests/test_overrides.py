"""Tests for header/sheet selection (M2 overrides, unified into M3 selections)."""

from __future__ import annotations

from _helpers import make_grid, make_workbook
from excel_analysis.app.pipeline import analyze
from excel_analysis.domain.config import DEFAULT_CONFIG, TableSelection

_TITLE_GRID = [
    ["Title", None, None],
    ["Region", "Units", "Rev"],
    ["North", 1, 2.0],
    ["South", 3, 4.0],
]


def _codes(result):
    return [d.code for d in result.diagnostics]


def test_forced_header_is_obeyed_over_the_heuristic():
    # Auto-detect prefers the "Region" row (index 1); pin the title row (index 0).
    cfg = DEFAULT_CONFIG.with_selections([TableSelection(sheet="S", header_row=0)])
    result = analyze(make_workbook([make_grid(_TITLE_GRID, name="S")]), cfg)
    assert result.tables[0].detected.header_row == 0
    assert "user-override" in _codes(result)


def test_auto_detection_disagrees_with_the_forced_choice():
    result = analyze(make_workbook([make_grid(_TITLE_GRID, name="S")]), DEFAULT_CONFIG)
    assert result.tables[0].detected.header_row == 1  # the "Region" row


def test_invalid_override_degrades_to_auto_detection():
    grid = make_grid([["Region", "Units"], ["North", 1], ["South", 2]], name="S")
    cfg = DEFAULT_CONFIG.with_selections([TableSelection(sheet="S", header_row=99)])
    result = analyze(make_workbook([grid]), cfg)
    assert "invalid-override" in _codes(result)
    assert result.tables[0].detected.header_row == 0  # auto still produced a table


def test_sheet_restriction_limits_analysis():
    alpha = make_grid([["A"], ["one"]], name="Alpha")
    beta = make_grid([["B"], ["two"]], name="Beta")
    cfg = DEFAULT_CONFIG.with_selections([TableSelection(sheet="Beta")])
    result = analyze(make_workbook([alpha, beta]), cfg)
    assert {t.detected.sheet_name for t in result.tables} == {"Beta"}


def test_selection_sheet_not_found_warns_and_analyzes_nothing():
    alpha = make_grid([["A"], ["one"]], name="Alpha")
    cfg = DEFAULT_CONFIG.with_selections([TableSelection(sheet="Ghost")])
    result = analyze(make_workbook([alpha]), cfg)
    assert result.tables == ()
    assert "selection-sheet-not-found" in _codes(result)
