"""Report model — the shared section structure both renderers format (M8).

`build_report` reads AnalysisResult ONLY and emits presentation blocks with
finance-facing labels ("Structural changes", not "schema"). It performs no
recomputation: every number comes verbatim from the contract; only list lengths
and a truncation count are taken. Markdown and HTML are two stylings of this one
structure, so they cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Union

from ..domain.models import AnalysisResult, DiffResult, InsightSeverity

_MAX_CELL_ROWS = 25


@dataclass(frozen=True)
class Heading:
    level: int
    text: str


@dataclass(frozen=True)
class Text:
    text: str


@dataclass(frozen=True)
class Bullets:
    items: tuple[str, ...]


@dataclass(frozen=True)
class Table:
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class Callout:
    kind: str  # "integrity" | "warning" | "info"
    text: str


Block = Union[Heading, Text, Bullets, Table, Callout]


def build_report(result: AnalysisResult) -> list[Block]:
    blocks: list[Block] = [Heading(1, "Comparison Report")]
    blocks += _alignment(result.diff)
    blocks += _key_findings(result)
    blocks += _structural(result.diff)
    blocks += _records(result.diff)
    blocks += _changed_values(result.diff)
    blocks += _datasets(result)
    blocks += _warnings(result)
    return blocks


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _alignment(diff: DiffResult) -> list[Block]:
    basis = diff.row_basis.value
    if basis == "key":
        return [Text(f"Rows aligned on key '{diff.row_key}' (confidence {diff.row_confidence}).")]
    if basis == "position":
        return [Callout(
            "warning",
            f"No row key found - rows matched by POSITION (confidence {diff.row_confidence}); "
            f"row-level differences are unverified.",
        )]
    return [Callout("integrity", "The two tables share no columns and are not comparable by row.")]


def _key_findings(result: AnalysisResult) -> list[Block]:
    blocks: list[Block] = [Heading(2, "Key findings")]
    if not result.insights:
        blocks.append(Text("No differences detected."))
        return blocks
    rest: list[str] = []
    for insight in result.insights:
        if insight.severity is InsightSeverity.INTEGRITY:
            blocks.append(Callout("integrity", insight.message))
        else:
            rest.append(insight.message)
    if rest:
        blocks.append(Bullets(tuple(rest)))
    return blocks


def _structural(diff: DiffResult) -> list[Block]:
    rows: list[tuple[str, str]] = []
    if diff.columns_added:
        rows.append(("Added", ", ".join(diff.columns_added)))
    if diff.columns_removed:
        rows.append(("Removed", ", ".join(diff.columns_removed)))
    renamed = [(m.left, m.right) for m in diff.columns_matched if m.left != m.right]
    if renamed:
        rows.append(("Renamed", ", ".join(f"{left} -> {right}" for left, right in renamed)))
    if diff.columns_retyped:
        rows.append((
            "Type changed",
            ", ".join(
                f"{t.left} ({t.left_type.value} -> {t.right_type.value})"
                for t in diff.columns_retyped
            ),
        ))
    blocks: list[Block] = [Heading(2, "Structural changes")]
    blocks.append(Table(("Change", "Columns"), tuple(rows)) if rows else Text("No structural changes."))
    return blocks


def _records(diff: DiffResult) -> list[Block]:
    return [
        Heading(2, "Record changes"),
        Text(
            f"Changed: {len(diff.row_changes)}; unchanged: {diff.rows_unchanged}; "
            f"added: {diff.rows_added}; removed: {diff.rows_removed}."
        ),
    ]


def _changed_values(diff: DiffResult) -> list[Block]:
    cells = [
        (
            _fmt(rc.key), c.column, _fmt(c.left_value), _fmt(c.right_value),
            "" if c.delta is None else f"{c.delta:+}",
            "" if c.pct_change is None else f"{c.pct_change:+}%",
        )
        for rc in diff.row_changes
        for c in rc.cells
    ]
    blocks: list[Block] = [Heading(2, "Changed values")]
    if not cells:
        blocks.append(Text("No cell-level changes."))
        return blocks
    blocks.append(Table(
        ("Record", "Column", "Before", "After", "Delta", "% change"),
        tuple(cells[:_MAX_CELL_ROWS]),
    ))
    if len(cells) > _MAX_CELL_ROWS:
        blocks.append(Text(
            f"Showing the first {_MAX_CELL_ROWS} of {len(cells)} changed cells; "
            f"see the JSON output for the full list."
        ))
    return blocks


def _datasets(result: AnalysisResult) -> list[Block]:
    lp, rp = result.left_profile, result.right_profile
    return [
        Heading(2, "Datasets"),
        Bullets((
            f"Left: {lp.name} - {lp.n_rows} rows x {lp.n_columns} columns",
            f"Right: {rp.name} - {rp.n_rows} rows x {rp.n_columns} columns",
        )),
    ]


def _warnings(result: AnalysisResult) -> list[Block]:
    blocks: list[Block] = [Heading(2, "Warnings & notes")]
    warns = [w for w in result.warnings if w.severity.value in ("warning", "error")]
    notes = [w for w in result.warnings if w.severity.value == "info"]
    for w in warns:
        blocks.append(Callout("warning", f"{w.code}: {w.message}"))
    if notes:
        blocks.append(Bullets(tuple(f"{w.code}: {w.message}" for w in notes)))
    if not warns and not notes:
        blocks.append(Text("None."))
    return blocks
