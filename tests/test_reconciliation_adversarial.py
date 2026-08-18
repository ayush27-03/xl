"""Adversarial reconciliation cases — the 'messy month', not the happy path.

The whole trust argument for this tool is that the bridge ties out even when the
inputs are ugly. Two properties must hold on every case below:

  1. The population identity is structural:  delta == joiners + leavers + retained.
  2. The retained residual stays at (near) zero WHENEVER the file's own stored
     subtotals are internally consistent — because the ring-fence is taken from
     those subtotals, not re-derived. When they are NOT consistent, the residual
     must be surfaced (a hard flag), never silently absorbed.

If any of these balloon on an ugly case, that is real exposure hiding, so these
are asserted as hard invariants.
"""

from __future__ import annotations

from _helpers import col, dataset
from excel_analysis.domain.aligner import align
from excel_analysis.domain.diagnostics import Diagnostics
from excel_analysis.domain.models import ColumnType
from excel_analysis.domain.reconciliation import reconcile

N = ColumnType.NUMBER
MATERIALITY = 1.0  # a residual below one rupee is rounding; at/above it is real


def payroll(recs, *, drop=()):
    """Build a payroll Dataset whose stored subtotals tie by construction:
    Gross Earnings = Σ earnings, Net Pay = GE − PF, Net Payable = Net Pay + LTA.
    `recs` are dicts; `drop` omits an earning column entirely (schema drift).
    A per-row 'net_payable' key overrides the stored total (breaks the tie)."""
    ids = [r["id"] for r in recs]
    basic = [r.get("basic", 0) for r in recs]
    hra = [r.get("hra", 0) for r in recs]
    special = [r.get("special", 0) for r in recs]
    pf = [r.get("pf", 0) for r in recs]
    lta = [r.get("lta", 0) for r in recs]

    earnings = [("Basic", basic), ("HRA", hra)]
    if "Special Allowance" not in drop:
        earnings.append(("Special Allowance", special))
    ge = [sum(vals[i] for _, vals in earnings) for i in range(len(recs))]
    gd = list(pf)
    net_pay = [e - d for e, d in zip(ge, gd)]
    gr = list(lta)
    net_payable = [r["net_payable"] if "net_payable" in r else np + g
                   for r, np, g in zip(recs, net_pay, gr)]

    cols = [col("Employee_ID", ids, N)]
    cols += [col(name, vals, N) for name, vals in earnings]
    cols += [
        col("Gross Earnings", ge, N),
        col("PF", pf, N),
        col("Gross Deduction", gd, N),
        col("Net Pay", net_pay, N),
        col("LTA Reimbursement", lta, N),
        col("Gross Reimbursement", gr, N),
        col("Net Payable", net_payable, N),
    ]
    return dataset(cols)


def _reconcile(left, right, **kw):
    diags = Diagnostics()
    r = reconcile(left, right, align(left, right, diags), **kw)
    return r, [d.code for d in r.diagnostics]


def _identity_holds(r) -> bool:
    return abs(r.delta - (r.joiners.amount + r.leavers.amount + r.retained.amount)) < 0.01


# A clean base pair (3 retained employees), mutated per case.
def base_left():
    return payroll([
        {"id": 1, "basic": 1000, "hra": 500, "special": 100, "pf": 120, "lta": 50},
        {"id": 2, "basic": 2000, "hra": 900, "special": 200, "pf": 240, "lta": 80},
        {"id": 3, "basic": 3000, "hra": 1400, "special": 300, "pf": 360, "lta": 120},
    ])


# --- the six ugly cases the residual must survive ---------------------------


def test_duplicate_employee_ids_still_ties():
    left = base_left()
    # id 2 duplicated in the current period.
    right = payroll([
        {"id": 1, "basic": 1100, "hra": 500, "special": 100, "pf": 120, "lta": 50},
        {"id": 2, "basic": 2000, "hra": 900, "special": 200, "pf": 240, "lta": 80},
        {"id": 2, "basic": 2500, "hra": 900, "special": 200, "pf": 300, "lta": 80},
    ])
    r, _ = _reconcile(left, right)
    assert r.comparable is True
    assert _identity_holds(r)
    assert abs(r.retained_residual) < MATERIALITY


def test_employee_only_in_one_file():
    left = base_left()
    right = payroll([  # id 3 gone (leaver), id 4 new (joiner)
        {"id": 1, "basic": 1100, "hra": 500, "special": 100, "pf": 120, "lta": 50},
        {"id": 2, "basic": 2000, "hra": 900, "special": 200, "pf": 240, "lta": 80},
        {"id": 4, "basic": 2200, "hra": 800, "special": 150, "pf": 250, "lta": 60},
    ])
    r, _ = _reconcile(left, right)
    assert (r.leavers.count, r.joiners.count) == (1, 1)
    assert _identity_holds(r)
    assert abs(r.retained_residual) < MATERIALITY


def test_part_month_joiner_prorated():
    left = base_left()
    right = payroll([
        {"id": 1, "basic": 1000, "hra": 500, "special": 100, "pf": 120, "lta": 50},
        {"id": 2, "basic": 2000, "hra": 900, "special": 200, "pf": 240, "lta": 80},
        {"id": 3, "basic": 3000, "hra": 1400, "special": 300, "pf": 360, "lta": 120},
        {"id": 9, "basic": 250, "hra": 120, "special": 10, "pf": 30, "lta": 0},  # 5-day joiner
    ])
    r, _ = _reconcile(left, right)
    assert r.joiners.count == 1
    assert abs(r.joiners.amount - (250 + 120 + 10 - 30 + 0)) < 0.01  # their full net payable
    assert _identity_holds(r)
    assert abs(r.retained_residual) < MATERIALITY


def test_component_present_in_one_schema_only():
    left = base_left()  # has Special Allowance
    right = payroll([   # Special Allowance column absent entirely this period
        {"id": 1, "basic": 1100, "hra": 520, "pf": 122, "lta": 50},
        {"id": 2, "basic": 2050, "hra": 900, "pf": 244, "lta": 80},
        {"id": 3, "basic": 3000, "hra": 1400, "pf": 360, "lta": 120},
    ], drop=("Special Allowance",))
    r, _ = _reconcile(left, right)
    assert _identity_holds(r)
    # residual holds because the ring-fence uses stored Gross Earnings, which each
    # file computes over its own columns — a dropped component cannot desync it.
    assert abs(r.retained_residual) < MATERIALITY


def test_negative_net_payable():
    left = base_left()
    right = payroll([
        {"id": 1, "basic": 1000, "hra": 500, "special": 100, "pf": 120, "lta": 50},
        {"id": 2, "basic": 2000, "hra": 900, "special": 200, "pf": 240, "lta": 80},
        {"id": 3, "basic": 100, "hra": 0, "special": 0, "pf": 5000, "lta": 0},  # recovery > earnings
    ])
    r, _ = _reconcile(left, right)
    # id 3 net payable is now 100 - 5000 = -4900
    assert r.total_right < r.total_left
    assert _identity_holds(r)
    assert abs(r.retained_residual) < MATERIALITY


def test_reimbursement_heavy_run():
    left = base_left()
    right = payroll([  # earnings flat, reimbursements spike (travel claims cleared)
        {"id": 1, "basic": 1000, "hra": 500, "special": 100, "pf": 120, "lta": 40000},
        {"id": 2, "basic": 2000, "hra": 900, "special": 200, "pf": 240, "lta": 55000},
        {"id": 3, "basic": 3000, "hra": 1400, "special": 300, "pf": 360, "lta": 60000},
    ])
    r, _ = _reconcile(left, right)
    # the swing is reimbursement, not compensation cost — the ring-fence must show it
    assert abs(r.retained_compensation_delta) < 0.01
    assert r.retained_reimbursement_delta > 100000
    assert _identity_holds(r)
    assert abs(r.retained_residual) < MATERIALITY


def test_the_messy_month_all_at_once():
    """Every ugly feature in one run: a dup id, a leaver, a joiner, negative net,
    and a reimbursement swing. The bridge must still tie and the residual hold."""
    left = base_left()
    right = payroll([
        {"id": 1, "basic": 1200, "hra": 600, "special": 100, "pf": 130, "lta": 9000},  # reimb swing
        {"id": 2, "basic": 2000, "hra": 900, "special": 200, "pf": 240, "lta": 80},
        {"id": 2, "basic": 2000, "hra": 900, "special": 200, "pf": 240, "lta": 80},    # dup id
        {"id": 4, "basic": 50, "hra": 0, "special": 0, "pf": 9000, "lta": 0},          # joiner, negative net
    ])  # id 3 is a leaver
    r, _ = _reconcile(left, right)
    assert r.comparable is True
    assert _identity_holds(r)
    assert abs(r.retained_residual) < MATERIALITY


# --- the case that MUST NOT tie: inconsistent stored subtotals --------------


def test_inconsistent_subtotals_are_flagged_not_hidden():
    left = base_left()
    # id 1's consistent Net Payable is GE 1700 − PF 120 + LTA 50 = 1630; overstate it
    # by exactly 25 in the file, so the ring-fence should leave a 25 residual.
    right = payroll([
        {"id": 1, "basic": 1100, "hra": 500, "special": 100, "pf": 120, "lta": 50, "net_payable": 1655},
        {"id": 2, "basic": 2000, "hra": 900, "special": 200, "pf": 240, "lta": 80},
        {"id": 3, "basic": 3000, "hra": 1400, "special": 300, "pf": 360, "lta": 120},
    ])
    r, codes = _reconcile(left, right)
    # the top-level identity STILL holds (it is defined on the anchor itself)
    assert _identity_holds(r)
    # but the ring-fence cannot explain 25 of it — surfaced, above materiality
    assert abs(r.retained_residual) >= MATERIALITY
    assert abs(r.retained_residual - 25.0) < 0.01
    assert "reconciliation-residual" in codes
