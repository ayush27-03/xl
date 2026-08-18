"""Reconciliation analyzer (M11) — the payroll sign-off bridge.

Consumes two Datasets + an Alignment and walks the Period-A total to the
Period-B total through mutually exclusive buckets that tie out to the rupee.
Pure domain: no I/O, imports no other analysis stage (CLAUDE.md rules 1-3).

The headline anchor is a stored total column (default **Net Payable** — the cash
that leaves the account). The three population buckets (Joiners / Leavers /
Retained) satisfy `delta == joiners + leavers + retained` by construction, so the
top of the bridge cannot silently fail to reconcile. The Retained bucket is then
split into ring-fenced compensation-cost vs reimbursement/recovery movement,
taken from the file's *own* stored subtotal columns (`Gross Earnings`,
`Gross Deduction`, `Gross Reimbursement`), with any untied remainder surfaced as
an explicit residual — never a silent fudge (rules 4-5).

Column classification (which component is an earning / deduction / reimbursement)
is derived from those subtotal anchors and *validated* against them, so the SPA's
drill-down groups components the way the payroll system itself already balanced
them. Nothing is inferred from a column name alone.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

from .diagnostics import Diagnostics
from .models import (
    Alignment,
    BucketFlow,
    CategoryFlow,
    Column,
    ColumnClassification,
    ColumnRole,
    ColumnType,
    Dataset,
    PayCategory,
    ReconciliationResult,
    RowMatchBasis,
)

# Money tie-out tolerance: sub-paisa. Real payroll totals are whole rupees.
_TOL = 0.01

# Default anchor preference, most-complete first. Net Payable is a superset
# bridge (earnings -> deductions -> reimbursements); the others nest inside it.
_ANCHOR_PREFERENCE = ("Net Payable", "Net Pay", "Gross Earnings")

# Which stored subtotals constitute each anchor, with the sign each contributes
# to the net figure. Standard payroll algebra, stated explicitly rather than
# guessed. An empty list marks a leaf total (its own movement is the earning).
_ANCHOR_CONSTITUENTS: dict[str, tuple[tuple[str, int, PayCategory], ...]] = {
    "net payable": (
        ("gross earnings", +1, PayCategory.EARNING),
        ("gross deduction", -1, PayCategory.DEDUCTION),
        ("gross reimbursement", +1, PayCategory.REIMBURSEMENT),
    ),
    "net pay": (
        ("gross earnings", +1, PayCategory.EARNING),
        ("gross deduction", -1, PayCategory.DEDUCTION),
    ),
    "gross earnings": (),
}

# Stored subtotal columns (normalized) and the category each belongs to.
_SUBTOTALS: dict[str, PayCategory] = {
    "statutory earnings": PayCategory.EARNING,
    "gross earnings": PayCategory.EARNING,
    "statutory deduction": PayCategory.DEDUCTION,
    "statutory deductions": PayCategory.DEDUCTION,
    "gross deduction": PayCategory.DEDUCTION,
    "gross deductions": PayCategory.DEDUCTION,
    "net pay": PayCategory.NONE,
    "gross reimbursement": PayCategory.REIMBURSEMENT,
    "gross reimbursements": PayCategory.REIMBURSEMENT,
    "net payable": PayCategory.NONE,
}


def _norm(name: str) -> str:
    collapsed = re.sub(r"[^0-9a-z]+", " ", name.strip().lower())
    return re.sub(r"\s+", " ", collapsed).strip()


def _num(value) -> Optional[float]:
    """Coerce a cell to a float, or None if it isn't a finite quantity. Dates and
    non-numeric text are not quantities."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, (datetime, date)):
        return None
    s = str(value).strip().replace(",", "")
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _sum_at(col: Column, rows) -> float:
    return sum((_num(col.values[r]) or 0.0) for r in rows)


def _by_norm(dataset: Dataset) -> dict[str, Column]:
    """Normalized-name -> Column. On a collision the first (leftmost) wins; a
    payroll sheet's subtotal names are unique in practice."""
    out: dict[str, Column] = {}
    for c in dataset.columns:
        out.setdefault(_norm(c.name), c)
    return out


def reconcile(
    left: Dataset,
    right: Dataset,
    alignment: Alignment,
    *,
    anchor: str = "Net Payable",
) -> ReconciliationResult:
    """Reconciliation owns its own diagnostics collector: payroll-specific
    findings belong with the reconciliation, not in the generic diff warnings."""
    diagnostics = Diagnostics()
    left_by = _by_norm(left)
    right_by = _by_norm(right)

    resolved, substituted = _resolve_anchor(anchor, left_by, right_by, diagnostics)
    classification = _classify(right, diagnostics, alignment.row_key)

    if resolved is None:
        diagnostics.warning(
            "reconciliation-not-applicable",
            "No shared numeric total column (e.g. Net Payable) found in both "
            "periods; the payroll bridge is not applicable.",
        )
        return _empty(anchor, alignment.row_key, classification, diagnostics.to_tuple())

    if alignment.row_basis is not RowMatchBasis.KEY:
        diagnostics.warning(
            "reconciliation-no-key",
            "Rows are aligned by position, not a stable key. Joiner/leaver "
            "buckets are unreliable without an Employee ID; treat with caution.",
            confidence=alignment.row_confidence,
        )

    lcol, rcol = left_by[resolved], right_by[resolved]
    retained = list(alignment.row_matches)
    leaver_rows = list(alignment.rows_only_in_left)
    joiner_rows = list(alignment.rows_only_in_right)

    total_left = _sum_at(lcol, range(left.n_rows))
    total_right = _sum_at(rcol, range(right.n_rows))
    delta = total_right - total_left

    joiners_amt = _sum_at(rcol, joiner_rows)
    leavers_amt = -_sum_at(lcol, leaver_rows)
    retained_amt = sum(
        (_num(rcol.values[rm.right_row]) or 0.0) - (_num(lcol.values[rm.left_row]) or 0.0)
        for rm in retained
    )

    comp, reimb, flows = _decompose_retained(resolved, left_by, right_by, retained, diagnostics)
    residual = retained_amt - comp - reimb

    # Top-level identity is structural, but assert it so a future refactor that
    # breaks it fails loudly rather than shipping a bridge that doesn't tie.
    assert abs(delta - (joiners_amt + leavers_amt + retained_amt)) < _TOL, (
        "reconciliation identity broken: buckets do not sum to delta"
    )
    if abs(residual) > _TOL:
        diagnostics.warning(
            "reconciliation-residual",
            f"Retained {resolved} movement has an unexplained residual of "
            f"{round(residual, 2)} after compensation and reimbursement buckets; "
            f"stored subtotals may not sum to the anchor.",
            confidence=0.0,
        )

    return ReconciliationResult(
        comparable=True,
        anchor=rcol.name,
        anchor_requested=anchor,
        anchor_substituted=substituted,
        key_column=alignment.row_key,
        total_left=round(total_left, 2),
        total_right=round(total_right, 2),
        delta=round(delta, 2),
        joiners=BucketFlow("Joiners", len(joiner_rows), round(joiners_amt, 2)),
        leavers=BucketFlow("Leavers", len(leaver_rows), round(leavers_amt, 2)),
        retained=BucketFlow("Retained", len(retained), round(retained_amt, 2)),
        retained_compensation_delta=round(comp, 2),
        retained_reimbursement_delta=round(reimb, 2),
        retained_residual=round(residual, 2),
        category_flows=flows,
        classification=classification,
        diagnostics=diagnostics.to_tuple(),
    )


def _resolve_anchor(requested, left_by, right_by, diagnostics):
    """Return (normalized anchor present in both, substituted?). Falls back to the
    preference order and records the substitution loudly (never silent)."""
    def shared_numeric(name_norm: str) -> bool:
        lc, rc = left_by.get(name_norm), right_by.get(name_norm)
        return (
            lc is not None and rc is not None
            and lc.type is ColumnType.NUMBER and rc.type is ColumnType.NUMBER
        )

    req = _norm(requested)
    if shared_numeric(req):
        return req, False
    for candidate in _ANCHOR_PREFERENCE:
        cn = _norm(candidate)
        if cn != req and shared_numeric(cn):
            diagnostics.warning(
                "reconciliation-anchor-substituted",
                f"Requested anchor '{requested}' is not a shared numeric column; "
                f"reconciling on '{candidate}' instead. Period-over-period "
                f"comparisons must use the same anchor.",
            )
            return cn, True
    return None, False


def _decompose_retained(anchor_norm, left_by, right_by, retained, diagnostics):
    """Ring-fence the retained movement into compensation-cost vs reimbursement,
    from the anchor's stored constituent subtotals. Returns (comp, reimb, flows)."""
    constituents = _ANCHOR_CONSTITUENTS.get(anchor_norm)
    if not constituents:  # leaf total (e.g. Gross Earnings): movement is itself
        amt = sum(
            (_num(right_by[anchor_norm].values[rm.right_row]) or 0.0)
            - (_num(left_by[anchor_norm].values[rm.left_row]) or 0.0)
            for rm in retained
        )
        return amt, 0.0, (CategoryFlow(PayCategory.EARNING, right_by[anchor_norm].name, round(amt, 2)),)

    comp = 0.0
    reimb = 0.0
    flows: list[CategoryFlow] = []
    for sub_norm, sign, category in constituents:
        lc, rc = left_by.get(sub_norm), right_by.get(sub_norm)
        if lc is None or rc is None:
            diagnostics.info(
                "reconciliation-subtotal-missing",
                f"Anchor constituent '{sub_norm}' absent in a period; its movement "
                f"falls into the residual bucket.",
            )
            continue
        amt = sign * sum(
            (_num(rc.values[rm.right_row]) or 0.0) - (_num(lc.values[rm.left_row]) or 0.0)
            for rm in retained
        )
        flows.append(CategoryFlow(category, rc.name, round(amt, 2)))
        if category is PayCategory.REIMBURSEMENT:
            reimb += amt
        else:
            comp += amt
    return comp, reimb, tuple(flows)


# --- Column classification ---------------------------------------------------


def _classify(
    dataset: Dataset, diagnostics: Diagnostics, key_column: Optional[str] = None
) -> tuple[ColumnClassification, ...]:
    """Assign each column a payroll role/category from the subtotal anchors and
    validate each component block against its stored subtotal. The alignment key
    is an identifier, never a pay component, even when it is numeric."""
    cols = list(dataset.columns)
    norms = [_norm(c.name) for c in cols]
    idx = {n: i for i, n in enumerate(norms)}  # first occurrence
    out: list[Optional[ColumnClassification]] = [None] * len(cols)
    key_norm = _norm(key_column) if key_column else None

    # 0) the alignment key is identity — pin it before any block logic claims it.
    for i, n in enumerate(norms):
        if key_norm is not None and n == key_norm:
            out[i] = ColumnClassification(cols[i].name, ColumnRole.IDENTITY, PayCategory.NONE)

    # 1) subtotals first.
    for i, n in enumerate(norms):
        if out[i] is None and n in _SUBTOTALS:
            out[i] = ColumnClassification(cols[i].name, ColumnRole.SUBTOTAL, _SUBTOTALS[n])

    i_ge = idx.get("gross earnings")
    i_gd = idx.get("gross deduction", idx.get("gross deductions"))
    i_np = idx.get("net pay")
    i_gr = idx.get("gross reimbursement", idx.get("gross reimbursements"))
    rows = range(dataset.n_rows)

    def numeric_unclassified(lo: int, hi: int) -> list[int]:
        return [
            j for j in range(max(lo, 0), min(hi, len(cols)))
            if out[j] is None and cols[j].type is ColumnType.NUMBER
        ]

    # 2) earnings: the right-anchored run before Gross Earnings that ties to it
    #    (peels attendance off the left, since attendance breaks the tie).
    if i_ge is not None:
        region = numeric_unclassified(0, i_ge)
        earning_idxs, tied = _tying_suffix(region, cols, cols[i_ge], rows)
        conf = 1.0 if tied else 0.5
        if not tied and earning_idxs:
            diagnostics.info(
                "reconciliation-earnings-untied",
                "Earning components did not sum to 'Gross Earnings'; component "
                "attribution is best-effort (confidence 0.5).",
            )
        for j in earning_idxs:
            out[j] = ColumnClassification(cols[j].name, ColumnRole.COMPONENT, PayCategory.EARNING, conf)
        for j in region:
            if out[j] is None:  # numeric, before earnings block -> attendance
                out[j] = ColumnClassification(cols[j].name, ColumnRole.ATTENDANCE, PayCategory.NONE)

    # 3) deductions: cleanly bounded by Gross Earnings .. Gross Deduction.
    if i_ge is not None and i_gd is not None:
        _tag_bounded(numeric_unclassified(i_ge + 1, i_gd), cols, cols[i_gd], rows,
                     PayCategory.DEDUCTION, out, diagnostics, "deductions")

    # 4) reimbursements: bounded by Net Pay (or Gross Deduction) .. Gross Reimbursement.
    lo = (i_np if i_np is not None else i_gd)
    if lo is not None and i_gr is not None:
        _tag_bounded(numeric_unclassified(lo + 1, i_gr), cols, cols[i_gr], rows,
                     PayCategory.REIMBURSEMENT, out, diagnostics, "reimbursements")

    # 5) everything else: numeric -> attendance/other, non-numeric -> identity.
    for i, c in enumerate(cols):
        if out[i] is None:
            role = ColumnRole.ATTENDANCE if c.type is ColumnType.NUMBER else ColumnRole.IDENTITY
            out[i] = ColumnClassification(c.name, role, PayCategory.NONE)
    return tuple(o for o in out if o is not None)


def _tying_suffix(region: list[int], cols, target: Column, rows):
    """Largest right-anchored subset of `region` whose per-row sum equals the
    target column, within tolerance, with identically-zero boundary columns
    trimmed off the left (an all-zero column contributes nothing to the subtotal
    and is not a live component of it). Returns (indices, tied?)."""
    target_vals = [(_num(target.values[r]) or 0.0) for r in rows]
    for k in range(len(region) + 1):
        suffix = region[k:]
        ok = True
        for ri, r in enumerate(rows):
            s = sum((_num(cols[j].values[r]) or 0.0) for j in suffix)
            if abs(s - target_vals[ri]) > _TOL:
                ok = False
                break
        if ok:
            while suffix and _all_zero(cols[suffix[0]], rows):
                suffix = suffix[1:]
            return suffix, True
    return region, False


def _all_zero(col: Column, rows) -> bool:
    return all(abs(_num(col.values[r]) or 0.0) <= _TOL for r in rows)


def _tag_bounded(region, cols, target, rows, category, out, diagnostics, label):
    tied = _block_ties(region, cols, target, rows)
    conf = 1.0 if tied else 0.5
    if not tied and region:
        diagnostics.info(
            f"reconciliation-{label}-untied",
            f"{label.capitalize()} components did not sum to their stored "
            f"subtotal; component attribution is best-effort (confidence 0.5).",
        )
    for j in region:
        out[j] = ColumnClassification(cols[j].name, ColumnRole.COMPONENT, category, conf)


def _block_ties(region, cols, target, rows) -> bool:
    for r in rows:
        s = sum((_num(cols[j].values[r]) or 0.0) for j in region)
        if abs(s - (_num(target.values[r]) or 0.0)) > _TOL:
            return False
    return True


def _empty(anchor, key_column, classification, diagnostics) -> ReconciliationResult:
    zero = BucketFlow("", 0, 0.0)
    return ReconciliationResult(
        comparable=False, anchor=None, anchor_requested=anchor, anchor_substituted=False,
        key_column=key_column, total_left=0.0, total_right=0.0, delta=0.0,
        joiners=zero, leavers=zero, retained=zero,
        retained_compensation_delta=0.0, retained_reimbursement_delta=0.0,
        retained_residual=0.0, category_flows=(), classification=classification,
        diagnostics=diagnostics,
    )
