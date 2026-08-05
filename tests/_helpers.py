"""Shared test helpers: build domain objects directly, no files needed."""

from __future__ import annotations

from excel_analysis.adapters.workbook_loader import _to_raw_cell
from excel_analysis.domain.models import RawSheetGrid, RawWorkbook


def make_grid(rows, name="S", hidden=False, merges=()):
    """Build a RawSheetGrid from a 2D list of Python values."""
    n_cols = max((len(r) for r in rows), default=0)
    cells = tuple(
        tuple(_to_raw_cell(r[c] if c < len(r) else None) for c in range(n_cols))
        for r in rows
    )
    return RawSheetGrid(
        name=name, hidden=hidden, n_rows=len(rows), n_cols=n_cols,
        cells=cells, merged_ranges=tuple(merges),
    )


def make_workbook(sheets, path="mem.xlsx"):
    return RawWorkbook(path=path, sheets=tuple(sheets))
