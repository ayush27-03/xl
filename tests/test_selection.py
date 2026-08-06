"""Tests for region selection and multi-source ingestion (M3)."""

from __future__ import annotations

from _helpers import make_grid, make_workbook
from excel_analysis.app.pipeline import analyze, analyze_sources
from excel_analysis.domain.config import DEFAULT_CONFIG, TableSelection
from excel_analysis.domain.models import CellRange


def _codes(result):
    return [d.code for d in result.diagnostics]


def test_region_selection_forces_a_table():
    grid = make_grid(
        [
            ["junk", None],
            ["ID", "Val"],
            [1, 10],
            [2, 20],
        ],
        name="S",
    )
    # Select A2:B4 -> rows 1..3, cols 0..1; header is the region's first row.
    sel = TableSelection(sheet="S", region=CellRange(1, 3, 0, 1))
    result = analyze(make_workbook([grid]), DEFAULT_CONFIG.with_selections([sel]))
    detected = result.tables[0].detected
    assert detected.header_row == 1
    assert (detected.region.first_col, detected.region.last_col) == (0, 1)
    assert [c.name for c in result.tables[0].profile.columns] == ["ID", "Val"]
    assert "user-selection" in _codes(result)


def test_multiple_selections_profile_n_tables():
    s1 = make_grid([["A", "B"], ["North", 1], ["South", 2]], name="S1")
    s2 = make_grid([["X", "Y"], ["East", 3]], name="S2")
    cfg = DEFAULT_CONFIG.with_selections(
        [TableSelection(sheet="S1"), TableSelection(sheet="S2")]
    )
    result = analyze(make_workbook([s1, s2]), cfg)
    assert {t.detected.sheet_name for t in result.tables} == {"S1", "S2"}


def test_multi_source_report_preserves_order_and_paths():
    wb1 = make_workbook([make_grid([["A", "B"], ["x", 1]], name="Sheet1")], path="one.xlsx")
    wb2 = make_workbook([make_grid([["C", "D"], ["y", 2]], name="Sheet1")], path="two.xlsx")
    report = analyze_sources([wb1, wb2], DEFAULT_CONFIG)
    assert len(report.sources) == 2
    assert [s.source_path for s in report.sources] == ["one.xlsx", "two.xlsx"]
    assert report.sources[0].tables[0].profile.columns[0].name == "A"
    assert report.sources[1].tables[0].profile.columns[0].name == "C"


def test_selection_scoped_to_one_source_leaves_others_auto():
    s0 = make_grid([["A", "B"], ["x", 1], ["y", 2]], name="Data")
    s1 = make_grid([["p", "q"], ["m", 9], ["n", 8]], name="Data")
    wb0 = make_workbook([s0], path="zero.xlsx")
    wb1 = make_workbook([s1], path="one.xlsx")
    # Pin header row 2 (0-based 1) only on source 1.
    cfg = DEFAULT_CONFIG.with_selections(
        [TableSelection(sheet="Data", header_row=1, source=1)]
    )
    report = analyze_sources([wb0, wb1], cfg)
    assert report.sources[0].tables[0].detected.header_row == 0  # source 0: auto
    assert report.sources[1].tables[0].detected.header_row == 1  # source 1: forced
    assert "user-override" in [d.code for d in report.sources[1].diagnostics]
