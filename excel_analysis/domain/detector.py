"""TableDetector — heuristic structure discovery (CLAUDE.md rules 4 & 5).

Turns a raw sheet grid into zero or more DetectedTables, each with an explicit
confidence score for its header-row choice. It never assumes row 1 is the header
or that a sheet holds exactly one table. It knows nothing about diffs, profiles,
or Datasets (CLAUDE.md rule 1) and imports no I/O.

Strategy (deliberately simple for the first slice):
  1. Split the sheet into blocks of consecutive non-empty rows (blank rows are
     separators -> this is how multiple stacked tables are found).
  2. In each block, score the first few rows as header candidates and pick the
     best; rows above it are recorded as title/notes.
Known limitation: two tables side-by-side in the same rows are not split. That
is a future TableDetectionStrategy, not a silent wrong answer.
"""

from __future__ import annotations

from typing import Optional

from .diagnostics import Diagnostics
from .models import (
    CellRange,
    CellType,
    DetectedTable,
    RawSheetGrid,
    a1,
    range_ref,
)

# How many rows at the top of a block to consider as the header.
_MAX_HEADER_CANDIDATES = 5
# Below this confidence, the header choice is flagged prominently.
_LOW_CONFIDENCE = 0.5


def detect_tables(
    sheet: RawSheetGrid, diagnostics: Diagnostics
) -> tuple[DetectedTable, ...]:
    if sheet.hidden:
        diagnostics.warning(
            "hidden-sheet",
            f"Sheet '{sheet.name}' is hidden; analyzing it anyway - verify this "
            f"is intended.",
            location=sheet.name,
        )

    blocks = _row_blocks(sheet)
    if not blocks:
        diagnostics.info(
            "empty-sheet",
            f"Sheet '{sheet.name}' has no populated cells; no tables detected.",
            location=sheet.name,
        )
        return ()

    tables: list[DetectedTable] = []
    for first_row, last_row in blocks:
        table = _detect_in_block(sheet, first_row, last_row, len(tables), diagnostics)
        if table is not None:
            tables.append(table)

    if not tables:
        diagnostics.info(
            "no-tables",
            f"Sheet '{sheet.name}' contained data but no table could be located.",
            location=sheet.name,
        )
    return tuple(tables)


# --- Blocking ---------------------------------------------------------------


def _row_is_empty(sheet: RawSheetGrid, r: int) -> bool:
    return all(cell.type == CellType.EMPTY for cell in sheet.cells[r])


def _row_blocks(sheet: RawSheetGrid) -> list[tuple[int, int]]:
    """Contiguous runs of non-empty rows, split by fully-blank rows."""
    blocks: list[tuple[int, int]] = []
    start: Optional[int] = None
    for r in range(sheet.n_rows):
        if not _row_is_empty(sheet, r):
            if start is None:
                start = r
        elif start is not None:
            blocks.append((start, r - 1))
            start = None
    if start is not None:
        blocks.append((start, sheet.n_rows - 1))
    return blocks


def _column_span(
    sheet: RawSheetGrid, first_row: int, last_row: int
) -> Optional[tuple[int, int]]:
    first_col: Optional[int] = None
    last_col: Optional[int] = None
    for r in range(first_row, last_row + 1):
        for c in range(sheet.n_cols):
            if sheet.cells[r][c].type != CellType.EMPTY:
                first_col = c if first_col is None else min(first_col, c)
                last_col = c if last_col is None else max(last_col, c)
    if first_col is None or last_col is None:
        return None
    return first_col, last_col


def _detect_in_block(
    sheet: RawSheetGrid,
    first_row: int,
    last_row: int,
    table_index: int,
    diagnostics: Diagnostics,
) -> Optional[DetectedTable]:
    span = _column_span(sheet, first_row, last_row)
    if span is None:
        return None
    first_col, last_col = span

    best_row: Optional[int] = None
    best_score = -1.0
    best_signals: dict[str, float] = {}
    limit = min(last_row, first_row + _MAX_HEADER_CANDIDATES - 1)
    for r in range(first_row, limit + 1):
        next_row = r + 1 if r + 1 <= last_row else None
        score, signals = score_header_row(sheet, r, next_row, first_col, last_col)
        if score > best_score:
            best_row, best_score, best_signals = r, score, signals

    if best_row is None:
        return None

    region = CellRange(
        first_row=best_row, last_row=last_row, first_col=first_col, last_col=last_col
    )

    if region.n_rows <= 1:
        # A header with no data rows below it is not a table — most often a title
        # or a stray label. Record it (rule 4) rather than emit a phantom table.
        diagnostics.info(
            "non-tabular-region",
            f"Sheet '{sheet.name}' region {range_ref(region)} has a header but no "
            f"data rows; treated as title/notes, not a table.",
            location=f"{sheet.name}!{range_ref(region)}",
        )
        return None

    # Rows above the header inside the block are title/notes — recorded, not used.
    for r in range(first_row, best_row):
        diagnostics.info(
            "title-or-notes",
            f"Sheet '{sheet.name}' row {r + 1} treated as title/notes above the "
            f"table.",
            location=f"{sheet.name}!{a1(r, first_col)}",
        )

    confidence = round(best_score, 4)
    table = DetectedTable(
        sheet_name=sheet.name,
        table_index=table_index,
        region=region,
        header_row=best_row,
        confidence=confidence,
        signals=best_signals,
    )
    if confidence < _LOW_CONFIDENCE:
        diagnostics.warning(
            "low-confidence-header",
            f"Sheet '{sheet.name}' table {table_index}: header row {best_row + 1} "
            f"chosen with low confidence ({confidence}). Verify the header.",
            location=f"{sheet.name}!{range_ref(region)}",
            confidence=confidence,
        )
    return table


# --- The header heuristic ---------------------------------------------------


def score_header_row(
    sheet: RawSheetGrid,
    row: int,
    next_row: Optional[int],
    first_col: int,
    last_col: int,
) -> tuple[float, dict[str, float]]:
    """Score how strongly ``row`` looks like a header for the column span.

    Returns ``(confidence in 0..1, signals)``. This is the single most
    consequential heuristic in the system — the whole downstream pipeline trusts
    its verdict — so it is isolated here and its signals are recorded for audit.
    Adjust the signals and weights below to change detection behaviour.
    """
    n_cols = last_col - first_col + 1
    types = [sheet.cells[row][c].type for c in range(first_col, last_col + 1)]
    values = [sheet.cells[row][c].value for c in range(first_col, last_col + 1)]

    non_empty = sum(t != CellType.EMPTY for t in types)
    filled = non_empty / n_cols                       # headers are fully populated
    texty = (
        sum(t == CellType.TEXT for t in types) / non_empty if non_empty else 0.0
    )                                                 # headers are text labels
    labels = [str(v).strip() for v, t in zip(values, types) if t != CellType.EMPTY]
    unique = len(set(labels)) / len(labels) if labels else 0.0   # distinct labels

    # Distinctness: the row below should look more like data (less texty).
    if next_row is not None:
        next_types = [sheet.cells[next_row][c].type for c in range(first_col, last_col + 1)]
        next_non_empty = sum(t != CellType.EMPTY for t in next_types)
        next_texty = (
            sum(t == CellType.TEXT for t in next_types) / next_non_empty
            if next_non_empty
            else 0.0
        )
        distinct = max(0.0, texty - next_texty)
    else:
        distinct = 0.0

    signals = {
        "filled": round(filled, 4),
        "texty": round(texty, 4),
        "unique": round(unique, 4),
        "distinct_from_next": round(distinct, 4),
    }

    # Weights are the knob that shapes detection behaviour; they sum to 1.0.
    weights = {"filled": 0.30, "texty": 0.35, "unique": 0.20, "distinct_from_next": 0.15}
    score = (
        weights["filled"] * filled
        + weights["texty"] * texty
        + weights["unique"] * unique
        + weights["distinct_from_next"] * distinct
    )
    return max(0.0, min(1.0, score)), signals
