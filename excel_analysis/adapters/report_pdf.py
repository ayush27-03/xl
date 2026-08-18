"""PDF renderer for the payroll reconciliation report — a single A4 portrait page
a payroll manager signs and forwards. No chrome, no interactivity: header,
headline, bridge, headcount, top movers, exceptions, and the assurance line, in
the order leadership reads them. Detail truncates; it never spills to page two.
"""

from __future__ import annotations

import os
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

from ..app.payroll_report import PayrollReport, ReportComponent, ReportEmployee

# Prefer a system font that carries the rupee glyph; fall back to Helvetica/"Rs".
FONT, FONT_B, RUPEE = "Helvetica", "Helvetica-Bold", "Rs."
for _reg, _bold in (
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
):
    if os.path.exists(_reg):
        try:
            pdfmetrics.registerFont(TTFont("AppSans", _reg))
            pdfmetrics.registerFont(TTFont("AppSans-Bold", _bold if os.path.exists(_bold) else _reg))
            FONT, FONT_B, RUPEE = "AppSans", "AppSans-Bold", "\u20b9"
            break
        except Exception:
            pass

NAVY = colors.HexColor("#0F2F4C")
TEAL = colors.HexColor("#0E7490")
RED = colors.HexColor("#B91C1C")
GREEN = colors.HexColor("#047857")
MUTED = colors.HexColor("#6B7280")
LINE = colors.HexColor("#D0D7DE")


def _grp(n: float) -> str:
    """Indian digit grouping: 31,27,398."""
    s = str(int(round(abs(n))))
    if len(s) <= 3:
        return s
    last3, rest = s[-3:], s[:-3]
    parts = []
    while len(rest) > 2:
        parts.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        parts.insert(0, rest)
    return ",".join(parts) + "," + last3


def inr(n) -> str:
    if n is None:
        return "—"
    sign = "−" if n < 0 else ""  # a negative amount must never read as positive
    return f"{sign}{RUPEE}{_grp(n)}"


def inr_s(n) -> str:
    if n is None:
        return "—"
    sign = "+" if n > 0 else ("\u2212" if n < 0 else "")
    return f"{sign}{RUPEE}{_grp(n)}"


def render_pdf(rep: PayrollReport) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    m = 15 * mm
    x = m
    y = H - m
    cw = W - 2 * m

    # --- header ---
    c.setFillColor(NAVY)
    c.setFont(FONT_B, 15)
    c.drawString(x, y, rep.entity or "Payroll Reconciliation")
    c.setFont(FONT, 9)
    c.setFillColor(MUTED)
    c.drawRightString(x + cw, y, f"Prepared by {rep.prepared_by} · {rep.run_date}")
    y -= 15
    c.setFillColor(colors.black)
    c.setFont(FONT_B, 11)
    c.drawString(x, y, "Payroll Reconciliation Report")
    y -= 14
    c.setFont(FONT, 9.5)
    c.drawString(x, y, f"{rep.period_prev}   →   {rep.period_curr}")
    y -= 13
    c.setFont(FONT, 8.5)
    c.setFillColor(MUTED)
    c.drawString(x, y, f"Basis: disbursed {rep.anchor}.")
    y -= 12
    if rep.anchor_substituted:
        c.setFillColor(RED)
        c.setFont(FONT_B, 8.5)
        c.drawString(x, y, f"NOTE: headline anchor was substituted to {rep.anchor} (a total column was missing in a file).")
        y -= 12
    c.setStrokeColor(LINE)
    c.line(x, y, x + cw, y)
    y -= 16

    # --- headline ---
    third = cw / 3
    for i, (label, val, tone) in enumerate([
        (f"Previous  ({rep.anchor})", inr(rep.total_prev), colors.black),
        (f"Current  ({rep.anchor})", inr(rep.total_curr), colors.black),
        ("Net movement", inr_s(rep.delta) + (f"   {_pct(rep.pct)}" if rep.pct is not None else ""),
         GREEN if rep.delta >= 0 else RED),
    ]):
        cx = x + i * third
        c.setFillColor(MUTED)
        c.setFont(FONT, 8)
        c.drawString(cx, y, label.upper())
        c.setFillColor(tone)
        c.setFont(FONT_B, 15)
        c.drawString(cx, y - 18, val)
    y -= 34
    c.setStrokeColor(LINE)
    c.line(x, y, x + cw, y)
    y -= 10

    # --- bridge (compact table) ---
    c.setFillColor(NAVY)
    c.setFont(FONT_B, 9.5)
    c.drawString(x, y, "Reconciliation bridge")
    y -= 4
    labels, vals, tones = ["Previous"], [inr(rep.total_prev)], [colors.black]
    if rep.joiners:
        labels.append("Joiners"); vals.append(inr_s(rep.joiner_cost)); tones.append(GREEN)
    if rep.leavers:
        labels.append("Leavers"); vals.append(inr_s(rep.leaver_credit)); tones.append(RED)
    labels.append("Compensation"); vals.append(inr_s(rep.comp_movement)); tones.append(GREEN if rep.comp_movement >= 0 else RED)
    if abs(rep.reimb_movement) > 0.5:
        labels.append("Reimb/recovery"); vals.append(inr_s(rep.reimb_movement)); tones.append(GREEN if rep.reimb_movement >= 0 else RED)
    if abs(rep.residual) >= 1.0:
        labels.append("Residual"); vals.append(inr_s(rep.residual)); tones.append(RED)
    labels.append("Current"); vals.append(inr(rep.total_curr)); tones.append(colors.black)
    ncol = len(labels)
    data = [labels, vals]
    t = Table(data, colWidths=[cw / ncol] * ncol, rowHeights=[13, 16])
    ts = [
        ("FONT", (0, 0), (-1, 0), FONT, 7.5),
        ("FONT", (0, 1), (-1, 1), FONT_B, 9),
        ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.4, LINE),
    ]
    for i, tone in enumerate(tones):
        ts.append(("TEXTCOLOR", (i, 1), (i, 1), tone))
    t.setStyle(TableStyle(ts))
    _draw(t, c, x, y - 4, cw)
    y -= 42
    c.setFont(FONT, 8.6)
    c.setFillColor(colors.black)
    ring = (f"{rep.anchor} moved {inr_s(rep.delta)}: {inr_s(rep.comp_movement)} real compensation-cost movement"
            + (f" and {inr_s(rep.reimb_movement)} reimbursement/recovery (pass-through)." if abs(rep.reimb_movement) > 0.5 else "."))
    for line in _wrap(c, ring, FONT, 8.6, cw):
        c.drawString(x, y, line); y -= 11
    c.setFillColor(NAVY)
    c.setFont(FONT_B, 8.6)
    c.drawString(x, y, f"Net movement of {inr_s(rep.delta)} sits on {inr(rep.gross_churn)} of gross component churn.")
    y -= 15

    # --- headcount ---
    c.setFillColor(colors.black)
    c.setFont(FONT, 8.8)
    hc = (f"Headcount: {rep.retained} retained · {rep.joiners} joiners "
          f"({inr(rep.joiner_cost)} added) · {rep.leavers} leavers ({inr(abs(rep.leaver_credit))} credit).")
    c.drawString(x, y, hc)
    y -= 16

    # --- top movers: components + employees side by side would be tight; stack ---
    y = _mini_table(c, x, y, cw, "Top components by net impact",
                    ["Component", "Prev", "Curr", "Net impact", "Share"],
                    [[_ell(cc.name, 34), inr(cc.prev), inr(cc.curr), inr_s(cc.net_impact), f"{cc.share * 100:.1f}%"]
                     for cc in rep.top_components],
                    [0.40, 0.15, 0.15, 0.19, 0.11], rep.n_components_more, right_cols={2, 3})
    y = _mini_table(c, x, y - 6, cw, "Top employees by net impact",
                    ["Employee", "Department", "Prev", "Curr", "Change"],
                    [[_ell(f"{e.name or e.id} #{e.id}", 28), _ell(e.dept, 22), inr(e.prev), inr(e.curr), inr_s(e.delta)]
                     for e in rep.top_employees],
                    [0.30, 0.26, 0.14, 0.14, 0.16], rep.n_employees_more, right_cols={2, 3, 4})

    # --- exceptions ---
    y -= 6
    c.setFillColor(RED if any(x.severity == "high" for x in rep.exceptions) else NAVY)
    c.setFont(FONT_B, 9.5)
    c.drawString(x, y, f"Requires attention ({len(rep.exceptions)})")
    y -= 13
    c.setFont(FONT, 8.3)
    if not rep.exceptions:
        c.setFillColor(GREEN)
        c.drawString(x, y, "No business-impact issues detected.")
        y -= 11
    for ex in rep.exceptions[:5]:
        c.setFillColor(RED if ex.severity == "high" else colors.HexColor("#B45309"))
        c.setFont(FONT_B, 8.3)
        c.drawString(x, y, f"• {ex.title}")
        c.setFillColor(MUTED)
        c.setFont(FONT, 8.3)
        for line in _wrap(c, ex.detail, FONT, 8.3, cw - 12):
            y -= 10
            c.drawString(x + 12, y, line)
        y -= 12
    c.drawString(x, y, "Full list in the portal · Data Quality.")
    y -= 16

    # --- assurance + basis footer ---
    c.setStrokeColor(LINE)
    c.line(x, y, x + cw, y)
    y -= 13
    c.setFont(FONT_B, 9)
    if rep.ties_out:
        c.setFillColor(GREEN)
        c.drawString(x, y, f"Bridge ties to disbursed {rep.anchor}; residual {RUPEE}0.")
    else:
        c.setFillColor(RED)
        c.drawString(x, y, f"CAVEAT: residual of {inr(rep.residual)} above materiality — does not fully tie out.")
    y -= 12
    c.setFillColor(MUTED)
    c.setFont(FONT, 7.5)
    for line in _wrap(c, rep.basis_note, FONT, 7.5, cw):
        c.drawString(x, y, line); y -= 9

    c.showPage()
    c.save()
    return buf.getvalue()


def _pct(v) -> str:
    if v is None:
        return "—"
    sign = "+" if v > 0 else ("\u2212" if v < 0 else "")
    return f"{sign}{abs(v):.1f}%"


def _draw(t: Table, c, x, y_top, avail):
    _, h = t.wrapOn(c, avail, 1000)
    t.drawOn(c, x, y_top - h)
    return h


def _mini_table(c, x, y, cw, title, headers, rows, fracs, more, right_cols):
    c.setFillColor(NAVY)
    c.setFont(FONT_B, 9.5)
    c.drawString(x, y, title)
    y -= 4
    col_w = [f * cw for f in fracs]
    data = [headers] + (rows if rows else [["—"] * len(headers)])
    ts = [
        ("FONT", (0, 0), (-1, 0), FONT_B, 7.5),
        ("FONT", (0, 1), (-1, -1), FONT, 8),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F6F9")]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ]
    for rc in right_cols:
        ts.append(("ALIGN", (rc, 0), (rc, -1), "RIGHT"))
    ts.append(("ALIGN", (len(headers) - 1, 0), (len(headers) - 1, -1), "RIGHT"))
    t = Table(data, colWidths=col_w)
    t.setStyle(TableStyle(ts))
    h = _draw(t, c, x, y, cw)
    y -= h + 3
    if more > 0:
        c.setFillColor(MUTED)
        c.setFont(FONT, 7.5)
        c.drawString(x, y, f"+{more} more in portal")
        y -= 10
    return y


def _ell(s, n):
    s = s or "—"
    return s if len(s) <= n else s[: n - 1] + "…"


def _wrap(c, text, font, size, maxw):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if c.stringWidth(trial, font, size) <= maxw:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines
