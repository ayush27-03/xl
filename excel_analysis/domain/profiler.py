"""Profiler — deterministic descriptive statistics over a Dataset.

Pure analysis: it consumes the Dataset contract and never sees a raw cell
(CLAUDE.md rule 1). Given the same Dataset it always returns the same profile
(CLAUDE.md rule 3): no set iteration order or randomness leaks into the output.
"""

from __future__ import annotations

from typing import Any

from .models import (
    Column,
    ColumnProfile,
    ColumnType,
    Dataset,
    DatasetProfile,
)


def profile_dataset(dataset: Dataset) -> DatasetProfile:
    columns = tuple(_profile_column(col) for col in dataset.columns)
    return DatasetProfile(
        name=dataset.name,
        n_rows=dataset.n_rows,
        n_columns=len(dataset.columns),
        columns=columns,
    )


def _profile_column(col: Column) -> ColumnProfile:
    non_null = [v for v in col.values if v is not None]
    return ColumnProfile(
        name=col.name,
        type=col.type,
        count=len(col.values),
        null_count=len(col.values) - len(non_null),
        non_null_count=len(non_null),
        unique_count=len(set(non_null)),
        stats=_stats_for(col.type, non_null),
    )


def _stats_for(col_type: ColumnType, non_null: list[Any]) -> dict[str, Any]:
    if not non_null:
        return {}
    if col_type == ColumnType.NUMBER:
        nums = [float(v) for v in non_null]
        total = sum(nums)
        return {
            "min": min(nums),
            "max": max(nums),
            "mean": total / len(nums),
            "sum": total,
        }
    if col_type == ColumnType.DATE:
        return {"min": min(non_null), "max": max(non_null)}
    if col_type == ColumnType.BOOL:
        true_count = sum(1 for v in non_null if v is True)
        return {"true_count": true_count, "false_count": len(non_null) - true_count}
    if col_type == ColumnType.TEXT:
        lengths = [len(str(v)) for v in non_null]
        return {
            "min_length": min(lengths),
            "max_length": max(lengths),
            "most_common": _most_common(non_null),
        }
    return {}  # MIXED / EMPTY: counts only


def _most_common(values: list[Any]) -> dict[str, Any]:
    counts: dict[Any, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    # Deterministic tie-break: highest count, then lexicographic string form.
    value, count = min(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))
    return {"value": value, "count": count}
