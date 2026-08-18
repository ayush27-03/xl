"""XLSX renderer for the payroll reconciliation report.

The workbook is the proof: a finance analyst opens it to re-check every number
the PDF states. Four sheets mirror the drill hierarchy, and each foots to the
same headline delta. Values are real numbers (not text), so the arithmetic can
be re-verified in Excel.
"""

from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..app.payroll_report import PayrollReport

_MONEY = '"₹"#,##,##0'
_PCT = '0.0"%"'
_NAVY = "0F2F4C"
_HEAD = Font(bold=True, color="FFFFFF")
_HEAD_FILL = PatternFill("solid", fgColor=_NAVY)
_BOLD = Font(bold=True)
_MUTED = Font(color="6B7280")
_THIN = Side(style="thin", color="D0D7DE")
_TOPB = Border(top=Side(style="medium", color="0F2F4C"))


def render_xlsx(report: PayrollReport) -> bytes:
    wb = Workbook()
    _bridge_sheet(wb.active, report)
    _components_sheet(wb.create_sheet("Components"), report)
    _employees_sheet(wb.create_sheet("Employees"), report)
    _exceptions_sheet(wb.create_sheet("Exceptions"), report)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _headerrow(ws, r, labels):
    for c, label in enumerate(labels, start=1):
        cell = ws.cell(row=r, column=c, value=label)
        cell.font = _HEAD
        cell.fill = _HEAD_FILL
        cell.alignment = Alignment(horizontal="left")


def _money(ws, r, c, v):
    cell = ws.cell(row=r, column=c, value=round(v, 2))
    cell.number_format = _MONEY
    return cell


def _widths(ws, widths):
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _bridge_sheet(ws, rep: PayrollReport):
    ws.title = "Bridge"
    ws["A1"] = "Payroll Reconciliation"
    ws["A1"].font = Font(bold=True, size=16)
    meta = [
        ("Entity", rep.entity or "—"),
        ("Previous period", rep.period_prev),
        ("Current period", rep.period_curr),
        ("Basis", f"Disbursed {rep.anchor}" + (" (SUBSTITUTED)" if rep.anchor_substituted else "")),
        ("Prepared by", rep.prepared_by),
        ("Run date", rep.run_date),
    ]
    r = 2
    for k, v in meta:
        ws.cell(row=r, column=1, value=k).font = _MUTED
        ws.cell(row=r, column=2, value=v)
        r += 1

    r += 1
    _headerrow(ws, r, ["Bridge step", "Amount", "Running total"])
    r += 1
    running = rep.total_prev
    steps = [("Previous total", None, rep.total_prev)]
    if rep.joiners:
        steps.append(("Joiners (cost added)", rep.joiner_cost, None))
    if rep.leavers:
        steps.append(("Leavers (credit)", rep.leaver_credit, None))
    steps.append(("Compensation-cost movement", rep.comp_movement, None))
    if abs(rep.reimb_movement) > 0.5:
        steps.append(("Reimbursement / recovery", rep.reimb_movement, None))
    if abs(rep.residual) >= 1.0:
        steps.append(("Unexplained residual", rep.residual, None))
    steps.append(("Current total", None, rep.total_curr))

    start = r
    for label, amt, total in steps:
        ws.cell(row=r, column=1, value=label)
        if amt is not None:
            _money(ws, r, 2, amt)
            running += amt
            _money(ws, r, 3, running)
        if total is not None:
            _money(ws, r, 3, total).font = _BOLD
            ws.cell(row=r, column=1).font = _BOLD
        r += 1
    # the running total on the final row must equal Current — the by-hand proof
    for col in (1, 2, 3):
        ws.cell(row=start, column=col).border = _TOPB

    r += 1
    ws.cell(row=r, column=1, value="Net movement").font = _BOLD
    _money(ws, r, 2, rep.delta).font = _BOLD
    ws.cell(row=r, column=3, value=round(rep.pct or 0, 2)).number_format = _PCT
    r += 1
    ws.cell(row=r, column=1, value="Gross component churn")
    _money(ws, r, 2, rep.gross_churn)
    r += 2
    ws.cell(row=r, column=1, value=(
        f"Ties to disbursed {rep.anchor}; residual "
        + ("₹0." if rep.ties_out else f"₹{rep.residual:,.2f} (ABOVE MATERIALITY)")
    )).font = _BOLD if not rep.ties_out else _MUTED
    r += 1
    ws.cell(row=r, column=1, value=rep.basis_note).font = _MUTED
    _widths(ws, [34, 18, 18])


def _components_sheet(ws, rep: PayrollReport):
    _headerrow(ws, 1, ["Component", "Category", "Previous", "Current", "Net impact",
                       "Gross churn", "% of movement", "Employees", "Largest increase", "Largest decrease"])
    r = 2
    for c in rep.components_all:
        ws.cell(row=r, column=1, value=c.name)
        ws.cell(row=r, column=2, value=c.category)
        _money(ws, r, 3, c.prev)
        _money(ws, r, 4, c.curr)
        _money(ws, r, 5, c.net_impact)
        _money(ws, r, 6, c.gross_churn)
        ws.cell(row=r, column=7, value=round(c.share * 100, 1)).number_format = _PCT
        ws.cell(row=r, column=8, value=c.employees_affected)
        ws.cell(row=r, column=9, value=_mover(c.top_increase))
        ws.cell(row=r, column=10, value=_mover(c.top_decrease))
        r += 1
    ws.cell(row=r, column=1, value="TOTAL net impact").font = _BOLD
    total = _money(ws, r, 5, sum(c.net_impact for c in rep.components_all))
    total.font = _BOLD
    total.border = _TOPB
    ws.cell(row=r, column=4, value="ties to comp + reimb =").font = _MUTED
    _money(ws, r, 6, rep.comp_movement + rep.reimb_movement).font = _MUTED
    _widths(ws, [30, 14, 14, 14, 14, 14, 13, 11, 24, 24])


def _employees_sheet(ws, rep: PayrollReport):
    _headerrow(ws, 1, ["Employee ID", "Name", "Department", "Designation", "Status",
                       "Previous", "Current", "Change", "% change", "% of movement"])
    r = 2
    for e in rep.employees_all:
        ws.cell(row=r, column=1, value=e.id)
        ws.cell(row=r, column=2, value=e.name)
        ws.cell(row=r, column=3, value=e.dept)
        ws.cell(row=r, column=4, value=e.designation)
        ws.cell(row=r, column=5, value=e.status)
        if e.prev is not None:
            _money(ws, r, 6, e.prev)
        if e.curr is not None:
            _money(ws, r, 7, e.curr)
        _money(ws, r, 8, e.delta)
        if e.pct is not None:
            ws.cell(row=r, column=9, value=round(e.pct, 1)).number_format = _PCT
        ws.cell(row=r, column=10, value=round(e.share * 100, 1)).number_format = _PCT
        r += 1
    ws.cell(row=r, column=1, value="TOTAL change").font = _BOLD
    total = _money(ws, r, 8, sum(e.delta for e in rep.employees_all))
    total.font = _BOLD
    total.border = _TOPB
    ws.cell(row=r, column=6, value="ties to headline =").font = _MUTED
    _money(ws, r, 7, rep.delta).font = _MUTED
    _widths(ws, [12, 20, 22, 22, 11, 14, 14, 14, 11, 13])


def _exceptions_sheet(ws, rep: PayrollReport):
    _headerrow(ws, 1, ["Severity", "Finding", "Detail"])
    r = 2
    if not rep.exceptions:
        ws.cell(row=r, column=1, value="—")
        ws.cell(row=r, column=2, value="No business-impact issues detected.")
    for x in rep.exceptions:
        ws.cell(row=r, column=1, value=x.severity.upper())
        ws.cell(row=r, column=2, value=x.title).font = _BOLD
        ws.cell(row=r, column=3, value=x.detail)
        r += 1
    _widths(ws, [12, 36, 70])


def _mover(m):
    if not m:
        return ""
    _id, name, amt = m
    return f"{name or _id} ({amt:+,.0f})"
