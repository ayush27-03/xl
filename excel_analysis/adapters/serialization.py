"""JSON serialization adapter — renders the analysis result for the CLI.

Presentation lives at the edge: domain models stay ignorant of JSON. Output key
order is fixed here so the same result always serialises byte-for-byte
identically (CLAUDE.md rule 3). Row/column indices are surfaced 1-based for
humans, matching Excel's own addressing.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from ..domain.models import (
    ColumnProfile,
    DatasetProfile,
    DetectedTable,
    Diagnostic,
    TableAnalysis,
    WorkbookAnalysis,
    range_ref,
)


def to_json(result: WorkbookAnalysis, *, indent: int | None = 2) -> str:
    return json.dumps(_workbook(result), indent=indent, default=_fallback)


def _fallback(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _workbook(result: WorkbookAnalysis) -> dict[str, Any]:
    return {
        "source_path": result.source_path,
        "table_count": len(result.tables),
        "tables": [_table(t) for t in result.tables],
        "diagnostics": [_diagnostic(d) for d in result.diagnostics],
    }


def _table(t: TableAnalysis) -> dict[str, Any]:
    return {"detected": _detected(t.detected), "profile": _profile(t.profile)}


def _detected(d: DetectedTable) -> dict[str, Any]:
    return {
        "sheet": d.sheet_name,
        "table_index": d.table_index,
        "range": range_ref(d.region),
        "header_row": d.header_row + 1,  # 1-based for humans
        "confidence": d.confidence,
        "signals": d.signals,
    }


def _profile(p: DatasetProfile) -> dict[str, Any]:
    return {
        "name": p.name,
        "n_rows": p.n_rows,
        "n_columns": p.n_columns,
        "columns": [_column(c) for c in p.columns],
    }


def _column(c: ColumnProfile) -> dict[str, Any]:
    return {
        "name": c.name,
        "type": c.type.value,
        "count": c.count,
        "null_count": c.null_count,
        "non_null_count": c.non_null_count,
        "unique_count": c.unique_count,
        "stats": {k: _scalar(v) for k, v in c.stats.items()},
    }


def _scalar(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):  # e.g. most_common
        return {k: _scalar(v) for k, v in value.items()}
    return value


def _diagnostic(d: Diagnostic) -> dict[str, Any]:
    item: dict[str, Any] = {
        "severity": d.severity.value,
        "code": d.code,
        "message": d.message,
    }
    if d.location is not None:
        item["location"] = d.location
    if d.confidence is not None:
        item["confidence"] = d.confidence
    return item
