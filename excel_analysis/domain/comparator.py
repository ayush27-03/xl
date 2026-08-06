"""Comparator — diffs two aligned Datasets (M5).

Consumes two Datasets plus an Alignment and produces a DiffResult: schema diff
(added / removed / renamed / retyped / reordered columns), row diff (added /
removed / changed / unchanged), and per-cell variance (numeric delta and %, or
categorical before -> after). Pure, deterministic, imports no other stage.

Cell comparison is type-aware: each value is reduced to a canonical token so a
date equals its text rendering, and a number equals its numeric text (leading
zeros stripped). Pure-integer values canonicalize to an exact int, never a float
-- long identifiers like bank-account numbers must not lose precision. Given the
same inputs, diff(A, A) is empty (the leading property).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Optional

from .diagnostics import Diagnostics
from .models import (
    Alignment,
    CellChange,
    ColumnTypeChange,
    Dataset,
    DiffResult,
    RowChange,
)


def compare(
    left: Dataset, right: Dataset, alignment: Alignment, diagnostics: Diagnostics
) -> DiffResult:
    left_cols = {c.name: c for c in left.columns}
    right_cols = {c.name: c for c in right.columns}

    renamed = tuple(
        (m.left, m.right) for m in alignment.column_matches if m.left != m.right
    )
    retyped: list[ColumnTypeChange] = []
    for m in alignment.column_matches:
        lt, rt = left_cols[m.left].type, right_cols[m.right].type
        if lt != rt:
            retyped.append(ColumnTypeChange(m.left, m.right, lt, rt))
            diagnostics.info(
                "column-retyped",
                f"Column '{m.left}' changed type {lt.value} -> {rt.value}.",
            )

    matched_pairs = [(m.left, m.right) for m in alignment.column_matches]
    row_changes: list[RowChange] = []
    unchanged = 0
    for rm in alignment.row_matches:
        cells = []
        for lname, rname in matched_pairs:
            change = _cell_change(
                lname,
                left_cols[lname].values[rm.left_row],
                right_cols[rname].values[rm.right_row],
            )
            if change is not None:
                cells.append(change)
        if cells:
            row_changes.append(RowChange(rm.key, rm.left_row, rm.right_row, tuple(cells)))
        else:
            unchanged += 1

    return DiffResult(
        columns_matched=alignment.column_matches,
        columns_added=alignment.columns_only_in_right,
        columns_removed=alignment.columns_only_in_left,
        columns_renamed=renamed,
        columns_retyped=tuple(retyped),
        column_order_changed=_order_changed(alignment.column_matches, left, right),
        rows_added=len(alignment.rows_only_in_right),
        rows_removed=len(alignment.rows_only_in_left),
        rows_unchanged=unchanged,
        row_changes=tuple(row_changes),
        row_basis=alignment.row_basis,
        row_key=alignment.row_key,
        row_confidence=alignment.row_confidence,
    )


# --- Schema helpers ---------------------------------------------------------


def _order_changed(matches, left, right) -> bool:
    if not matches:
        return False
    left_pos = {c.name: i for i, c in enumerate(left.columns)}
    right_pos = {c.name: i for i, c in enumerate(right.columns)}
    seq = [right_pos[m.right] for m in sorted(matches, key=lambda m: left_pos[m.left])]
    return seq != sorted(seq)


# --- Type-aware cell comparison ---------------------------------------------

_DATE_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y",
    "%d-%b-%Y", "%d %b %Y", "%d-%B-%Y", "%b %d, %Y", "%d.%m.%Y",
)


def _parse_date(s: str) -> Optional[date]:
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _canonical(value: Any):
    """Reduce a cell value to a type-tagged canonical token for comparison."""
    if value is None:
        return None
    if isinstance(value, bool):
        return ("b", value)
    if isinstance(value, datetime):
        return ("d", value.date())
    if isinstance(value, date):
        return ("d", value)
    if isinstance(value, int):
        return ("n", value)          # exact — no float precision loss
    if isinstance(value, float):
        return ("n", value)
    s = str(value).strip()
    if s == "":
        return None
    if re.fullmatch(r"[+-]?\d+", s):
        return ("n", int(s))         # leading zeros stripped, exact int
    try:
        return ("n", float(s))
    except ValueError:
        pass
    parsed = _parse_date(s)
    if parsed is not None:
        return ("d", parsed)
    return ("t", s)


def _cell_change(column: str, a: Any, b: Any) -> Optional[CellChange]:
    ca, cb = _canonical(a), _canonical(b)
    if ca == cb:
        return None                              # type-aware equality
    if ca is None:
        return CellChange(column, a, b, "added")
    if cb is None:
        return CellChange(column, a, b, "removed")
    if ca[0] == "n" and cb[0] == "n":
        delta = cb[1] - ca[1]
        pct = (delta / ca[1] * 100.0) if ca[1] != 0 else None
        return CellChange(
            column, a, b, "numeric",
            round(float(delta), 6),
            round(pct, 4) if pct is not None else None,
        )
    return CellChange(column, a, b, "categorical")
