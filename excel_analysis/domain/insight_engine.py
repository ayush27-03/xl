"""Insight Engine — ranks and surfaces facts already in the DiffResult (M7).

Strictly rule-based and deterministic (no AI; narration is deferred to the
optional M9 port). The governing rule: an insight may only RESTATE a fact
already in the diff (counts, existing deltas/%, before/after values) and rank
it. It never computes a new domain number, so insights inherit the comparator's
verified accuracy instead of opening a second place where numbers are made.

Rules are tiered integrity > structural > variance > info, so data-integrity
defects (e.g. a retyped date column that also differs across rows — the DoB
shift) rank above routine value variance. Output is capped and ordered.
"""

from __future__ import annotations

from collections import Counter

from .models import ColumnType, DiffResult, Insight, InsightSeverity

_INSIGHT_CAP = 12
_TOP_COLUMNS = 5
_MAX_LISTED = 8
_SEVERITY_ORDER = {
    InsightSeverity.INTEGRITY: 0,
    InsightSeverity.STRUCTURAL: 1,
    InsightSeverity.VARIANCE: 2,
    InsightSeverity.INFO: 3,
}


def generate_insights(diff: DiffResult) -> tuple[Insight, ...]:
    collected: list[tuple[int, Insight]] = []
    for rule_index, rule in enumerate(_RULES):
        for insight in rule(diff):
            collected.append((rule_index, insight))
    collected.sort(key=lambda t: (_SEVERITY_ORDER[t[1].severity], t[0], t[1].code))
    return tuple(insight for _, insight in collected[:_INSIGHT_CAP])


# --- shared fact lookups (tallies of existing facts only) -------------------


def _matched_rows(diff: DiffResult) -> int:
    return len(diff.row_changes) + diff.rows_unchanged


def _change_counts(diff: DiffResult) -> Counter:
    counts: Counter = Counter()
    for rc in diff.row_changes:
        for cell in rc.cells:
            counts[cell.column] += 1
    return counts


def _example_cell(diff: DiffResult, column: str):
    for rc in diff.row_changes:
        for cell in rc.cells:
            if cell.column == column:
                return cell
    return None


def _listed(names: list[str]) -> str:
    shown = ", ".join(names[:_MAX_LISTED])
    return shown + (", ..." if len(names) > _MAX_LISTED else "")


# --- integrity tier ---------------------------------------------------------


def _rule_not_comparable(diff):
    if diff.row_basis.value == "none":
        return [Insight(
            "not-comparable", InsightSeverity.INTEGRITY,
            "The two tables share no columns and are not comparable by row.",
            ("row_basis=none",),
        )]
    return []


def _rule_positional(diff):
    if diff.row_basis.value == "position":
        return [Insight(
            "positional-alignment", InsightSeverity.INTEGRITY,
            f"No row key was found; rows were matched by POSITION only "
            f"(confidence {diff.row_confidence}). Row-level differences are unverified.",
            (f"row_basis=position", f"row_confidence={diff.row_confidence}"),
        )]
    return []


def _rule_retyped_columns_changed(diff):
    counts = _change_counts(diff)
    matched = _matched_rows(diff)
    flagged = [
        (counts.get(t.left, 0), t)
        for t in diff.columns_retyped
        if t.right_type is not ColumnType.EMPTY and counts.get(t.left, 0) > 0
    ]
    if not flagged:
        return []
    flagged.sort(key=lambda x: (-x[0], x[1].left))
    parts = [
        f"{t.left} ({t.left_type.value}->{t.right_type.value}, {n}/{matched} rows changed)"
        for n, t in flagged
    ]
    return [Insight(
        "retyped-columns-changed", InsightSeverity.INTEGRITY,
        f"{len(flagged)} column(s) changed type AND differ across rows - verify these are "
        f"real changes, not a shift or formatting artifact: " + "; ".join(parts) + ".",
        tuple(
            f"columns_retyped:{t.left} {t.left_type.value}->{t.right_type.value}; changed {n}/{matched}"
            for n, t in flagged
        ),
    )]


def _rule_columns_emptied(diff):
    emptied = [t for t in diff.columns_retyped if t.right_type is ColumnType.EMPTY]
    if not emptied:
        return []
    names = [t.left for t in emptied]
    return [Insight(
        "columns-emptied", InsightSeverity.INTEGRITY,
        f"{len(emptied)} column(s) present but empty in the right table - possible data "
        f"loss: {_listed(names)}.",
        tuple(f"columns_retyped:{t.left} {t.left_type.value}->empty" for t in emptied),
    )]


# --- structural tier --------------------------------------------------------


def _rule_columns_removed(diff):
    if not diff.columns_removed:
        return []
    cols = list(diff.columns_removed)
    return [Insight(
        "columns-removed", InsightSeverity.STRUCTURAL,
        f"{len(cols)} column(s) dropped in the right table: {_listed(cols)}.",
        (f"columns_removed={cols}",),
    )]


def _rule_columns_added(diff):
    if not diff.columns_added:
        return []
    cols = list(diff.columns_added)
    return [Insight(
        "columns-added", InsightSeverity.STRUCTURAL,
        f"{len(cols)} column(s) added in the right table: {_listed(cols)}.",
        (f"columns_added={cols}",),
    )]


def _rule_columns_renamed(diff):
    renamed = [m for m in diff.columns_matched if m.left != m.right]
    if not renamed:
        return []
    parts = ", ".join(f"'{m.left}'->'{m.right}'" for m in renamed[:_MAX_LISTED])
    return [Insight(
        "columns-renamed", InsightSeverity.STRUCTURAL,
        f"{len(renamed)} column(s) matched under a different name: {parts}.",
        tuple(f"matched:{m.left}->{m.right} ({m.basis.value})" for m in renamed),
    )]


def _rule_roster_change(diff):
    if diff.rows_added or diff.rows_removed:
        return [Insight(
            "roster-change", InsightSeverity.STRUCTURAL,
            f"Roster changed: {diff.rows_added} row(s) added, {diff.rows_removed} removed "
            f"(new / departed records).",
            (f"rows_added={diff.rows_added}", f"rows_removed={diff.rows_removed}"),
        )]
    return [Insight(
        "roster-stable", InsightSeverity.INFO,
        f"Roster unchanged: no rows added or removed ({_matched_rows(diff)} matched).",
        ("rows_added=0", "rows_removed=0", f"matched={_matched_rows(diff)}"),
    )]


# --- variance tier ----------------------------------------------------------


def _rule_systematic_change(diff):
    matched = _matched_rows(diff)
    if matched == 0:
        return []
    counts = _change_counts(diff)
    systematic = sorted(col for col, n in counts.items() if n == matched)
    if not systematic:
        return []
    example = _example_cell(diff, systematic[0])
    hint = ""
    if example is not None:
        pct = f", {example.pct_change:+}%" if example.pct_change is not None else ""
        hint = f" (e.g. {systematic[0]}: {example.left_value} -> {example.right_value}{pct})"
    return [Insight(
        "systematic-change", InsightSeverity.VARIANCE,
        f"{len(systematic)} column(s) changed in every one of the {matched} matched rows "
        f"(a systematic change, e.g. a revised run): {_listed(systematic)}{hint}.",
        tuple(f"changed_in_all_rows:{col} ({matched}/{matched})" for col in systematic),
    )]


def _rule_overall_summary(diff):
    matched = _matched_rows(diff)
    changed = len(diff.row_changes)
    total_cells = sum(len(rc.cells) for rc in diff.row_changes)
    cols_changed = len(_change_counts(diff))
    return [Insight(
        "overall-change-summary", InsightSeverity.VARIANCE,
        f"{changed} of {matched} matched rows changed; {total_cells} cell difference(s) "
        f"across {cols_changed} column(s).",
        (f"row_changes={changed}", f"rows_unchanged={diff.rows_unchanged}",
         f"total_cell_changes={total_cells}", f"columns_changed={cols_changed}"),
    )]


def _rule_most_changed_columns(diff):
    counts = _change_counts(diff)
    if not counts:
        return []
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:_TOP_COLUMNS]
    parts = ", ".join(f"{col} ({n})" for col, n in ranked)
    return [Insight(
        "most-changed-columns", InsightSeverity.VARIANCE,
        f"Most-changed columns (by rows affected): {parts}.",
        tuple(f"changes:{col}={n}" for col, n in ranked),
    )]


def _rule_largest_numeric_change(diff):
    numeric = [
        (abs(cell.delta), cell)
        for rc in diff.row_changes
        for cell in rc.cells
        if cell.kind == "numeric" and cell.delta is not None
    ]
    if not numeric:
        return []
    numeric.sort(key=lambda x: (-x[0], x[1].column))
    cell = numeric[0][1]
    pct = f", {cell.pct_change:+}%" if cell.pct_change is not None else ""
    return [Insight(
        "largest-numeric-change", InsightSeverity.VARIANCE,
        f"Largest single numeric change: {cell.column} {cell.left_value} -> {cell.right_value} "
        f"(delta {cell.delta:+}{pct}).",
        (f"cell:{cell.column} delta={cell.delta} pct={cell.pct_change}",),
    )]


_RULES = (
    _rule_not_comparable,
    _rule_positional,
    _rule_retyped_columns_changed,
    _rule_columns_emptied,
    _rule_columns_removed,
    _rule_columns_added,
    _rule_columns_renamed,
    _rule_roster_change,
    _rule_systematic_change,
    _rule_overall_summary,
    _rule_most_changed_columns,
    _rule_largest_numeric_change,
)
