"""Domain models — the contract spine shared across every pipeline stage.

These are plain dataclasses. They carry no behaviour and import no I/O library:
openpyxl, pandas, argparse, and json all stay out of this module (CLAUDE.md
rule 2). Stages communicate *only* through the types defined here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Raw layer — produced by the WorkbookLoader adapter. Faithful to the file,
# uninterpreted. All row/col indices in the domain are 0-based.
# ---------------------------------------------------------------------------


class CellType(str, Enum):
    EMPTY = "empty"
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    BOOL = "bool"
    ERROR = "error"


@dataclass(frozen=True)
class RawCell:
    value: Any
    type: CellType


@dataclass(frozen=True)
class MergedRange:
    first_row: int
    last_row: int
    first_col: int
    last_col: int

    def contains(self, row: int, col: int) -> bool:
        return (
            self.first_row <= row <= self.last_row
            and self.first_col <= col <= self.last_col
        )


@dataclass(frozen=True)
class RawSheetGrid:
    name: str
    hidden: bool
    n_rows: int
    n_cols: int
    cells: tuple[tuple[RawCell, ...], ...]  # rectangular, indexed [row][col]
    merged_ranges: tuple[MergedRange, ...]


@dataclass(frozen=True)
class RawWorkbook:
    path: str
    sheets: tuple[RawSheetGrid, ...]


# ---------------------------------------------------------------------------
# Detection layer — produced by the TableDetector.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CellRange:
    first_row: int
    last_row: int
    first_col: int
    last_col: int

    @property
    def n_rows(self) -> int:
        return self.last_row - self.first_row + 1

    @property
    def n_cols(self) -> int:
        return self.last_col - self.first_col + 1


@dataclass(frozen=True)
class DetectedTable:
    sheet_name: str
    table_index: int            # 0-based ordinal within the sheet
    region: CellRange           # full table region, including the header row
    header_row: int             # absolute 0-based index of the chosen header
    confidence: float           # 0..1 confidence in the header choice
    signals: dict[str, float]   # named signals behind the score (for audit)


# ---------------------------------------------------------------------------
# Normalized layer — the Dataset contract. THE hard boundary (CLAUDE.md rule 1).
# Nothing above this leaks down; nothing below it looks back at a raw cell.
# ---------------------------------------------------------------------------


class ColumnType(str, Enum):
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    BOOL = "bool"
    MIXED = "mixed"
    EMPTY = "empty"


@dataclass(frozen=True)
class ColumnProvenance:
    sheet_name: str
    source_column: int   # absolute 0-based column in the source sheet
    header_cell: str     # A1 reference of the header cell, e.g. "B3"


@dataclass(frozen=True)
class Column:
    name: str
    type: ColumnType
    values: tuple[Any, ...]
    provenance: ColumnProvenance


@dataclass(frozen=True)
class DatasetProvenance:
    sheet_name: str
    region_ref: str      # A1-style range, e.g. "A3:D12"
    header_row: int      # absolute 0-based


@dataclass(frozen=True)
class Dataset:
    """The single most important contract in the system (CLAUDE.md rule 1)."""

    name: str
    columns: tuple[Column, ...]
    n_rows: int
    provenance: DatasetProvenance


# ---------------------------------------------------------------------------
# Profile layer — produced by the Profiler.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ColumnProfile:
    name: str
    type: ColumnType
    count: int
    null_count: int
    non_null_count: int
    unique_count: int
    stats: dict[str, Any]   # type-specific extras (min/max/mean/...)


@dataclass(frozen=True)
class DatasetProfile:
    name: str
    n_rows: int
    n_columns: int
    columns: tuple[ColumnProfile, ...]


# ---------------------------------------------------------------------------
# Diagnostics — the audit trail (CLAUDE.md rule 4). Data here; the collector
# that accumulates them lives in diagnostics.py.
# ---------------------------------------------------------------------------


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class Diagnostic:
    severity: Severity
    code: str
    message: str
    location: Optional[str] = None    # e.g. "Sheet1!A3"
    confidence: Optional[float] = None


# ---------------------------------------------------------------------------
# Slice-level aggregate — the output of this vertical slice.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TableAnalysis:
    detected: DetectedTable
    profile: DatasetProfile


@dataclass(frozen=True)
class WorkbookAnalysis:
    source_path: str
    tables: tuple[TableAnalysis, ...]
    diagnostics: tuple[Diagnostic, ...]


# ---------------------------------------------------------------------------
# Cell-reference helpers (pure). Kept here so any domain stage can build
# human-readable A1 provenance without a separate utility import.
# ---------------------------------------------------------------------------


def column_letter(index0: int) -> str:
    """0-based column index -> Excel letters (0 -> 'A', 26 -> 'AA')."""
    n = index0 + 1
    letters = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def a1(row0: int, col0: int) -> str:
    return f"{column_letter(col0)}{row0 + 1}"


def range_ref(region: CellRange) -> str:
    return (
        f"{a1(region.first_row, region.first_col)}:"
        f"{a1(region.last_row, region.last_col)}"
    )
