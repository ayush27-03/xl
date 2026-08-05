"""Normalizer — produces the Dataset contract (CLAUDE.md rule 1).

Takes a raw sheet grid plus a DetectedTable and emits a clean, typed Dataset:
canonical column names, values inferred from the data itself, standardised
missing values, and a default merged-cell policy. This is where spreadsheet
chaos ends. It imports no I/O and never looks past the Dataset boundary.

Default merged-cell (unmerge) policy: a merged cell takes its top-left value.
Applied merges in the region are recorded as a Diagnostic.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from .config import DEFAULT_CONFIG, Config
from .diagnostics import Diagnostics
from .models import (
    Column,
    ColumnProvenance,
    ColumnType,
    Dataset,
    DatasetProvenance,
    DetectedTable,
    MergedRange,
    RawSheetGrid,
    a1,
    range_ref,
)


def normalize(
    sheet: RawSheetGrid,
    table: DetectedTable,
    diagnostics: Diagnostics,
    config: Config = DEFAULT_CONFIG,
) -> Dataset:
    # config.unmerge_policy currently has a single value (PROPAGATE_TOP_LEFT);
    # it is threaded here to reserve the seam for future unmerge policies.
    region = table.region
    header_row = table.header_row
    first_col, last_col = region.first_col, region.last_col

    _note_merges(sheet, table, diagnostics)

    raw_headers = [
        _effective_value(sheet, header_row, c) for c in range(first_col, last_col + 1)
    ]
    names = _canonical_names(raw_headers, diagnostics, sheet.name)

    data_first = header_row + 1
    n_rows = max(0, region.last_row - data_first + 1)

    columns: list[Column] = []
    for offset, name in enumerate(names):
        c = first_col + offset
        values = tuple(
            _standardize(_effective_value(sheet, r, c))
            for r in range(data_first, region.last_row + 1)
        )
        col_type = _infer_type(values, diagnostics, sheet.name, name)
        provenance = ColumnProvenance(
            sheet_name=sheet.name, source_column=c, header_cell=a1(header_row, c)
        )
        columns.append(
            Column(name=name, type=col_type, values=values, provenance=provenance)
        )

    provenance = DatasetProvenance(
        sheet_name=sheet.name, region_ref=range_ref(region), header_row=header_row
    )
    return Dataset(
        name=f"{sheet.name}!{range_ref(region)}",
        columns=tuple(columns),
        n_rows=n_rows,
        provenance=provenance,
    )


# --- Merged cells -----------------------------------------------------------


def _merged_at(sheet: RawSheetGrid, row: int, col: int) -> Optional[MergedRange]:
    for m in sheet.merged_ranges:
        if m.contains(row, col):
            return m
    return None


def _effective_value(sheet: RawSheetGrid, row: int, col: int) -> Any:
    """Default unmerge policy: a merged cell takes its top-left value."""
    m = _merged_at(sheet, row, col)
    if m is not None:
        return sheet.cells[m.first_row][m.first_col].value
    return sheet.cells[row][col].value


def _note_merges(
    sheet: RawSheetGrid, table: DetectedTable, diagnostics: Diagnostics
) -> None:
    region = table.region
    overlaps = any(
        not (
            m.last_row < region.first_row
            or m.first_row > region.last_row
            or m.last_col < region.first_col
            or m.first_col > region.last_col
        )
        for m in sheet.merged_ranges
    )
    if overlaps:
        diagnostics.info(
            "merged-cells",
            f"Sheet '{sheet.name}' region {range_ref(region)}: merged cells filled "
            f"with their top-left value (default policy).",
            location=f"{sheet.name}!{range_ref(region)}",
        )


# --- Header names -----------------------------------------------------------


def _canonical_names(
    raw_headers: list[Any], diagnostics: Diagnostics, sheet_name: str
) -> list[str]:
    names: list[str] = []
    counts: dict[str, int] = {}
    for i, raw in enumerate(raw_headers):
        base = "" if raw is None else " ".join(str(raw).strip().split())
        if base == "":
            base = f"column_{i + 1}"
            diagnostics.info(
                "empty-header",
                f"Sheet '{sheet_name}' header {i + 1} was blank; named '{base}'.",
                location=sheet_name,
            )
        if base in counts:
            counts[base] += 1
            name = f"{base}_{counts[base]}"
            diagnostics.info(
                "duplicate-header",
                f"Sheet '{sheet_name}' duplicate header '{base}' renamed '{name}'.",
                location=sheet_name,
            )
        else:
            counts[base] = 0
            name = base
        names.append(name)
    return names


# --- Missing values & type inference ---------------------------------------


def _standardize(value: Any) -> Any:
    """Standardise missing values to None; trim strings."""
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped != "" else None
    return value


def _value_kind(value: Any) -> ColumnType:
    # bool must precede int/float: bool is a subclass of int.
    if isinstance(value, bool):
        return ColumnType.BOOL
    if isinstance(value, (datetime, date)):
        return ColumnType.DATE
    if isinstance(value, (int, float)):
        return ColumnType.NUMBER
    return ColumnType.TEXT


def _infer_type(
    values: tuple[Any, ...], diagnostics: Diagnostics, sheet_name: str, col_name: str
) -> ColumnType:
    """Infer a column's type from its values, never from what Excel stored.

    Homogeneous non-null values -> that type. A genuine mix is flagged as MIXED
    and left uncoerced (CLAUDE.md rule 5: surface ambiguity, don't force it).
    """
    kinds = {_value_kind(v) for v in values if v is not None}
    if not kinds:
        return ColumnType.EMPTY
    if len(kinds) == 1:
        return next(iter(kinds))
    diagnostics.warning(
        "mixed-types",
        f"Sheet '{sheet_name}' column '{col_name}' holds mixed types "
        f"({', '.join(sorted(k.value for k in kinds))}); left as MIXED, not coerced.",
        location=sheet_name,
    )
    return ColumnType.MIXED
