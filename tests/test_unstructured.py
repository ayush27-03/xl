"""Tests for unstructured-region handling (M3): free text is reported, not
profiled — unless the user explicitly selects it."""

from __future__ import annotations

from _helpers import make_grid, make_workbook
from excel_analysis.app.pipeline import analyze
from excel_analysis.domain.config import DEFAULT_CONFIG, TableSelection
from excel_analysis.domain.models import CellRange

_PROSE = [
    ["Internal draft - do not distribute"],
    ["Reviewed by finance on Tuesday"],
    ["Pending approval from the director"],
]


def _codes(result):
    return [d.code for d in result.diagnostics]


def test_prose_column_is_reported_not_profiled():
    result = analyze(make_workbook([make_grid(_PROSE, name="Notes")]), DEFAULT_CONFIG)
    assert result.tables == ()
    assert "unstructured-region" in _codes(result)


def test_single_word_column_stays_a_table():
    grid = make_grid([["Fruit"], ["Apple"], ["Banana"]], name="S")
    result = analyze(make_workbook([grid]), DEFAULT_CONFIG)
    assert len(result.tables) == 1
    assert "unstructured-region" not in _codes(result)


def test_user_selection_profiles_prose_anyway():
    # A pinned region is authoritative — it overrides the unstructured cut.
    cfg = DEFAULT_CONFIG.with_selections(
        [TableSelection(sheet="Notes", region=CellRange(0, 2, 0, 0))]
    )
    result = analyze(make_workbook([make_grid(_PROSE, name="Notes")]), cfg)
    assert len(result.tables) == 1
    assert "unstructured-region" not in _codes(result)


def test_threshold_controls_prose_sensitivity():
    grid = make_grid(_PROSE, name="Notes")
    # Raise the bar above the average words/cell -> no longer treated as prose.
    lenient = DEFAULT_CONFIG.with_overrides({"unstructured_min_words": 20})
    result = analyze(make_workbook([grid]), lenient)
    assert "unstructured-region" not in _codes(result)
    assert len(result.tables) == 1
