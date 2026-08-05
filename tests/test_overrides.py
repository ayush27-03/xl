"""Tests for detection overrides (M2, auto-first posture)."""

from __future__ import annotations

from _helpers import make_grid, make_workbook
from excel_analysis.app.pipeline import analyze
from excel_analysis.domain.config import DEFAULT_CONFIG, Override


def _codes(result):
    return [d.code for d in result.diagnostics]


def test_forced_header_is_obeyed_over_the_heuristic():
    # Auto-detect prefers the "Region" row (index 1); the user forces the title
    # row (index 0). The override must win, with a user-override diagnostic.
    grid = make_grid(
        [
            ["Title", None, None],
            ["Region", "Units", "Rev"],
            ["North", 1, 2.0],
            ["South", 3, 4.0],
        ],
        name="S",
    )
    wb = make_workbook([grid])
    cfg = DEFAULT_CONFIG.with_override(Override(sheet="S", header_row=0))
    result = analyze(wb, cfg)
    assert result.tables[0].detected.header_row == 0
    assert "user-override" in _codes(result)


def test_auto_detection_disagrees_with_the_forced_choice():
    # Sanity check that without the override, auto-detect picks a different row.
    grid = make_grid(
        [
            ["Title", None, None],
            ["Region", "Units", "Rev"],
            ["North", 1, 2.0],
            ["South", 3, 4.0],
        ],
        name="S",
    )
    result = analyze(make_workbook([grid]), DEFAULT_CONFIG)
    assert result.tables[0].detected.header_row == 1  # the "Region" row


def test_invalid_override_degrades_to_auto_detection():
    grid = make_grid([["Region", "Units"], ["North", 1], ["South", 2]], name="S")
    cfg = DEFAULT_CONFIG.with_override(Override(sheet="S", header_row=99))
    result = analyze(make_workbook([grid]), cfg)
    assert "invalid-override" in _codes(result)
    assert result.tables[0].detected.header_row == 0  # auto still produced a table


def test_sheet_restriction_limits_analysis():
    alpha = make_grid([["A"], ["1"]], name="Alpha")
    beta = make_grid([["B"], ["2"]], name="Beta")
    cfg = DEFAULT_CONFIG.with_override(Override(sheet="Beta"))
    result = analyze(make_workbook([alpha, beta]), cfg)
    assert {t.detected.sheet_name for t in result.tables} == {"Beta"}


def test_override_sheet_not_found_warns_and_analyzes_nothing():
    alpha = make_grid([["A"], ["1"]], name="Alpha")
    cfg = DEFAULT_CONFIG.with_override(Override(sheet="Ghost"))
    result = analyze(make_workbook([alpha]), cfg)
    assert result.tables == ()
    assert "override-sheet-not-found" in _codes(result)
