"""Shared test helpers: build domain objects directly, no files needed."""

from __future__ import annotations

from excel_analysis.adapters.workbook_loader import _to_raw_cell
from excel_analysis.domain.models import (
    Column,
    ColumnProvenance,
    ColumnType,
    Dataset,
    DatasetProvenance,
    RawSheetGrid,
    RawWorkbook,
)


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


def col(name, values, ctype=ColumnType.TEXT):
    """Build a Dataset Column directly from a list of values."""
    return Column(
        name=name, type=ctype, values=tuple(values),
        provenance=ColumnProvenance(sheet_name="S", source_column=0, header_cell="A1"),
    )


def dataset(columns, name="S!A1:A9"):
    n = len(columns[0].values) if columns else 0
    return Dataset(
        name=name, columns=tuple(columns), n_rows=n,
        provenance=DatasetProvenance(sheet_name="S", region_ref="A1:A9", header_row=0),
    )
