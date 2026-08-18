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
    AnalysisReport,
    AnalysisResult,
    CellChange,
    ColumnMatch,
    ColumnProfile,
    ColumnTypeChange,
    DatasetProfile,
    DetectedTable,
    Diagnostic,
    DiffResult,
    Insight,
    RowChange,
    TableAnalysis,
    WorkbookAnalysis,
    range_ref,
)


def to_json(result: WorkbookAnalysis, *, indent: int | None = 2) -> str:
    return json.dumps(_workbook(result), indent=indent, default=_fallback)


def report_to_json(report: AnalysisReport, *, indent: int | None = 2) -> str:
    return json.dumps(_report(report), indent=indent, default=_fallback)


def _report(report: AnalysisReport) -> dict[str, Any]:
    return {
        "source_count": len(report.sources),
        "sources": [_workbook(w) for w in report.sources],
    }


def analysis_to_json(result: AnalysisResult, *, indent: int | None = 2) -> str:
    return json.dumps(_analysis(result), indent=indent, default=_fallback)


def _analysis(r: AnalysisResult) -> dict[str, Any]:
    return {
        "comparison": _diff(r.diff),
        "left_profile": _profile(r.left_profile),
        "right_profile": _profile(r.right_profile),
        "warnings": [_diagnostic(d) for d in r.warnings],
        "insights": [_insight(i) for i in r.insights],
        # M11 additive blocks: row-level data for the portal, and the payroll
        # reconciliation bridge. `null` when absent so the key set is stable.
        "datasets": _datasets(r),
        "reconciliation": _reconciliation(r.reconciliation),
    }


def _datasets(r: AnalysisResult) -> Any:
    if r.left_dataset is None or r.right_dataset is None:
        return None
    return {"left": _dataset(r.left_dataset), "right": _dataset(r.right_dataset)}


def _dataset(ds) -> dict[str, Any]:
    """Row-major serialization of a normalized Dataset. Columns carry name+type;
    rows are arrays aligned to `columns` by index (compact and unambiguous)."""
    return {
        "name": ds.name,
        "n_rows": ds.n_rows,
        "provenance": {
            "sheet": ds.provenance.sheet_name,
            "range": ds.provenance.region_ref,
            "header_row": ds.provenance.header_row + 1,  # 1-based for humans
        },
        "columns": [{"name": c.name, "type": c.type.value} for c in ds.columns],
        "rows": [
            [_scalar(c.values[i]) for c in ds.columns] for i in range(ds.n_rows)
        ],
    }


def _reconciliation(rec) -> Any:
    if rec is None:
        return None
    return {
        "comparable": rec.comparable,
        "anchor": rec.anchor,
        "anchor_requested": rec.anchor_requested,
        "anchor_substituted": rec.anchor_substituted,
        "key_column": rec.key_column,
        "total_left": rec.total_left,
        "total_right": rec.total_right,
        "delta": rec.delta,
        "buckets": {
            "joiners": _bucket(rec.joiners),
            "leavers": _bucket(rec.leavers),
            "retained": _bucket(rec.retained),
        },
        "retained": {
            "compensation_delta": rec.retained_compensation_delta,
            "reimbursement_delta": rec.retained_reimbursement_delta,
            "residual": rec.retained_residual,
        },
        "category_flows": [
            {"category": f.category.value, "subtotal_column": f.subtotal_column, "amount": f.amount}
            for f in rec.category_flows
        ],
        "classification": [
            {"column": c.column, "role": c.role.value, "category": c.category.value, "confidence": c.confidence}
            for c in rec.classification
        ],
        "diagnostics": [_diagnostic(d) for d in rec.diagnostics],
    }


def _bucket(b) -> dict[str, Any]:
    return {"label": b.label, "count": b.count, "amount": b.amount}


def _insight(i: Insight) -> dict[str, Any]:
    return {
        "code": i.code,
        "severity": i.severity.value,
        "message": i.message,
        "evidence": list(i.evidence),
    }


def _diff(d: DiffResult) -> dict[str, Any]:
    return {
        "alignment": {
            "row_basis": d.row_basis.value,
            "row_key": d.row_key,
            "row_confidence": d.row_confidence,
        },
        "schema": {
            "matched": [_column_match(m) for m in d.columns_matched],
            "added": list(d.columns_added),
            "removed": list(d.columns_removed),
            "retyped": [_type_change(t) for t in d.columns_retyped],
            "order_changed": d.column_order_changed,
        },
        "rows": {
            "changed": len(d.row_changes),
            "unchanged": d.rows_unchanged,
            "added": d.rows_added,
            "removed": d.rows_removed,
            "changes": [_row_change(rc) for rc in d.row_changes],
        },
    }


def _column_match(m: ColumnMatch) -> dict[str, Any]:
    return {"left": m.left, "right": m.right, "basis": m.basis.value, "confidence": m.confidence}


def _type_change(t: ColumnTypeChange) -> dict[str, Any]:
    return {"left": t.left, "right": t.right, "from": t.left_type.value, "to": t.right_type.value}


def _row_change(rc: RowChange) -> dict[str, Any]:
    return {
        "key": rc.key,
        "left_row": rc.left_row,
        "right_row": rc.right_row,
        "cells": [_cell(c) for c in rc.cells],
    }


def _cell(c: CellChange) -> dict[str, Any]:
    item: dict[str, Any] = {
        "column": c.column,
        "before": _scalar(c.left_value),
        "after": _scalar(c.right_value),
        "kind": c.kind,
    }
    if c.delta is not None:
        item["delta"] = c.delta
    if c.pct_change is not None:
        item["pct_change"] = c.pct_change
    return item


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
