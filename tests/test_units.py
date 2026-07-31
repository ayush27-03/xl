"""Unit tests for the pure domain logic (no files needed)."""

from __future__ import annotations

from excel_analysis.adapters.workbook_loader import _to_raw_cell
from excel_analysis.domain.detector import _row_blocks, score_header_row
from excel_analysis.domain.diagnostics import Diagnostics
from excel_analysis.domain.models import (
    Column,
    ColumnProvenance,
    ColumnType,
    Dataset,
    DatasetProvenance,
    RawSheetGrid,
)
from excel_analysis.domain.normalizer import _canonical_names, _infer_type
from excel_analysis.domain.profiler import _most_common, profile_dataset


def make_grid(rows, name="S", hidden=False):
    n_cols = max((len(r) for r in rows), default=0)
    cells = tuple(
        tuple(_to_raw_cell(r[c] if c < len(r) else None) for c in range(n_cols))
        for r in rows
    )
    return RawSheetGrid(
        name=name, hidden=hidden, n_rows=len(rows), n_cols=n_cols,
        cells=cells, merged_ranges=(),
    )


# --- detector ---------------------------------------------------------------


def test_header_scoring_prefers_text_row_over_data_row():
    g = make_grid([["Name", "Age"], ["Alice", 30], ["Bob", 25]])
    header_score, _ = score_header_row(g, 0, 1, 0, 1)
    data_score, _ = score_header_row(g, 1, 2, 0, 1)
    assert header_score > data_score
    assert 0.0 <= header_score <= 1.0


def test_row_blocks_split_on_blank_rows():
    g = make_grid([["a"], [None], ["b"], ["c"]])
    assert _row_blocks(g) == [(0, 0), (2, 3)]


# --- normalizer -------------------------------------------------------------


def test_infer_type_homogeneous_number():
    assert _infer_type((1, 2, 3), Diagnostics(), "S", "c") == ColumnType.NUMBER


def test_infer_type_mixed_is_flagged_not_coerced():
    diag = Diagnostics()
    assert _infer_type((1, "x", 2), diag, "S", "c") == ColumnType.MIXED
    assert any(d.code == "mixed-types" for d in diag.to_tuple())


def test_infer_type_all_null_is_empty():
    assert _infer_type((None, None), Diagnostics(), "S", "c") == ColumnType.EMPTY


def test_canonical_names_dedupe_and_fill_blanks():
    assert _canonical_names(["A", "A", None], Diagnostics(), "S") == ["A", "A_1", "column_3"]


# --- profiler ---------------------------------------------------------------


def test_profiler_number_stats_and_null_count():
    col = Column(
        "x", ColumnType.NUMBER, (1.0, 2.0, None, 3.0), ColumnProvenance("S", 0, "A1")
    )
    ds = Dataset("S!A1:A4", (col,), 4, DatasetProvenance("S", "A1:A4", 0))
    c = profile_dataset(ds).columns[0]
    assert (c.null_count, c.non_null_count, c.unique_count) == (1, 3, 3)
    assert c.stats == {"min": 1.0, "max": 3.0, "mean": 2.0, "sum": 6.0}


def test_most_common_tiebreak_is_deterministic():
    # equal counts -> lexicographically smallest string form wins, regardless of order
    assert _most_common(["b", "a"])["value"] == "a"
    assert _most_common(["a", "b"])["value"] == "a"
