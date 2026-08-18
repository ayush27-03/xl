"""Domain models — the contract spine shared across every pipeline stage.

These are plain dataclasses. They carry no behaviour and import no I/O library:
openpyxl, pandas, argparse, and json all stay out of this module (CLAUDE.md
rule 2). Stages communicate *only* through the types defined here.
"""

from __future__ import annotations

import re
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
# Alignment layer — produced by the Aligner. How two Datasets correspond,
# column-to-column and row-to-row, with the basis and a confidence (rule 4).
# ---------------------------------------------------------------------------


class ColumnMatchBasis(str, Enum):
    EXACT = "exact"
    NORMALIZED = "normalized"


class RowMatchBasis(str, Enum):
    KEY = "key"
    POSITION = "position"
    NONE = "none"


@dataclass(frozen=True)
class ColumnMatch:
    left: str            # column name in the left Dataset
    right: str           # column name in the right Dataset
    basis: ColumnMatchBasis
    confidence: float


@dataclass(frozen=True)
class RowMatch:
    left_row: int        # 0-based row index into the left Dataset
    right_row: int       # 0-based row index into the right Dataset
    key: Optional[str] = None   # normalized key value when matched by key


@dataclass(frozen=True)
class Alignment:
    column_matches: tuple[ColumnMatch, ...]
    columns_only_in_left: tuple[str, ...]
    columns_only_in_right: tuple[str, ...]
    row_basis: RowMatchBasis
    row_key: Optional[str]          # key column name when row_basis is KEY
    row_confidence: float
    row_matches: tuple[RowMatch, ...]
    rows_only_in_left: tuple[int, ...]
    rows_only_in_right: tuple[int, ...]


# ---------------------------------------------------------------------------
# Diff layer — produced by the Comparator from two Datasets + an Alignment.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ColumnTypeChange:
    left: str
    right: str
    left_type: ColumnType
    right_type: ColumnType


@dataclass(frozen=True)
class CellChange:
    column: str                      # left (canonical) column name
    left_value: Any
    right_value: Any
    kind: str                        # "numeric" | "categorical" | "added" | "removed"
    delta: Optional[float] = None    # numeric only: right - left
    pct_change: Optional[float] = None  # numeric only: delta / left * 100


@dataclass(frozen=True)
class RowChange:
    key: Optional[str]               # row key value (None when positional)
    left_row: int
    right_row: int
    cells: tuple[CellChange, ...]


@dataclass(frozen=True)
class DiffResult:
    # schema
    columns_matched: tuple[ColumnMatch, ...]
    columns_added: tuple[str, ...]
    columns_removed: tuple[str, ...]
    columns_renamed: tuple[tuple[str, str], ...]
    columns_retyped: tuple[ColumnTypeChange, ...]
    column_order_changed: bool
    # rows
    rows_added: int
    rows_removed: int
    rows_unchanged: int
    row_changes: tuple[RowChange, ...]
    # provenance of the row correspondence (carried from the Alignment)
    row_basis: RowMatchBasis
    row_key: Optional[str]
    row_confidence: float


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


@dataclass(frozen=True)
class AnalysisReport:
    """Multiple workbooks profiled together (M3 multi-source ingestion)."""

    sources: tuple[WorkbookAnalysis, ...]


class InsightSeverity(str, Enum):
    INTEGRITY = "integrity"     # data-integrity defects — ranked highest
    STRUCTURAL = "structural"   # schema / roster changes
    VARIANCE = "variance"       # routine value changes
    INFO = "info"


@dataclass(frozen=True)
class Insight:
    """A ranked, human-readable observation that RESTATES facts already in the
    diff — it never computes a new number. `evidence` lists the facts it draws
    on, for traceability."""

    code: str
    severity: InsightSeverity
    message: str
    evidence: tuple[str, ...]


# ---------------------------------------------------------------------------
# Reconciliation layer (M11) — the payroll-portal sign-off contract. Pure and
# deterministic: walks Period-A total to Period-B total through mutually
# exclusive buckets that tie out to the rupee (see architecture.md addendum).
# Produced by the Reconciliation analyzer from two Datasets + an Alignment.
# ---------------------------------------------------------------------------


class ColumnRole(str, Enum):
    """Structural payroll role of a normalized column, derived from the file's
    own layout (subtotal anchors + position), never from a name guess."""

    IDENTITY = "identity"        # id / name / org attrs / dates / bank — context
    ATTENDANCE = "attendance"    # numeric-but-not-pay (days worked, LOP, ...)
    COMPONENT = "component"      # an atomic pay component (earning/ded/reimb)
    SUBTOTAL = "subtotal"        # a stored total (gross/net/statutory)
    OTHER = "other"


class PayCategory(str, Enum):
    EARNING = "earning"
    DEDUCTION = "deduction"
    REIMBURSEMENT = "reimbursement"
    NONE = "none"


@dataclass(frozen=True)
class ColumnClassification:
    """Authoritative column→role/category map, computed once in Python so the
    SPA groups components consistently. `confidence` < 1 flags a block whose
    components did not sum to their stored subtotal."""

    column: str
    role: ColumnRole
    category: PayCategory
    confidence: float = 1.0


@dataclass(frozen=True)
class BucketFlow:
    """One mutually-exclusive step of the reconciliation bridge. `amount` is the
    signed contribution to the headline delta (leavers are negative)."""

    label: str
    count: int
    amount: float


@dataclass(frozen=True)
class CategoryFlow:
    """Retained-population movement of one pay category, taken from its stored
    subtotal column. `amount` is signed (deductions reduce net)."""

    category: PayCategory
    subtotal_column: Optional[str]
    amount: float


@dataclass(frozen=True)
class ReconciliationResult:
    """Deterministic Net-Payable (default) reconciliation. The three population
    buckets always satisfy `delta == joiners.amount + leavers.amount +
    retained.amount` by construction; the retained bucket further splits into
    ring-fenced compensation-cost vs reimbursement/recovery movement plus an
    explicit residual. `comparable` is False when no numeric anchor is shared —
    a first-class outcome, never a crash (CLAUDE.md rule 5)."""

    comparable: bool
    anchor: Optional[str]                 # total column actually used
    anchor_requested: str                 # what the caller asked for
    anchor_substituted: bool              # True if a fallback anchor was used
    key_column: Optional[str]             # alignment key (Employee_ID, ...)
    total_left: float
    total_right: float
    delta: float
    joiners: BucketFlow
    leavers: BucketFlow
    retained: BucketFlow
    retained_compensation_delta: float    # ring-fenced: ΔNet Pay over retained
    retained_reimbursement_delta: float   # ring-fenced: ΔGross Reimbursement
    retained_residual: float              # retained − (compensation + reimb)
    category_flows: tuple[CategoryFlow, ...]
    classification: tuple[ColumnClassification, ...]
    diagnostics: tuple[Diagnostic, ...] = ()  # reconciliation-scoped audit trail


@dataclass(frozen=True)
class AnalysisResult:
    """The comparison contract a renderer/dashboard consumes. Carries everything
    needed to draw the comparison without recomputing anything: both profiles,
    the full diff (schema + rows + cells + alignment provenance), the warnings,
    and ranked insights (M7).

    M11 additively carries the two normalized `Dataset`s (so the portal can build
    the roster, Employee 360, demographics and distributions without a second
    request) and the `ReconciliationResult`. Both default to None so every
    existing constructor and golden file is unaffected."""

    left_profile: DatasetProfile
    right_profile: DatasetProfile
    diff: DiffResult
    warnings: tuple[Diagnostic, ...]
    insights: tuple[Insight, ...] = ()
    left_dataset: Optional["Dataset"] = None
    right_dataset: Optional["Dataset"] = None
    reconciliation: Optional["ReconciliationResult"] = None


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


_A1_RE = re.compile(r"^([A-Za-z]+)([0-9]+)$")


def parse_a1(ref: str) -> tuple[int, int]:
    """Parse an A1 cell reference into 0-based (row, col). Raises ValueError."""
    match = _A1_RE.match(ref.strip())
    if match is None:
        raise ValueError(f"invalid cell reference '{ref}'")
    letters, digits = match.group(1).upper(), match.group(2)
    col = 0
    for ch in letters:
        col = col * 26 + (ord(ch) - 64)
    return int(digits) - 1, col - 1


def parse_range(ref: str) -> CellRange:
    """Parse 'A1:D10' into a normalized CellRange. Raises ValueError."""
    parts = ref.split(":")
    if len(parts) != 2:
        raise ValueError(f"invalid range '{ref}', expected 'A1:D10'")
    r1, c1 = parse_a1(parts[0])
    r2, c2 = parse_a1(parts[1])
    return CellRange(min(r1, r2), max(r1, r2), min(c1, c2), max(c1, c2))
