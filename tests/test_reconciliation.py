"""Tests for the Reconciliation analyzer (M11).

The bridge's core promise is a *structural* tie-out: the population buckets sum
to the headline delta, and the retained bucket splits into compensation-cost +
reimbursement + residual, to the rupee. These are properties, asserted on a
synthetic payroll mirror (a leaver, a joiner, two retained) — never the real
gitignored pair.
"""

from __future__ import annotations

import json

from _helpers import col, dataset
from excel_analysis.adapters.serialization import analysis_to_json
from excel_analysis.domain.aligner import align
from excel_analysis.domain.comparator import compare
from excel_analysis.domain.diagnostics import Diagnostics
from excel_analysis.domain.models import (
    AnalysisResult,
    ColumnRole,
    ColumnType,
    PayCategory,
    RowMatchBasis,
)
from excel_analysis.domain.profiler import profile_dataset
from excel_analysis.domain.reconciliation import reconcile

N = ColumnType.NUMBER


def _payroll(ids, basic, hra, pf, lta, *, net_payable_override=None):
    """Build a payroll Dataset whose stored subtotals tie by construction:
    Gross Earnings = Basic+HRA, Gross Deduction = PF, Net Pay = GE-GD,
    Gross Reimbursement = LTA, Net Payable = Net Pay + GR."""
    ge = [b + h for b, h in zip(basic, hra)]
    gd = list(pf)
    net_pay = [e - d for e, d in zip(ge, gd)]
    gr = list(lta)
    net_payable = net_payable_override or [n + r for n, r in zip(net_pay, gr)]
    return dataset([
        col("Employee_ID", ids, N),
        col("Basic", basic, N),
        col("HRA", hra, N),
        col("Gross Earnings", ge, N),
        col("PF", pf, N),
        col("Gross Deduction", gd, N),
        col("Net Pay", net_pay, N),
        col("LTA Reimbursement", lta, N),
        col("Gross Reimbursement", gr, N),
        col("Net Payable", net_payable, N),
    ])


def _reconcile(left, right, **kw):
    diags = Diagnostics()
    result = reconcile(left, right, align(left, right, diags), **kw)
    return result, [d.code for d in result.diagnostics]


# ids 1(leaver),2,3 in A ; 2,3,4(joiner) in B
LEFT = _payroll([1, 2, 3], basic=[100, 200, 300], hra=[50, 100, 150], pf=[20, 30, 40], lta=[10, 20, 30])
RIGHT = _payroll([2, 3, 4], basic=[220, 300, 500], hra=[100, 150, 200], pf=[30, 50, 60], lta=[5, 30, 0])


def test_default_anchor_and_key():
    r, _ = _reconcile(LEFT, RIGHT)
    assert r.comparable is True
    assert r.anchor == "Net Payable" and r.anchor_substituted is False
    assert r.key_column == "Employee_ID"


def test_population_buckets_sum_to_delta():
    r, _ = _reconcile(LEFT, RIGHT)
    # A total = 140+290+440 = 870 ; B total = 295+430+640 = 1365
    assert r.total_left == 870.0 and r.total_right == 1365.0
    assert r.delta == 495.0
    assert (r.joiners.count, r.joiners.amount) == (1, 640.0)   # id4
    assert (r.leavers.count, r.leavers.amount) == (1, -140.0)  # id1
    assert (r.retained.count, r.retained.amount) == (2, -5.0)  # id2:+5, id3:-10
    assert abs(r.delta - (r.joiners.amount + r.leavers.amount + r.retained.amount)) < 1e-9


def test_retained_ring_fence_ties():
    r, _ = _reconcile(LEFT, RIGHT)
    # comp = ΔNetPay: id2 +20, id3 -10 = +10 ; reimb = ΔGR: id2 -15, id3 0 = -15
    assert r.retained_compensation_delta == 10.0
    assert r.retained_reimbursement_delta == -15.0
    assert r.retained_residual == 0.0
    total = (r.retained_compensation_delta + r.retained_reimbursement_delta + r.retained_residual)
    assert abs(total - r.retained.amount) < 1e-9


def test_category_flows_from_stored_subtotals():
    r, _ = _reconcile(LEFT, RIGHT)
    flows = {f.category: f for f in r.category_flows}
    assert flows[PayCategory.EARNING].subtotal_column == "Gross Earnings"
    assert flows[PayCategory.DEDUCTION].subtotal_column == "Gross Deduction"
    assert flows[PayCategory.REIMBURSEMENT].subtotal_column == "Gross Reimbursement"
    # earning + deduction contributions equal compensation-cost movement
    assert flows[PayCategory.EARNING].amount + flows[PayCategory.DEDUCTION].amount == r.retained_compensation_delta


def test_classification_roles_and_categories():
    r, _ = _reconcile(LEFT, RIGHT)
    by_name = {c.column: c for c in r.classification}
    assert by_name["Employee_ID"].role is ColumnRole.IDENTITY
    assert by_name["Basic"].role is ColumnRole.COMPONENT and by_name["Basic"].category is PayCategory.EARNING
    assert by_name["PF"].category is PayCategory.DEDUCTION
    assert by_name["LTA Reimbursement"].category is PayCategory.REIMBURSEMENT
    assert by_name["Gross Earnings"].role is ColumnRole.SUBTOTAL
    assert all(c.confidence == 1.0 for c in r.classification)


def test_anchor_switch_to_gross_earnings():
    r, _ = _reconcile(LEFT, RIGHT, anchor="Gross Earnings")
    assert r.anchor == "Gross Earnings" and r.anchor_substituted is False
    # retained movement is purely earnings; no reimbursement split, no residual
    assert r.retained_reimbursement_delta == 0.0
    assert r.retained_residual == 0.0
    assert r.retained_compensation_delta == r.retained.amount


def test_absent_anchor_substitutes_loudly():
    r, codes = _reconcile(LEFT, RIGHT, anchor="Cost To Company")
    assert r.anchor == "Net Payable" and r.anchor_substituted is True
    assert "reconciliation-anchor-substituted" in codes


def test_residual_is_surfaced_not_hidden():
    # Break the stored identity: Net Payable is 7 too high for id3 in B.
    right = _payroll([2, 3, 4], basic=[220, 300, 500], hra=[100, 150, 200],
                     pf=[30, 50, 60], lta=[5, 30, 0], net_payable_override=[295, 437, 640])
    r, codes = _reconcile(LEFT, right)
    assert r.retained_residual == 7.0
    assert "reconciliation-residual" in codes
    # top-level identity still holds regardless of the stored-subtotal defect
    assert abs(r.delta - (r.joiners.amount + r.leavers.amount + r.retained.amount)) < 1e-9


def test_serialized_contract_shape():
    """Lock the JSON the SPA consumes: additive datasets + reconciliation blocks."""
    diags = Diagnostics()
    al = align(LEFT, RIGHT, diags)
    diff = compare(LEFT, RIGHT, al, diags)
    rec = reconcile(LEFT, RIGHT, al)
    result = AnalysisResult(
        left_profile=profile_dataset(LEFT), right_profile=profile_dataset(RIGHT),
        diff=diff, warnings=diags.to_tuple(), insights=(),
        left_dataset=LEFT, right_dataset=RIGHT, reconciliation=rec,
    )
    data = json.loads(analysis_to_json(result))

    ds = data["datasets"]
    assert ds["left"]["n_rows"] == 3 and ds["right"]["n_rows"] == 3
    assert ds["left"]["columns"][0]["name"] == "Employee_ID"
    assert len(ds["right"]["rows"]) == 3 and len(ds["right"]["rows"][0]) == len(ds["right"]["columns"])

    rc = data["reconciliation"]
    assert rc["comparable"] is True and rc["anchor"] == "Net Payable"
    assert rc["delta"] == 495.0
    assert rc["buckets"]["joiners"]["count"] == 1 and rc["buckets"]["leavers"]["count"] == 1
    assert rc["retained"]["compensation_delta"] == 10.0
    assert rc["retained"]["reimbursement_delta"] == -15.0
    assert {f["category"] for f in rc["category_flows"]} == {"earning", "deduction", "reimbursement"}
    assert any(c["role"] == "component" and c["category"] == "earning" for c in rc["classification"])


def test_not_comparable_without_a_total_column():
    left = dataset([col("Employee_ID", [1, 2], N), col("Notes", ["a", "b"])])
    right = dataset([col("Employee_ID", [2, 3], N), col("Notes", ["c", "d"])])
    r, codes = _reconcile(left, right)
    assert r.comparable is False and r.anchor is None
    assert "reconciliation-not-applicable" in codes


def test_positional_alignment_warns_no_key():
    # Duplicate values -> no column qualifies as a unique key -> POSITION.
    left = dataset([col("Net Payable", [100, 100], N), col("Basic", [100, 100], N)])
    right = dataset([col("Net Payable", [150, 150], N), col("Basic", [150, 150], N)])
    diags = Diagnostics()
    al = align(left, right, diags)
    assert al.row_basis is RowMatchBasis.POSITION
    r = reconcile(left, right, al)
    codes = [d.code for d in r.diagnostics]
    assert "reconciliation-no-key" in codes
    # identity still ties even on positional rows
    assert abs(r.delta - (r.joiners.amount + r.leavers.amount + r.retained.amount)) < 1e-9
