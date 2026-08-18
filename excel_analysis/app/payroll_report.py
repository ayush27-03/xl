"""Payroll one-page reconciliation report — the canonical model both file
renderers (PDF, XLSX) format.

Every figure here comes from the engine's own outputs: the headline, bridge,
residual and headcount are taken verbatim from the `ReconciliationResult`; the
component and employee rankings are aggregated from the normalized `Dataset`
rows. Nothing is recomputed in a way that could drift from the bridge — the
report *selects and ranks* canonical facts, it does not re-derive them. The one
page renderer truncates; this model carries the full lists for the workbook.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from ..domain.models import (
    AnalysisResult,
    Column,
    Dataset,
    RawWorkbook,
    ReconciliationResult,
)

# A residual below one rupee is rounding; at or above it is a real, hard flag.
RESIDUAL_MATERIALITY = 1.0

_MONTHS = (
    "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|"
    "january|february|march|april|june|july|august|september|october|november|december"
)
_ENTITY_RE = re.compile(r"\b(ltd|limited|pvt|private|inc|incorporated|llp|corp|corporation|company)\b", re.I)
_PERIOD_RE = re.compile(rf"(month of|for the month|pay\s*(sheet|slip|register|period)|({_MONTHS})[^0-9]{{0,4}}\d{{4}}|\b\d{{4}}\b)", re.I)


@dataclass(frozen=True)
class ReportComponent:
    name: str
    category: str
    prev: float
    curr: float
    net_impact: float
    gross_churn: float
    share: float
    employees_affected: int
    top_increase: Optional[tuple[str, str, float]]  # (id, name, amount)
    top_decrease: Optional[tuple[str, str, float]]


@dataclass(frozen=True)
class ReportEmployee:
    id: str
    name: str
    dept: str
    designation: str
    status: str
    prev: Optional[float]
    curr: Optional[float]
    delta: float
    pct: Optional[float]
    share: float


@dataclass(frozen=True)
class ReportException:
    severity: str  # "high" | "medium"
    title: str
    detail: str


@dataclass(frozen=True)
class PayrollReport:
    entity: Optional[str]
    period_prev: str
    period_curr: str
    run_date: str
    prepared_by: str
    anchor: str
    anchor_substituted: bool
    total_prev: float
    total_curr: float
    delta: float
    pct: Optional[float]
    comp_movement: float
    reimb_movement: float
    residual: float
    ties_out: bool
    gross_churn: float
    retained: int
    joiners: int
    leavers: int
    joiner_cost: float
    leaver_credit: float
    top_components: tuple[ReportComponent, ...]
    top_employees: tuple[ReportEmployee, ...]
    exceptions: tuple[ReportException, ...]
    components_all: tuple[ReportComponent, ...]
    employees_all: tuple[ReportEmployee, ...]
    n_components_more: int
    n_employees_more: int
    basis_note: str


# --- small numeric helpers (mirror the frontend so both agree) --------------


def _num(value) -> Optional[float]:
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


def _normkey(value) -> str:
    s = str(value if value is not None else "").strip()
    if s == "":
        return ""
    if re.fullmatch(r"[+-]?\d+", s):
        return str(int(s))
    try:
        f = float(s)
    except ValueError:
        return s
    return str(int(f)) if f.is_integer() else repr(f)


def _colmap(ds: Dataset) -> dict[str, Column]:
    return {c.name: c for c in ds.columns}


def _first_name_col(ds: Dataset) -> Optional[str]:
    for c in ds.columns:
        n = c.name.lower()
        if "name" in n and not any(x in n for x in ("bank", "father", "user")):
            return c.name
    return None


# --- title / entity / period extraction from the raw workbooks --------------


def _title_lines(raw: RawWorkbook, sheet_name: str, header_row: int) -> list[str]:
    for sheet in raw.sheets:
        if sheet.name != sheet_name:
            continue
        out: list[str] = []
        for r in range(min(header_row, sheet.n_rows)):
            for cell in sheet.cells[r]:
                v = cell.value
                if isinstance(v, str) and v.strip() and not v.strip().replace(".", "").isdigit():
                    out.append(v.strip())
        return out
    return []


def _pick_entity(lines: list[str]) -> Optional[str]:
    for ln in lines:
        if _ENTITY_RE.search(ln):
            return ln
    return None


def _pick_period(lines: list[str], fallback: str) -> str:
    for ln in lines:
        if _PERIOD_RE.search(ln):
            return ln
    return fallback


def _period_labels(result, left_raw, right_raw, left_name, right_name):
    lp = result.left_dataset.provenance
    rp = result.right_dataset.provenance
    left_lines = _title_lines(left_raw, lp.sheet_name, lp.header_row)
    right_lines = _title_lines(right_raw, rp.sheet_name, rp.header_row)
    entity = _pick_entity(right_lines) or _pick_entity(left_lines)
    prev = _pick_period(left_lines, _strip_ext(left_name))
    curr = _pick_period(right_lines, _strip_ext(right_name))
    return entity, prev, curr


def _strip_ext(name: str) -> str:
    return re.sub(r"\.xlsx$", "", name, flags=re.I)


def period_token(label: str) -> str:
    """A compact, filename-safe token for a period label: 'Jun2026' from
    'Pay Sheet for the Month of Jun 2026', else an alphanumeric squeeze."""
    m = re.search(rf"({_MONTHS})[a-z]*[^0-9]{{0,4}}(\d{{4}})", label, re.I)
    if m:
        return m.group(1).title()[:3] + m.group(2)
    y = re.search(r"\b(\d{4})\b", label)
    squeezed = re.sub(r"[^A-Za-z0-9]+", "", label)[:16]
    return squeezed or (y.group(1) if y else "Period")


# --- employee + component aggregation (canonical rows) ----------------------


def _employees(result: AnalysisResult, rec: ReconciliationResult):
    left, right = result.left_dataset, result.right_dataset
    lcols, rcols = _colmap(left), _colmap(right)
    key = rec.key_column
    anchor = rec.anchor
    name_col = _first_name_col(right) or _first_name_col(left)

    def index(ds_cols, key_name):
        idx: dict[str, int] = {}
        if key_name not in ds_cols:
            return idx
        vals = ds_cols[key_name].values
        for i, v in enumerate(vals):
            k = _normkey(v)
            if k and k not in idx:
                idx[k] = i
        return idx

    lidx = index(lcols, key)
    ridx = index(rcols, key)

    def cell(cols, i, name):
        col = cols.get(name)
        return col.values[i] if col is not None and i is not None else None

    records = []
    for k in dict.fromkeys(list(lidx) + list(ridx)):  # stable order: left then new right
        li = lidx.get(k)
        ri = ridx.get(k)
        status = "retained" if li is not None and ri is not None else ("joiner" if ri is not None else "leaver")
        a_l = _num(cell(lcols, li, anchor)) if li is not None else None
        a_r = _num(cell(rcols, ri, anchor)) if ri is not None else None
        if status == "retained":
            delta = (a_r or 0) - (a_l or 0)
        elif status == "joiner":
            delta = a_r or 0
        else:
            delta = -(a_l or 0)
        src_cols, src_i = (rcols, ri) if ri is not None else (lcols, li)
        records.append({
            "id": k,
            "name": str(cell(src_cols, src_i, name_col) or "") if name_col else "",
            "li": li, "ri": ri, "status": status,
            "prev": a_l, "curr": a_r, "delta": delta,
        })
    return records, lcols, rcols


def _report_employees(records, lcols, rcols, total_abs_delta) -> list[ReportEmployee]:
    def attr(rec, *names):
        cols, i = (rcols, rec["ri"]) if rec["ri"] is not None else (lcols, rec["li"])
        for n in cols:
            if any(t.lower() in n.lower() for t in names):
                v = cols[n].values[i]
                if v is not None and str(v).strip():
                    return str(v)
        return ""

    out = []
    for rec in records:
        prev, curr, delta = rec["prev"], rec["curr"], rec["delta"]
        pct = ((curr - prev) / abs(prev) * 100.0) if (prev not in (None, 0) and curr is not None) else None
        out.append(ReportEmployee(
            id=rec["id"], name=rec["name"],
            dept=attr(rec, "department"), designation=attr(rec, "designation"),
            status=rec["status"], prev=prev, curr=curr, delta=delta, pct=pct,
            share=(abs(delta) / total_abs_delta) if total_abs_delta else 0.0,
        ))
    out.sort(key=lambda e: abs(e.delta), reverse=True)
    return out


def _report_components(records, lcols, rcols, rec: ReconciliationResult) -> list[ReportComponent]:
    cats = {c.column: c.category.value for c in rec.classification}
    comp_cols = [c.column for c in rec.classification if c.role.value == "component"]
    retained = [r for r in records if r["status"] == "retained"]
    out = []
    for name in comp_cols:
        category = cats.get(name, "none")
        lc, rcc = lcols.get(name), rcols.get(name)
        left = right = 0.0
        affected = 0
        top_inc = top_dec = None
        for r in retained:
            lv = _num(lc.values[r["li"]]) if lc is not None and r["li"] is not None else 0.0
            rv = _num(rcc.values[r["ri"]]) if rcc is not None and r["ri"] is not None else 0.0
            lv = lv or 0.0
            rv = rv or 0.0
            left += lv
            right += rv
            d = rv - lv
            if abs(d) > 0.005:
                affected += 1
            if d > 0 and (top_inc is None or d > top_inc[2]):
                top_inc = (r["id"], r["name"], d)
            if d < 0 and (top_dec is None or d < top_dec[2]):
                top_dec = (r["id"], r["name"], d)
        delta = right - left
        net = -delta if category == "deduction" else delta
        if abs(delta) <= 0.005 and affected == 0:
            continue
        out.append(ReportComponent(
            name=name, category=category, prev=left, curr=right,
            net_impact=net, gross_churn=abs(net), share=0.0,
            employees_affected=affected, top_increase=top_inc, top_decrease=top_dec,
        ))
    total_abs = sum(c.gross_churn for c in out) or 1.0
    out = [
        ReportComponent(**{**c.__dict__, "share": c.gross_churn / total_abs})
        for c in out
    ]
    out.sort(key=lambda c: abs(c.net_impact), reverse=True)
    return out


def _exceptions(records, lcols, rcols, rec: ReconciliationResult, anchor: str) -> list[ReportException]:
    out: list[ReportException] = []

    def dup_ids(cols, period):
        key = rec.key_column
        if not key or key not in cols:
            return
        seen: dict[str, int] = {}
        for v in cols[key].values:
            k = _normkey(v)
            if k:
                seen[k] = seen.get(k, 0) + 1
        dups = [k for k, n in seen.items() if n > 1]
        if dups:
            out.append(ReportException("high", f"Duplicate Employee IDs in {period}",
                                       f"{len(dups)} ID(s) appear more than once and may double-count payroll."))

    dup_ids(lcols, "the previous period")
    dup_ids(rcols, "the current period")

    nonpos = [r for r in records if r["status"] != "leaver" and r["curr"] is not None and r["curr"] <= 0]
    if nonpos:
        out.append(ReportException("high", f"Zero or negative {anchor}",
                                   f"{len(nonpos)} employee(s) have a current {anchor} of zero or below."))

    statutory = {"pf", "provident fund", "tds", "pt", "professional tax", "esi", "employee state insurance"}
    stat_cols = [c.column for c in rec.classification
                 if c.role.value == "component" and c.category.value == "deduction" and c.column.strip().lower() in statutory]
    dropped = 0
    for r in records:
        if r["status"] != "retained":
            continue
        for name in stat_cols:
            lv = _num(lcols[name].values[r["li"]]) if name in lcols else None
            rv = _num(rcols[name].values[r["ri"]]) if name in rcols else None
            if (lv or 0) > 0 and (rv or 0) == 0:
                dropped += 1
                break
    if dropped:
        out.append(ReportException("high", "Statutory deduction disappeared",
                                   f"{dropped} employee(s) had a statutory deduction previously that is now zero."))

    joiners = sum(1 for r in records if r["status"] == "joiner")
    leavers = sum(1 for r in records if r["status"] == "leaver")
    if joiners or leavers:
        out.append(ReportException("medium", "Roster changed",
                                   f"{joiners} employee(s) only in the current file, {leavers} only in the previous."))

    if abs(rec.retained_residual) >= RESIDUAL_MATERIALITY:
        out.append(ReportException("high", "Reconciliation does not fully tie out",
                                   f"Unexplained residual of {rec.retained_residual:,.2f} after compensation and "
                                   f"reimbursement movement; stored subtotals may not sum to {anchor}."))
    return out


def build_payroll_report(
    result: AnalysisResult,
    left_raw: RawWorkbook,
    right_raw: RawWorkbook,
    *,
    left_name: str,
    right_name: str,
    prepared_by: str = "Payroll Portal",
    top_n: int = 5,
) -> PayrollReport:
    rec = result.reconciliation
    if rec is None or not rec.comparable:
        raise ValueError("Reconciliation is not applicable to these files; cannot build a report.")

    entity, period_prev, period_curr = _period_labels(result, left_raw, right_raw, left_name, right_name)
    records, lcols, rcols = _employees(result, rec)

    total_abs_delta = sum(abs(r["delta"]) for r in records) or 1.0
    employees = _report_employees(records, lcols, rcols, total_abs_delta)
    components = _report_components(records, lcols, rcols, rec)
    exceptions = _exceptions(records, lcols, rcols, rec, rec.anchor)

    gross_churn = sum(c.gross_churn for c in components)
    joiner_cost = rec.joiners.amount
    leaver_credit = rec.leavers.amount
    pct = (rec.delta / abs(rec.total_left) * 100.0) if rec.total_left else None
    residual = rec.retained_residual
    ties_out = abs(residual) < RESIDUAL_MATERIALITY

    return PayrollReport(
        entity=entity,
        period_prev=period_prev,
        period_curr=period_curr,
        run_date=date.today().isoformat(),
        prepared_by=prepared_by,
        anchor=rec.anchor,
        anchor_substituted=rec.anchor_substituted,
        total_prev=rec.total_left,
        total_curr=rec.total_right,
        delta=rec.delta,
        pct=pct,
        comp_movement=rec.retained_compensation_delta,
        reimb_movement=rec.retained_reimbursement_delta,
        residual=residual,
        ties_out=ties_out,
        gross_churn=gross_churn,
        retained=rec.retained.count,
        joiners=rec.joiners.count,
        leavers=rec.leavers.count,
        joiner_cost=joiner_cost,
        leaver_credit=leaver_credit,
        top_components=tuple(components[:top_n]),
        top_employees=tuple(employees[:top_n]),
        exceptions=tuple(exceptions),
        components_all=tuple(components),
        employees_all=tuple(employees),
        n_components_more=max(0, len(components) - top_n),
        n_employees_more=max(0, len(employees) - top_n),
        basis_note=(
            f"Basis: disbursed {rec.anchor}. Employer PF/ESI/gratuity are NOT included; "
            f"reimbursements are ring-fenced from compensation-cost movement."
        ),
    )
